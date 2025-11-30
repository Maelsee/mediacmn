# 数据库设计评估与扩展方案

## 现状评估
- 核心：`MediaCore(kind=movie|tv_series|tv_season|tv_episode)`（`models/media_models.py:46`）。
- 扩展：电影 `MovieExt`、剧集 `TVSeriesExt/SeasonExt/EpisodeExt`；`EpisodeExt` 已包含 `episode_type` 并注释了 `absolute_episode_number`（`models/media_models.py:205, 218`）。
- 关联与唯一：`EpisodeExt` 唯一约束（`series_core_id, season_number, episode_number`）`models/media_models.py:189-191`；`ExternalID` 唯一 `(user_id, core_id, source)` `models/media_models.py:291-292`。

## 扩展建议
- 新增 `MediaCore.sub_kind` 字段用于细分：`variety/anime/documentary/music/short/special`，不破坏现有 `kind`；便于前端展示与策略分派。
- 启用 `absolute_episode_number` 并建立索引，以支持番剧/国产剧的绝对集序与并行季集。
- `TVSeriesExt` 增加可选 `category_hint`，用于聚合与筛选；如不改表，可用 `group_key/canonical_source` 进行归类（`models/media_models.py:58-62`）。
- 继续使用现有季/集结构承载综艺/动画，避免碎片化表设计；如确有强差异字段（嘉宾列表等），再考虑增设扩展表与 `MediaCore` 关联。

## 索引与规范化
- 组合索引：`MediaCore(kind, sub_kind, year)`，提高查询性能。
- 绝对集序：`EpisodeExt(absolute_episode_number)` 非唯一索引，支持跨季检索。

## 迁移策略
- 向后兼容数据迁移脚本：新增列默认 `NULL`；逐步填充 `sub_kind` 与 `absolute_episode_number`；无破坏性。

## 验收
- 不修改核心关系结构即可支持综艺/动画等类型持久化；查询性能稳定，写入幂等。

## 参考定位
- `models/media_models.py:46, 145, 158, 186, 205`

