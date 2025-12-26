# 进度记录

## 2025-12-23
- 刮削插件：修复 `ScraperPlugin.get_details` 的 `MediaType` 分发，并支持 `TV_SERIES/TV_SEASON/TV_EPISODE`
- 刮削插件：在 `ScraperManager` 增加 `get_detail`（超时隔离 + 详情缓存 + episode 补齐并发化）
- 刮削插件：将缓存升级为有界 TTL（可选 Redis），仅缓存电影/系列/季
- 刮削插件：增加 Redis 分布式 singleflight，防止跨进程缓存击穿
- 基础设施：新增独立 `redis_cache` 实例供刮削缓存使用，避免影响任务队列 Redis
- 媒体服务：将存储信息缓存改为使用 `redis_cache`（DB=1），避免与队列 Redis 共享
- 丰富化：将 `metadata_enricher.py` 中详情获取逻辑下放到 `scraper_manager.get_detail`
- 测试：新增 `tests/test_scraper_manager_detail.py` 覆盖分发、缓存与超时降级
## 2025-12-24
- 丰富化：`metadata_enricher.enrich_multiple_files` 按父目录分组处理，同组文件共享一次搜索
- 丰富化：新增 `enrich_media_files`，剧集只拉取系列+季详情，单集由季 episodes 映射
- 刮削插件：在 `ScraperManager` 增加 `get_series_details_cached` / `get_season_details_cached` 复用缓存
- 测试：复用新缓存接口保持 `test_scraper_manager_detail` 通过，pytest 全量通过
- 丰富化：批处理中文件夹内电影始终逐个刮削，避免多电影混放误共享详情；剧集仍按父目录聚合解析与刮削
- 丰富化：新增 `iter_enrich_multiple_files` 流式接口，调用方可按异步迭代逐条消费元数据结果
- 任务队列：`metadata_worker` 使用流式接口逐条创建持久化与本地化任务，避免一次性持有全部丰富化结果，为未来批量持久化预留聚合扩展点
- 持久化：新增 `MetadataPersistenceService.apply_metadata_batch_async` 支持异步批量持久化调用
- 任务队列：新增 `create_persist_batch_task` 与 `persist_batch_worker`，用于聚合多文件持久化任务
- 测试：扩展 `tests/test_metadata_worker_batching.py` 覆盖元数据流式消费与批量持久化任务，pytest 全量通过
- 媒体服务：修复 `MediaService.get_media_detail` 中 `directors` / `writers` 异步化后未 await 导致的响应验证错误
- 媒体接口：更新 `/api/media/{id}/detail`，当核心记录不存在或剧集详情返回 `error` 时，返回 404 而不是 FastAPI `ResponseValidationError`
