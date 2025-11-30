## 审核结论
- base.py：公共接口大多被管理器加载/配置所需；默认 `get_artworks/get_credits/configure/test_connection/startup/shutdown/get_config_schema` 被现有流程或管理器引用，保留。
- manager.py：`get_available_plugins/auto_discover_plugins/enrich_with_best_match/startup/shutdown` 在测试和可能的API层使用，保留；不做删除。
- tmdb.py：存在两个明确的可清理点：
  - 预刮削残留：`get_episode_details` 内对 `TmdbPreScraper` 的导入与骨架处理（lines ~323-337）在预刮削模块已删除后应移除。
  - 统计方法：`get_stats()` 未被外部引用，可删除。

## 计划变更
- 删除 `services/scraper/tmdb.py` 中 `get_episode_details` 的预刮削骨架检查逻辑块（`from .tmdb_pre_scraper import TmdbPreScraper` 与其调用段）。
- 删除 `services/scraper/tmdb.py` 中未用的 `get_stats()`。
- 清理相关未使用导入（如仅用于预刮削逻辑的引用）。
- 不改动 `base.py` 和 `manager.py` 的方法集合，以免破坏现有测试与外层接口。

## 验证
- 运行现有测试套：缓存命中、回退路径、系列概览、分层持久化与幂等测试；确保无引用破坏。

## 影响
- 对外行为不变；去除死代码与失效路径，减少维护成本。