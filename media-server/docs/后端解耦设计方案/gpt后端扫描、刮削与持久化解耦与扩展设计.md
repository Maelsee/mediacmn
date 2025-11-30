# 后端扫描、刮削与持久化解耦与扩展设计

- 目标：解耦“存储与扫描”“扫描与丰富化”“丰富化与持久化”，并使数据库与业务可扩展到综艺、动画、纪录片等多类型。
- 背景与现状：
  - 异步扫描服务入口在 `services/scan/enhanced_async_scan_service.py:61`，通过统一任务调度器创建任务 `services/task/unified_task_scheduler.py:108`。
  - 扫描引擎已抽象到统一引擎 `services/scan/unified_scan_engine.py`，默认注册处理器 `services/scan/unified_scan_engine.py:470`，但组合任务仍在调度层紧耦合元数据任务 `services/task/unified_task_scheduler.py:362`。
  - 丰富化入口在 `services/media/metadata_enricher.py:34`，持久化策略集中在 `services/media/metadata_persistence_service.py:342, 625`，当前仅电影/剧集路径完善。
  - 存储抽象已存在：`StorageService` 与多个客户端 `services/storage/storage_service.py:1`，`get_client` 便捷方法 `services/storage/storage_service.py:369`，支持 WebDAV/SMB/Local（Cloud 结构已预留）。
  - 数据模型以 `MediaCore.kind` 为中心（`movie|tv_series|tv_season|tv_episode`）`models/media_models.py:46`，剧集扩展与季/集模型基本完备，绝对集序字段已预留注释 `models/media_models.py:205`。

## 1. 扫描与存储解耦设计

- 设计原则：Ports & Adapters，扫描只依赖抽象的“目录枚举/条目流”，不感知具体存储协议。
- 抽象契约：
  - `StorageClient` 已统一定义 `list_dir/info` 等操作（参考 `services/storage/storage_client.py:119, 134`）。继续将扫描的输入建模为 `AsyncGenerator[StorageEntry]`。
  - 新增“扫描源”概念：`ScanSource`（适配器）：从任意 `StorageClient` 拉取条目，统一产出 `StorageEntry` 流；负责分页、断点、重试、速率限制与路径规范化。
- 扫描管线（引擎内）：
  - `Enumerator`：消费 `ScanSource`，按 `path/depth` 递归/分页生成 `StorageEntry`。
  - `Classifier`：基于 `mimetype/扩展名/父目录`，决定资产角色与候选媒体类型（复用 `FilenameParser` 逻辑）。
  - `FileAssetProcessor`：幂等 upsert 文件到 `file_asset`（当前已存在，参考 `services/scan/unified_scan_engine.py:470`）。
  - `PostProcessors`：插件链（字幕/NFO/海报同名文件识别、技术指纹计算、软删除标记）。
- 存储适配器扩展：
  - WebDAV：已有 `services/storage/storage_clients/webdav_client.py`；
  - SMB：已有 `services/storage/storage_clients/smb_client.py`；
  - Local：已有 `services/storage/storage_clients/local_client.py`；
  - Cloud：基于预留 `CloudStorageConfig`（`services/storage/storage_service.py:64, 108`），实现如 S3/GDrive 适配器，适配分页列目录与 Head 请求速率限制。
- 关键能力：
  - 路径规范：所有 `StorageEntry.path` 归一化为“协议根+相对路径”，在 `FileAsset.relative_path` 统一持久化，避免多协议混淆。
  - 批处理与背压：枚举层按 batch 推送，处理层按 `batch_size` 写库（现有引擎已支持）。
  - 故障隔离：适配器内置重试与断路器，错误不上抛导致扫描中断；只记录并跳过。
- 落地步骤：
  - 在扫描引擎引入 `ScanSource` 抽象，现有 `StorageService.get_client` 注入到扫描会话。
  - 将“协议特有逻辑”（分页、限流、统计）留在各 `StorageClient`/适配器；引擎不感知。
  - 完成 Cloud 适配器的第一版（只读枚举 + 断点续扫描）。

## 2. 扫描与丰富化（刮削）的解耦与优化

- 现状：组合任务在调度器内触发元数据任务 `services/task/unified_task_scheduler.py:362`，耦合扫描结果的数据结构（轻量快照、文件 ID）。
- 目标：扫描仅产出“发现事件”，丰富化由独立处理器消费事件，不存在直接函数耦合。
- 事件总线：
  - 事件类型：`NewFilesDiscovered`、`FileUpdated`、`ScanCompleted`。
  - 事件负载：`{storage_id, file_ids[], parse_snapshot_map?, encountered_paths[]}`。
  - 生产者：统一扫描引擎/调度器；消费者：`MetadataTaskProcessor`（已有）与删除对齐处理器。
- 处理器与契约：
  - `MetadataTaskProcessor` 仅消费 `file_ids`+快照，在处理时使用 `metadata_enricher.enrich_media_file`（参考 `services/media/metadata_enricher.py:34`），但不依赖扫描引擎类型或任务结构。
  - 限流与断路器：保留在刮削侧（参考 `services/media/metadata_task_processor.py:1-32`），与扫描隔离。
  - 语言与策略：由 `scraper_manager` 统一策略控制（语言回退、插件健康），扫描不涉及语言。
- 优化项：
  - 将“组合任务”的创建改为“事件订阅”，即扫描结束后发布 `NewFilesDiscovered`；由元数据处理器批量创建自身的队列任务，不再通过调度器硬编码。
  - 侧车文件生成（本地化）继续异步化，保持与丰富化解耦（参考文档 `docs/sidecar_async_localization.md:73`）。

## 3. 丰富化扩展到多类型的架构

- 类型体系：
  - 扩展 `MediaType` 至：`MOVIE/TV_SERIES/TV_SEASON/TV_EPISODE/VARIETY_SERIES/VARIETY_EPISODE/ANIME_SERIES/ANIME_EPISODE/DOCUMENTARY_SERIES/DOCUMENTARY_EPISODE/SPECIAL/SHORT`。
  - 插件能力声明：`capabilities = {batch_series, batch_season, hierarchical_cache, supports_variety, supports_anime}`（参考 `docs/enricher_scraper_architecture.md:22`）。
- 插件接口统一：
  - `search(title, year?, media_type, language)`：由管理器做类型校正与语言回退（参考 `services/scraper/manager.py`）。
  - `get_work_details(id, media_type, language)`：对电影/系列统一入口；
  - `get_season_details(id, season, language)`、`get_episode_details(id, season, episode, language)`：剧集/综艺/动画通用。
- 策略管理：
  - 管理器根据 `media_type` 与插件能力选择最佳插件，提供 fallback；
  - 语言回退：`zh-CN → en-US → 原生`；健康检测 + 限流恢复。
- 解析与类型校正：
  - 解析器对父目录命名（如“第X期/第X话”）映射到综艺/动画的季/集；保留 `existing_snapshot` 用于批量任务（参考 `services/media/metadata_enricher.py:34-91`）。
- 存储契约（ScraperResult 扩展）：
  - 核心：`title/original_title/year/release_date/runtime/overview/tagline/rating/vote_count`。
  - 分类：`genres/countries/languages/keywords/status`。
  - 标识：`provider/provider_id/provider_url/external_ids[]`。
  - 层级：`series/seasons[]/episodes[]` 对综艺/动画同样适用；增加 `episode_type`、`absolute_episode_number` 支持番剧与特别篇。

## 4. 数据库设计评估与优化方案

- 现状评估：
  - `MediaCore.kind` 已覆盖 `movie/tv_series/tv_season/tv_episode`（`models/media_models.py:46`）。
  - `TVSeriesExt/SeasonExt/EpisodeExt` 字段基本满足通用剧集需求；`EpisodeExt.absolute_episode_number` 预留（注释）`models/media_models.py:205`。
  - 电影合集已建模为 `Collection`（`models/media_models.py:145`）。
- 扩展建议（保持兼容，最小化迁移）：
  - 在 `MediaCore` 增加 `sub_kind`（枚举：`variety/anime/documentary/music/short/special`），不改变既有 `kind`；用于细分展示与持久化策略选择。
  - 在 `EpisodeExt` 启用并持久化 `absolute_episode_number` 字段（番剧与国产剧常用），并完善 `episode_type`：`standard/finale/special` 已存在 `models/media_models.py:218`。
  - 在 `TVSeriesExt` 增加可选 `category_hint`（如 `variety/anime/documentary`），便于查询与聚合；如不改表，可先使用 `MediaCore.group_key/canonical_source` 进行规范化归类（`models/media_models.py:58-62`）。
  - 不新增 `VarietyShowExt/AnimeExt` 表，优先用现有 `TVSeriesExt/SeasonExt/EpisodeExt` 承载，减少碎片化；若未来出现明显差异化字段（如“期别主题/嘉宾列表”），再考虑单独扩展表，并通过外键与 `MediaCore` 关联。
- 规范化与索引：
  - 针对 `MediaCore.kind/sub_kind/year` 建立组合索引，提升查询；
  - 针对 `EpisodeExt(series_core_id, season_number, episode_number)` 已唯一约束 `models/media_models.py:189-191`，继续保留；对 `absolute_episode_number` 增加非唯一索引。

## 5. 持久化服务可扩展、低耦合设计

- 现状：不同类型持久化集中在一个服务内的多方法实现（如 `_apply_movie_detail` `services/media/metadata_persistence_service.py:342` 与 `_apply_search_result` `services/media/metadata_persistence_service.py:625`）。
- 目标：以策略模式/映射器插件化，按 `media_type/sub_kind` 动态分派；“一次性幂等 upsert”保留。
- 设计：
  - `PersistenceStrategy` 接口：`apply(session, media_file, scraped)`；
  - `StrategyRegistry`：按 `media_type/sub_kind/provider` 注册；默认策略处理 `movie/tv_series/tv_season/tv_episode`；
  - 映射层：通用字段映射（core/external_ids/artworks/credits/genres），类型层映射（movie_ext/tv_series_ext/season_ext/episode_ext），事务提交一处完成；
  - 版本绑定：保留 `bind_version(session, media_file, parse_out)` 的职责（已存在），与 apply 解耦；
  - 幂等性：以 `core_id+user_id` 查找/创建，`ExternalID` 以 `(user_id, core_id, source)` 唯一（`models/media_models.py:291-292`），避免重复；
  - 回退策略：当仅有 `ScraperSearchResult` 时，先入 `MediaCore`，后续详情补全；
- 扩展到综艺/动画：
  - 综艺/动画的季/集同样用 `SeasonExt/EpisodeExt`，按 `sub_kind` 决定额外字段是否映射（如 `absolute_episode_number`）。

## 6. 接口与任务编排调整

- 扫描 API 保持：`start_async_scan` `services/scan/enhanced_async_scan_service.py:61`。
- 调度器调整：
  - 从“组合任务创建元数据任务”改为“发布事件”，由 `MetadataTaskProcessor` 订阅并创建自身任务；减少耦合（现逻辑参考 `services/task/unified_task_scheduler.py:362`）。
  - `DeleteSyncService` 继续消费 `encountered_media_paths`（现已存在）。
- 任务与限流：限流与断路器留在刮削侧（`services/media/metadata_task_processor.py:1-32`），扫描只做 I/O 枚举与入库。

## 7. 迁移路径

- 阶段A：保持现有功能，增加 `sub_kind` 字段并开始在解析器与丰富化中填充；持久化映射内策略化分派，但保留现有方法。
- 阶段B：将“组合任务”的元数据创建改为事件驱动；`MetadataTaskProcessor` 订阅事件并批量创建任务。
- 阶段C：完善 Cloud 适配器，只读枚举上线；在扫描引擎引入 `ScanSource` 抽象并完成统一接入。
- 阶段D：针对综艺/动画的解析规则与映射增强（绝对集序/特别篇），完成端到端链路。

## 8. 验收标准

- 解耦：任意存储新增仅需实现一个适配器，扫描引擎无改动；扫描完成与刮削互不影响，任何一方失败不阻塞另一方。
- 扩展性：新增类型不改数据库核心结构，仅在 `sub_kind` 与策略注册层改动；持久化映射无需修改核心引擎。
- 可靠性：枚举/刮削分别有独立的限流与断路器；任务状态可追踪，失败可重试。

## 9. 参考与代码定位

- 扫描服务入口：`services/scan/enhanced_async_scan_service.py:61, 104`
- 调度器创建扫描任务：`services/task/unified_task_scheduler.py:108`
- 调度器组合任务耦合处：`services/task/unified_task_scheduler.py:362`
- 扫描引擎处理器注册：`services/scan/unified_scan_engine.py:470`
- 存储服务与客户端：`services/storage/storage_service.py:369`、`services/storage/storage_clients/*`
- 丰富化入口：`services/media/metadata_enricher.py:34`
- 持久化电影映射：`services/media/metadata_persistence_service.py:342`
- 持久化搜索回退：`services/media/metadata_persistence_service.py:625`
- 数据模型核心：`models/media_models.py:46, 145, 189-191, 205`

