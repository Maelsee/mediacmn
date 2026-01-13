媒体播放器前后端字幕与选集API接入：

- 后端：
  - 在 `media_service.py` 中实现基于 `fileId` 的字幕与选集查询逻辑，支持同目录外挂字幕与剧集选集列表返回。
  - 在 `routes_media.py` 中新增 `/api/media/subtitles/{file_id}` 与 `/api/media/episodes/{file_id}` 两个接口，并完成权限与参数校验。

- 前端：
  - 在 `ApiClient` 中新增 `getSubtitles` 与 `getEpisodes` 方法，对接后端接口。
  - 在 `MediaPlayerState` 中增加 `fileId` 字段，由 `PlayerNotifier.open` 负责更新当前播放文件 ID。
  - 在 `MediaPlayerPage` 中接入选集 API：优先通过 `/api/media/episodes/{file_id}` 获取选集列表，失败时回退到详情中的 `seasons/episodes` 结构解析，统一整理为 `_episodes` 列表并通过 `PlayerLayout` 传递给各平台 UI。
  - 在浏览器端播放器布局 `BrowserPlayerLayout` 中，监听当前播放 `fileId` 变化，调用 `getSubtitles` 拉取外挂字幕列表，并在「字幕/音轨」面板中分组展示「内嵌字幕」与「外挂字幕」。

- 文档与测试：
  - 更新 `media_player/README.md` 中的选集与字幕方案，记录当前实现细节与后续计划。
  - 运行 `flutter analyze` 与后端 `pytest`，当前均通过，无新增错误，仅保留少量非阻塞告警。

- 2025-12-28 修复 WebDAV 外挂字幕鉴权问题：
  - 问题：`media_kit` 播放器加载外挂字幕时无法附加 Headers，导致 WebDAV 字幕因缺权无法加载。
  - 解决：后端 `media_service.py` 在生成 WebDAV 字幕 URL 时，检测并自动将 Basic Auth 凭据嵌入 URL 中（`http://user:pass@host...`）。
  - 更新：同步更新了播放器架构文档 `media_client/lib/media_player/README.md` 说明。

- 2025-12-31 新增远程服务器 Docker 部署方案（FastAPI 后端）：
  - 新增 `media-server/Dockerfile` 与 `media-server/.dockerignore`，支持构建后端镜像并运行 Uvicorn。
  - 新增生产编排 `docker-compose.prod.yml`：包含 Postgres、Redis 队列、Redis 缓存、API、Dramatiq Worker、Caddy（HTTPS 反向代理）。
  - 新增部署模板 `deploy/.env.prod.example` 与 `deploy/Caddyfile`，并在 `.gitignore` 中忽略 `deploy/.env.prod` 防止泄露密钥。
  - 后端健康检查增强：`/api/health/ready` 增加数据库与两套 Redis 可用性探测；并修复 OpenAPI/Docs 路径为 `/api/docs`。
  - 修复部署启动稳定性：API 启动时仅在存在 Alembic 配置与迁移目录时执行迁移，并为健康检查增加 `start_period`，降低冷启动误判。
  - 新增部署文档 `DEPLOYMENT.md`，包含远程部署、升级与备份流程。

- 2026-01-04 修复存储配置更新 500 异常：
  - 问题：更新接口将 `config` 序列化成 dict 传入服务层，导致 `model_dump` 调用报错（`AttributeError: 'dict' object has no attribute 'model_dump'`）。
  - 解决：路由层保持 `config` 为 Pydantic 模型传给服务层；服务层同时兼容 dict/BaseModel 两种输入。
  - 测试：新增回归测试覆盖 dict 形式的 `config` 更新与 `select_path` 序列化。

- 2026-01-06 名称解析准确率优化（GuessIt + 路径预处理）：
  - 问题：直接对完整路径使用 GuessIt 时，中文分类目录/存储前缀/范围目录/“第X话”等噪声导致 title/season/episode/type 误判。
  - 解决：实现 `MediaParser` 对路径进行预处理与提示抽取（expected_title、中文集季转写、强制剧集判定），并在 `metadata_enricher.py` 中统一接入替代直接 guessit 调用。
  - 配套：增加 `tests/test_media_parser.py` 覆盖综艺/动画典型样例；新增 `media-server/pytest.ini` 忽略 vendored guessit 测试目录避免与 site-packages 冲突。
  - 文档：更新 `media-server/utils/name_parser.md` 记录最终方案与后续演进方向。

- 2026-01-06 媒体解析器人工标注数据集重构与评估：
  - 任务：根据用户要求，确认 `media_parser_dataset_paths.jsonl` 正确性，并全人工重构 `media_parser_dataset_labels.jsonl`。
  - 数据集：筛选并人工标注了 1001 条非电影路径（电视剧、动画、综艺），移除了所有电影路径以减少噪声。
  - 标注：逐条判断路径中的标题、年份、季、集信息，确保标注质量。
  - 评估：更新了评估脚本 `evaluate_media_parser_dataset.py` 以兼容新的扁平化标注格式。
  - 结果：初步评估显示季（90.1%）与集（94.4%）解析准确率较高，标题（72.7%）与年份（57.1%）仍有优化空间，主要原因是解析器类型定义（episode vs tv/anime）不一致导致整体准确率为 0%，后续需对齐类型定义。

- 2026-01-06 综艺“第N期上/PartN”命名解析与刮削链路修复：
  - 问题：对于 `/dav/302/133quark302/综艺/现在就出发/S03/2025.11.08-第3期上.mp4` 等综艺路径，名称解析器未填充 `episode/part`，导致组级刮削阶段在 `metadata_enricher.py` 内检测到 `episode` 为空而直接返回空 `contract_payload`，无法绑定到季详情中的对应单集。
  - 解析器：在 `MediaParser._preprocess_name` 与 `parse` 后处理逻辑中，新增对“第N期”中文期号与“上/中/下”和 `PartN` 文本的识别，将“第3期上”归一为 `episode=3, part=1`，并保证综艺目录下的“第N期中/下”分别映射到 `part=2/3`，统一交由解析器输出 `episode/part` 字段。
  - 丰富器：在 `MetadataEnricher` 组级装配逻辑中，仅消费 `path_info` 中的 `episode/part` 字段：按 `episode` 精确匹配季详情中的单集条目，并在返回的 `contract_payload` 中透传 `part` 字段，避免在业务层重复解析文件名，明确“解析器负责命名解析、丰富器负责刮削与组装”的职责分工。
  - 测试：扩展 `tests/test_media_parser.py` 新增综艺样例用例，覆盖“第3期上”路径的季、集与分段解析；后端 `pytest` 全量 16 项测试全部通过，保证改动稳定性。

- 2026-01-06 手动匹配（文件 ↔ TMDB 剧集/季/集）方案设计：
  - 产出：在 `media-server/DEVELOPMENT.md` 追加前端页面、交互流程、后端处理与 API/数据结构设计。

- 2026-01-06 手动匹配：TMDB 代理查询接口实现：
  - 新增 `/api/tmdb/search/tv`、`/api/tmdb/tv/{series_tmdb_id}`、`/api/tmdb/tv/{series_tmdb_id}/season/{season_number}` 三个接口，统一要求 Bearer 鉴权。
  - 新增 `services/tmdb_proxy_service.py`、`schemas/tmdb_proxy.py`，并补充 `tests/test_tmdb_proxy_routes.py` 回归测试。
  - 同步更新 `media-server/DEVELOPMENT.md` 对应接口说明。

- 2026-01-06 手动匹配：TMDB 代理电影搜索接口：
  - 新增 `/api/tmdb/search/movie`，请求/响应结构与系列搜索一致（page/total/items）。
  - 更新 `media-server/DEVELOPMENT.md` 增加电影搜索接口文档段落。
  - 补充 `tests/test_tmdb_proxy_routes.py` 覆盖电影搜索成功与未配置场景。

- 2026-01-07 手动匹配：提交手动绑定接口（manual-match）：
    - 新增 `PUT /api/media/{media_id}/manual-match`，支持 TV(bind_episode) 与 Movie(bind_movie) 手动绑定请求。
    - 接口内部直接基于前端提供的 TMDB ID/季集编号拉取详情契约并入队批量持久化任务（persist_batch），跳过名称解析。
    - 新增 `tests/test_manual_match_routes.py` 覆盖 TV 成功入队与文件不存在错误场景。

- 2026-01-10 依赖管理优化：
    - 更新 `media-server/requirements.txt`，完整导出当前虚拟环境中的所有 Python 模块及其版本。

- 2026-01-10 部署稳定性与测试方案优化：
    - 修复 Docker 构建超时问题：在 `media-server/Dockerfile` 中切换为国内可访问的基础镜像源（`docker.1ms.run`），并更新 `DEPLOYMENT.md` 说明解决方法。
    - 增强部署文档：在 `DEPLOYMENT.md` 中新增「测试与验证」章节，提供容器状态检查、API 健康检查、数据库/Redis 连通性验证等详细步骤。
    - 验证部署配置：通过 `docker compose config` 验证了生产编排文件的语法与环境变量必填项约束。

- 2026-01-10 TMDB 代理超时处理与网络兼容性增强：
  - 问题：服务器环境通过 Vercel TMDB 代理访问时偶发卡住/超时，FastAPI 路由侧表现为 500（未能正确映射为超时或上游错误）。
  - 解决：`TmdbProxyService` 引入请求级超时、连接超时与更细粒度的异常分类，超时统一映射为 504；并增加 `TMDB_FORCE_IPV4` 开关，在疑似 IPv6 路由异常的服务器环境中可强制使用 IPv4。
  - 同步：`TmdbScraper` 的请求超时改为读取 `TMDB_TIMEOUT`，并在连通性探测中复用同样的超时/代理参数。
  - 测试：扩展 `tests/test_tmdb_proxy_routes.py` 覆盖超时场景的 504 返回；全量 `pytest` 通过。

- 2026-01-10 修复 Worker 刮削任务启动卡住：
  - 现象：容器内 curl 可访问 TMDB 代理，但 metadata 刮削任务在“启动插件系统/自动发现插件”阶段卡住。
  - 解决：为 `ScraperManager` 插件连接测试与 startup 钩子增加超时保护；`metadata_worker` 补救启动加入超时并明确报错；`TmdbScraper` 会话支持强制 IPv4 且所有请求统一走带超时的 `_get`；生产 worker 线程数调整为 1 以避免跨事件循环锁/任务问题。
  - 测试：新增 `tests/test_scraper_manager_timeouts.py` 覆盖连接测试与启动超时不阻塞。

- 2026-01-10 GuessIt 并发解析崩溃修复（rebulk list.remove）：
  - 问题：Worker 并发解析时，GuessIt/Rebulk 偶发触发 `ValueError: list.remove(x): x not in list`，日志提示 `Please report at https://github.com/guessit-io/guessit/issues.`，并出现“解析失败”噪声。
  - 复现：对同一字符串进行多线程高并发解析时可稳定复现；且不依赖自定义 options.json（说明根因不是配置语法冲突）。
  - 解决：`MediaParser` 改为线程内复用独立的 `GuessItApi` 实例（thread-local），避免跨线程共享内部状态；并在单次失败时使用全新 `GuessItApi` 重试一次，进一步降低偶发失败概率。
  - 配置：`options.json` 补充 `expected_title` 里的 `牧神记`，提升该标题的解析稳定性。
  - 测试：新增并发回归测试；后端 `pytest`（29 通过）与前端 `flutter analyze` 均通过。

- 2026-01-10 修复质量目录污染标题（4K SDR 被误判为 title）：
  - 问题：如 `/电视剧/华语/大生意人（2025）/4K SDR/` 这类目录结构中，解析器会把 `4K SDR` 当作 title_hint，导致组级聚合标题错误、元数据搜索失败。
  - 解决：增强 `_is_ignorable_segment()`，对目录分词后全部命中技术词集合（如 `4K SDR`）的分段直接忽略，继续向上回溯到真实剧名目录；并在 `options.json` 的 `common_words` 补充 `4K/4k/UHD/uhd` 降低技术词干扰。
  - 文档：更新 `media-server/utils/name_parser.md` 补充该类失败样例与修复策略。
  - 测试：新增回归用例覆盖 `大生意人（2025）/4K SDR/03 4K.mkv`；后端 `pytest`（30 通过）与前端 `flutter analyze` 均通过。

- 2026-01-10 修复方括号标签污染剧名（入青云被误判为帧率版本）：
  - 问题：目录形如 `入青云[60帧率版本][全36集][国语配音+中文字幕]...` 时，`_extract_title_hint()` 按“最长中文片段”抽取会把 `帧率版本` 当作 title_hint，导致组级聚合标题错误、元数据搜索失败。
  - 解决：在 `_extract_title_hint()` 中新增“方括号/书名号标签剥离”规则，遇到 `[`/`【` 时优先取第一个括号前的头部片段作为剧名候选；并在 `options.json` `common_words` 补充 `帧率版本/60帧率版本/国语配音/中文字幕/60fps` 等标签词。
  - 文档：更新 `media-server/utils/name_parser.md` 增补失败样例与修复策略。
  - 测试：新增回归用例覆盖 `入青云[60帧率版本].../Love.in.the.Clouds.S01E03...mkv`；后端 `pytest` 通过。

- 2026-01-10 修复站点宣传词污染剧名（掌心被误判为地址发布页）：
  - 问题：目录形如 `掌心.2160p.60fps.电影港 地址发布页 www.dygang.me 收藏不迷路/` 时，`_extract_title_hint()` 会把 `地址发布页` 当作 title_hint，导致组级聚合标题错误、元数据搜索失败。
  - 解决：在 `_extract_title_hint()` 中增加“点分隔技术段剥离”规则，命中 `2160p/fps` 或宣传词时优先取第一个点前的头部片段作为剧名候选；并在 `options.json` `common_words` 补充 `电影港/地址发布页/收藏不迷路/fps`。
  - 文档：更新 `media-server/utils/name_parser.md` 增补失败样例与修复策略。
  - 测试：新增回归用例覆盖 `掌心.2160p.60fps.../掌心.S01E01...mkv`；后端 `pytest` 通过。

- 2026-01-12 扫描结果增加 all_file_ids（本次扫描命中的全部文件ID）：
  - 需求：扫描结果除 `new_file_ids` 外，额外返回 `all_file_ids`，用于后续任务链做“全量候选文件”处理。
  - 实现：`ScanResult` 新增 `all_file_ids` 字段；在处理器批量入库结果汇总阶段，累计新建/更新/未变化的 `file_id` 去重写入。
  - 测试：扩展 `tests/test_scan_routes.py` 增加单测覆盖 `all_file_ids` 聚合逻辑；后端 `pytest` 通过。

- 2026-01-12 生产环境 Docker 容器资源限制优化：
  - 需求：针对 2 Core 2G RAM 的目标服务器，限制容器资源使用，防止内存爆炸（OOM）。
  - 实现：在 `docker-compose.prod.yml` 中为 `postgres` (512M)、`redis_queue` (128M)、`api` (384M)、`worker` (512M) 和 `caddy` (128M) 配置了 `deploy.resources.limits` 和 `reservations`。
  - 策略：总预留 CPU 约 0.4 Cores，总限制 CPU 1.9 Cores；总预留内存约 0.6G，总限制内存约 1.6G，预留约 400M 给宿主机操作系统。

- 2026-01-11 修复手动匹配后详情页出现旧版本空数据：
  - 问题：手动匹配后文件已指向新 `MediaVersion.id`，但旧版本记录仍保留，详情页返回旧版本但无 assets。
  - 解决：在元数据持久化完成后，检测 `FileAsset.version_id/season_version_id` 是否发生变更；若旧版本已无任何文件引用，则自动删除旧版本（含 season_group 下无引用的子版本）。
  - 测试：新增 `test_metadata_persistence_cleanup_versions.py` 覆盖旧版本与旧季版本清理逻辑；后端 `pytest` 通过。
