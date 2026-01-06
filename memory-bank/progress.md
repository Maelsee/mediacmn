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
