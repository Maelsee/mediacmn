# 进度记录

## 2025-12-23
- 刮削插件：修复 `ScraperPlugin.get_details` 的 `MediaType` 分发，并支持 `TV_SERIES/TV_SEASON/TV_EPISODE`
- 刮削插件：在 `ScraperManager` 增加 `get_detail`（超时隔离 + 详情缓存 + episode 补齐并发化）
- 刮削插件：将缓存升级为有界 TTL（可选 Redis），仅缓存电影/系列/季
- 刮削插件：增加 Redis 分布式 singleflight，防止跨进程缓存击穿
- 基础设施：新增独立 `redis_cache` 实例供刮削缓存使用，避免影响任务队列 Redis
- 丰富化：将 `metadata_enricher.py` 中详情获取逻辑下放到 `scraper_manager.get_detail`
- 测试：新增 `tests/test_scraper_manager_detail.py` 覆盖分发、缓存与超时降级
