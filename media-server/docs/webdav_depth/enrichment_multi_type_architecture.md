# 多类型可扩展的丰富化架构

## 类型扩展
- `MediaType` 扩展覆盖：电影、剧集、季、集、综艺、动画、纪录片、特别篇、短片。
- 解析器支持综艺/动画术语：期/话/特别篇；填充 `season_number/episode_number/absolute_episode_number/episode_type`。

## 插件接口规范
- 基础：`search(title, year?, media_type, language)`；管理器做类型校正与语言回退。
- 详情统一：`get_work_details(id, media_type, language)`；剧集型另行：`get_season_details(id, season, language)`、`get_episode_details(id, season, episode, language)`。
- 能力声明：`capabilities = {batch_series, batch_season, hierarchical_cache, supports_variety, supports_anime}`。

## 管理器策略
- 能力与健康选择：根据 `media_type` 与 `capabilities` 选择插件；健康不佳时 fallback。
- 语言回退链：`zh-CN → en-US → 原生`。

## 丰富化流程（单文件内核）
- 解析 → 类型校正 → 搜索 → 详情（剧集优先季缓存）→ 持久化映射 → 版本绑定 → 侧车入队。
- 保持 `metadata_enricher.enrich_media_file` 的单文件幂等逻辑（`services/media/metadata_enricher.py:34`）。

## 数据契约（ScraperResult 扩展）
- 核心：标题/原名/年份/日期/时长/剧情/标语/评分/票数。
- 分类：流派/国家/语言/关键词/状态。
- 标识：`provider/provider_id/provider_url/external_ids[]`。
- 层级：`series/seasons[]/episodes[]`；`episode_type` 与 `absolute_episode_number` 支持综艺/动画特殊性。

## 持久化策略
- 策略化分派到 `movie/tv_series/tv_season/tv_episode`；综艺/动画沿用剧集模型，按 `sub_kind` 决定是否映射绝对集序等附加字段。

## 验收
- 新增综艺/动画无需改数据库与核心引擎，仅在策略注册与解析映射处扩展。

## 参考定位
- 丰富化入口：`services/media/metadata_enricher.py:34`
- 插件管理器：`services/scraper/manager.py`
- 持久化映射：`services/media/metadata_persistence_service.py:342, 625`
- 数据模型：`models/media_models.py:46, 205`

