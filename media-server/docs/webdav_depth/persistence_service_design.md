# 可扩展低耦合的持久化服务设计

## 现状
- 单体持久化服务集中处理电影/剧集映射：`_apply_movie_detail`（`services/media/metadata_persistence_service.py:342`）、`_apply_search_result`（`services/media/metadata_persistence_service.py:625`）。

## 目标
- 以策略模式实现类型无关的持久化映射，允许按 `media_type/sub_kind/provider` 动态扩展；幂等一次性应用。

## 设计
- 接口：`PersistenceStrategy.apply(session, media_file, scraped)`。
- 注册中心：`StrategyRegistry.register(media_type, sub_kind?, provider?, strategy)`；默认策略覆盖电影/剧集/季/集。
- 通用映射：`MediaCore` 基础字段、`ExternalID`、`Artwork`、`Credit`、`Genre`；
- 类型映射：
  - 电影：`MovieExt` 字段（tagline/collection/rating/release_date/runtime...）。
  - 剧集系列：`SeriesExt` 字段（status/season_count/episode_count/episode_run_time...）。
  - 季：`SeasonExt`（season_number/episode_count/...）。
  - 集：`EpisodeExt`（episode_number/season_number/runtime/episode_type/absolute_episode_number...）。
- 版本绑定：保留单独方法 `bind_version(session, media_file, parse_out)`；与 `apply` 解耦。
- 幂等策略：以 `(user_id, core_id)` 定位更新；外部 ID 以 `(user_id, core_id, source)` 唯一，避免重复记录；
- 回退：当仅有搜索项 `ScraperSearchResult`，先建 `MediaCore`，后续详情补全。

## 扩展到综艺/动画
- 不新增专用表，沿用季/集结构；当 `sub_kind` 为 `variety/anime` 时，额外填充 `absolute_episode_number/episode_type`。

## 验收
- 新增类型仅需注册策略；原有电影/剧集逻辑保持不变；事务一次性提交，失败滚回。

## 参考定位
- 持久化入口与映射：`services/media/metadata_persistence_service.py:342, 625`
- 数据模型：`models/media_models.py:46, 158, 186, 205`

