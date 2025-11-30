## 目标

* 直接覆盖 `ScraperResult` 与插件公共接口，引入剧集分层数据、批量与缓存能力；保持架构扩展性与低耦合。

## 新契约（覆盖式）

* `ScraperResult`（覆盖现有 `services/scraper/base.py:76-138`）：

  * 基本：`title, original_title, year, release_date, runtime, overview, tagline, rating, vote_count, genres, countries, languages`

  * 标识：`provider, provider_id, provider_url, external_ids[{provider, external_id, url}]`

  * 艺术：`artworks[{type, url, width?, height?, language?, rating?, vote_count?}]`

  * 电影合集：`collection={id,name,poster_path?,backdrop_path?,overview?}`

  * 剧集分层：

    * `series={id?, title, overview?, season_count?, episode_count?}`

    * `seasons=[{season_number, overview?, aired_date?, runtime?, rating?, episode_count?, artworks?}]`

    * `episodes=[{season_number, episode_number, title, overview?, aired_date?, runtime?, rating?, vote_count?, still_path?, artworks?, credits?}]`

  * 原始：`raw_data`

## 插件公共接口（覆盖式）

* `ScraperPlugin` 增加：

  * `capabilities={batch_series: bool, batch_season: bool, hierarchical_cache: bool}`

  * `async def get_season_details(series_id: str, season_number: int, language: str) -> ScraperResult`（填充 `episodes`）

  * `async def get_series_details_many(series_ids: List[str], language: str) -> Dict[str, ScraperResult]`（可选能力）

  * `async def get_season_details_many(reqs: List[Tuple[str,int]], language: str) -> Dict[Tuple[str,int], ScraperResult]`（可选能力）

  * 保留：`search(...)`, `get_details(...)`, `get_credits(...)` 更新为返回新契约结构

## TMDB 插件实现要点

* 位置：`services/scraper/tmdb.py`

* 分层复用：

  * 新增 `_get_season_detail(series_id, season_number, language)`：直接使用 `/tv/{id}/season/{season}`，构造 `episodes` 列表（含 `title/overview/runtime/rating/vote_count/still_path`）。

  * 更新 `get_episode_details(...)`：优先命中 `season_cache[(series_id, season_number, lang)]` 提取该集；缺失演职员时仅调用 `credits` 端点补齐。

  * `get_details(...)` 对 `TV_SERIES` 返回 `series` 与 `seasons` 概览；对 `MOVIE` 不变（但返回覆盖后的字段）。

* 批量能力（插件私有/可选）：

  * `_batch_get_series_details(series_ids, language)` 并发受控拉取，结果写入 `series_cache`。

  * `_batch_get_season_details(requests, language)` 并发受控拉取，结果写入 `season_cache`。

* 缓存：

  * `series_cache[(series_id, lang)]`，`season_cache[(series_id, season_number, lang)]`，`episode_cache[(series_id, season_number, episode_number, lang)]`；TTL：`series/season=24h`，`episode=7d`。

* 会话与限流：复用共享 `ClientSession`；在季/剧集批量方法中使用 `asyncio.Semaphore` 控制并发。

## 管理器与编排

* `ScraperManager`（`services/scraper/manager.py`）保持现有搜索逻辑；如检测到插件 `capabilities.batch_*`，在批量任务路径（未来）优先调用批量接口；普通路径不变。

* 策略搜索 `search_media_with_policy(...)` 无需变更（已在管理器中实现）。

## 持久化映射

* `MetadataPersistenceService.apply_metadata(...)`（`services/media/metadata_persistence_service.py:1`）适配新契约：

  * 电影：从顶层字段映射到 `MovieExt/Collection`（已有逻辑保持）。

  * 剧集：

    * 从 `series` 建立/更新 `TVSeriesExt`

    * 从 `seasons[]` 建立/更新 `SeasonExt`

    * 从 `episodes[]` 建立/更新 `EpisodeExt`（含 `still_path/rating/vote_count`）与 `Credit/Artwork`

## 可行性与耦合性

* 可行性：高；TMDB季端点数据充分，分层复用能显著减少调用。

* 耦合性：低；覆盖式更新集中在 `base.py` 与 TMDB 插件内部；管理器与业务层调用路径保持不变（返回更丰富结构）。

## 风险与回退

* 风险：已有测试需同步更新；部分地区季端点字段缺失时需按需回退单集详情。

* 回退：保留单集端点调用，按需补齐；缓存 TTL 控制与手动清理；资源在 `shutdown()` 正常关闭。

## 实施步骤

1. 覆盖 `ScraperResult` 与 `ScraperPlugin` 接口定义（新增分层字段与批量方法/能力字段）。
2. 实现 TMDB 分层与缓存：新增季详情方法，改造 `get_episode_details` 优先季缓存，再按需补齐；实现批量私有方法与缓存。
3. 更新持久化服务适配新契约的剧集分层映射。
4. 同步更新测试用例（`tests/test_scraper_*`）与性能压测脚本。
5. 更新策略文档 `docs/tmdb_刮削器_strategy.md`，记录实现与参数选项。

## 验收标准

* 单集调用次数与时延显著减少（目标≥70%）；批量任务减少≥90%。

* 电影路径一致；剧集分层数据完整入库；资源无泄漏；缓存有效并可清理。

