# 丰富器与刮削器架构设计与实现

## 总览
- 目标：将本地媒体文件的元数据自动丰富为结构化的领域模型，并完成版本绑定与侧车本地化。
- 数据流：文件 → 解析文件名 → 插件搜索 → 插件详情（剧集优先季详情缓存） → 持久化映射 → 版本绑定 → 事务提交 → 侧车本地化。
- 关键组件：
  - 刮削插件（ScraperPlugin），例如 TMDB 插件 `services/scraper/tmdb.py`。
  - 插件管理器（ScraperManager）`services/scraper/manager.py`。
  - 元数据丰富器（MetadataEnricher）`services/media/metadata_enricher.py`。
  - 持久化服务（MetadataPersistenceService）`services/media/metadata_persistence_service.py`。

## 架构设计
- 分层职责：
  - 插件层（采集）：与外部 API 交互，统一返回 `ScraperResult`。
  - 管理器层（编排）：插件注册/启用、策略搜索（含语言回退）、生命周期管理。
  - 业务层（丰富器）：单文件内核与批量驱动，事务与侧车边界控制。
  - 持久化层：将 `ScraperResult` 一次性映射到领域模型（Movie/TV Series/Season/Episode，附属 Artwork/Genres/ExternalIDs/Credits），并完成版本绑定。
- 低耦合原则：插件不持久化；持久化不依赖插件内部形态；统一契约 `ScraperResult` 是唯一跨层数据协议。

## 模块说明
- ScraperPlugin 抽象 `services/scraper/base.py`
  - 能力字段 `capabilities`（可选）：`batch_series/batch_season/hierarchical_cache`。
  - 接口：`search`、`get_details`、`get_season_details`（新增）、`get_episode_details`。
  - 生命周期：`startup/shutdown` 用于资源初始化与清理。
- ScraperManager `services/scraper/manager.py`
  - 插件注册/加载/启用：`ensure_default_plugins()`。
  - 策略搜索：`search_media_with_policy(title, year, media_type, language)`，内置 zh-CN → en-US 回退。
  - 生命周期：`startup/shutdown`。
- MetadataEnricher `services/media/metadata_enricher.py`
  - 单文件内核：解析 → 策略搜索 → 详情（剧集优先季缓存命中） → 持久化映射 → 版本绑定 → 提交 → 侧车入队。
  - 批量驱动：并发调度多个文件，每个文件仍走“单文件内核”，确保事务与容错以文件为单位。
- MetadataPersistenceService `services/media/metadata_persistence_service.py`
  - `apply_metadata(session, media_file, result)`：统一幂等 upsert 一次性应用所有映射。
  - `bind_version(session, media_file, parse_out)`：版本建模与首选选择。

## 数据契约（覆盖版 ScraperResult）
- 位置：`services/scraper/base.py`
- 字段：
  - 基本：`title/original_title/year/release_date/runtime/overview/tagline/rating/vote_count`。
  - 分类：`genres/countries/languages`（字符串列表）。
  - 标识：`provider/provider_id/provider_url`，`external_ids[{provider, external_id, url?}]`。
  - 艺术：`artworks[{type,url,width?,height?,language?,rating?,vote_count?}]`。
  - 电影合集：`collection={id,name,poster_path?,backdrop_path?,overview?}`。
  - 剧集分层：
    - `series={title, overview?, season_count?, episode_count?}`。
    - `seasons=[{season_number, overview?, aired_date?, episode_count?, runtime?}]`。
    - `episodes=[{season_number, episode_number, title, overview?, aired_date?, runtime?, rating?, vote_count?, still_path?}]`。
  - 原始：`raw_data`（保留原始 JSON）。

## 流程细节
- 单文件内核（丰富器）：
  1. 文件名解析，识别媒体类型（电影/电视剧单集/季归档）。
  2. 调用管理器策略搜索（含语言回退），获取候选，选择最佳匹配。
  3. 获取详情：
     - 电视剧优先季详情（`get_season_details`）命中缓存，单集详情由季中抽取，必要时补齐 credits；缓存未命中再回退单集端点。
  4. 调用持久化服务：一次性幂等 upsert 到领域模型，并版本绑定与首选选择。
  5. 提交事务；入队侧车任务（如图片本地化）。
- 批量刮削（丰富器）：
  - 能力探测（插件能力 `capabilities.hierarchical_cache`）：如可用，先批量预热季详情缓存；随后对每个文件执行“单文件内核”。

## TMDB 插件实现与优化
- 文件：`services/scraper/tmdb.py`
- 季详情与分层缓存：
  - `_season_cache[(series_id, season_number, language)]` 存储季详情；TTL 可扩展。
  - `get_season_details(series_id, season, language)` 拉取季详情并构造 `episodes[]`（标题、概览、播出日期、时长、评分、still_path）。
- 单集详情优先缓存：`get_episode_details` 先查季缓存，命中则构造 `ScraperResult`；缓存未命中回退到单集端点。
- 系列详情增强：`get_details(TV_SERIES)` 填充 `series/seasons` 概览信息。
- 生命周期与资源：`shutdown()` 关闭 `aiohttp.ClientSession`，避免“Unclosed client session”。

## 持久化映射
- 文件：`services/media/metadata_persistence_service.py`
- 电影：顶层字段与 `collection` 映射到 `MovieExt/Collection`。
- 电视剧分层：
  - `series` → `SeriesExt`（概览/季数/总集数）。
  - `seasons[]` → 匹配季号写入 `SeasonExt`（概览/播出日期/集数/时长）。
  - `episodes[]` → 匹配集号写入 `EpisodeExt`（标题/概览/播出日期/时长/评分/投票数/still_path）。
- 通用：`ExternalID/Artwork/Genre/MediaCoreGenre/Person/Credit` 幂等写入。
- 版本绑定：在同事务内完成版本创建与首选选择，避免读写不一致。

## 并发与缓存策略
- 并发控制：
  - 批量端点使用 `asyncio.Semaphore` 控制并发；单文件内核并发更小。
- 缓存层次：
  - 插件实例级内存缓存（series/season/episode）；后续支持 Redis 注入。
- 降级与重试：
  - 字段缺失或缓存未命中时回退单集端点；仅按需补齐 credits；记录降级日志。

## 错误处理与可观测性
- 管理器与丰富器记录限流/降级与失败计数。
- 指标建议：
  - 季缓存命中率
  - 详情端点调用次数
  - 平均响应耗时
  - 失败率与重试次数

## 配置项（示例）
- 插件鉴权：API Key 或 V4 Token。
- 语言策略：`zh-CN → en-US` 回退。
- 并发与批量开关：在插件或管理器中配置。

## 测试与验收
- 单元测试：
  - 季缓存命中与回退路径（`tests/test_tmdb_cache.py`, `tests/test_tmdb_fallback.py`）。
  - 系列概览填充（`tests/test_tmdb_series_seasons_overview.py`）。
  - 分层持久化映射与日期转换（`tests/test_persistence_episodes.py`）。
  - 幂等性验证（`tests/test_persistence_idempotent.py`）。
- 验收指标：调用次数与耗时显著下降；重复执行不产生重复记录；电影路径不受影响。

## 关键代码参考
- 数据契约与插件抽象：`services/scraper/base.py:49`（ScraperResult 覆盖版）、`services/scraper/base.py:140`（插件扩展接口与能力）。
- 插件管理器策略搜索与默认启用：`services/scraper/manager.py:232-281`。
- TMDB 插件季缓存与单集回退：`services/scraper/tmdb.py:46`（缓存初始化）、`services/scraper/tmdb.py:308`（单集详情优先缓存）、`services/scraper/tmdb.py:540`（季详情）。
- 元数据丰富器编排：`services/media/metadata_enricher.py:118-133`（插件启用）、`services/media/metadata_enricher.py:128-133`（策略搜索）、`services/media/metadata_enricher.py:171-189`（统一持久化应用）。
- 持久化分层适配：`services/media/metadata_persistence_service.py:17`（日期解析）、`services/media/metadata_persistence_service.py:72-158`（series/seasons/episodes 映射）。

## 扩展与维护
- 新插件接入：实现 `ScraperPlugin`，返回覆盖版 `ScraperResult`；注册至管理器并启用。
- 批量能力：
  - 插件可实现批量辅助或声明能力；管理器在批量任务路径上优先使用批量接口（能力存在时），否则按单次路径执行。
- 文档更新：本文件为单一入口，新增能力或字段时更新“数据契约/流程/测试”三节。