## 目标与范围
- 替换并精简 `services/media/media_service.py`，实现媒体库首页卡片列表、条件筛选、影片详情三大能力。
- 修改 `api/routes_media.py` 提供 REST API：卡片分页查询（含总数量）、多条件筛选、按 id 查询详情。

## 数据来源与模型映射
- 主要表/模型：`MediaCore`（kind/title/year/plot）、`MovieExt`、`TVSeriesExt/SeasonExt/EpisodeExt`、`Artwork`（poster/backdrop）、`Genre/MediaCoreGenre`、`Credit/Person`、`FileAsset`（路径/版本）。
- 统一封面选取策略：优先选 `Artwork(type=poster)` 的 `preferred=True` 或存在本地路径；否则回退 `backdrop`；最终回退搜索到的 `remote_url`。
- 评分/发布时间：使用 `MovieExt.rating` 或 `EpisodeExt.rating`（若存在）；发布时间 `MovieExt.release_date` 或 `EpisodeExt.aired_date`/`SeasonExt.aired_date`。

## 服务层接口（media_service.py）
- 新建/重构 `MediaService` 类：
  - `list_media_cards(page: int, page_size: int, filters: MediaFilters) -> MediaCardsResponse`
    - 返回：`items: List[MediaCard]`（id、name、rating、release_date、cover_url、media_type）、`total_count: int`、`type_counts: Dict[str,int]`（电影/剧集总数量）。
    - 排序：默认按发布时间/更新日期倒序。
  - `get_media_detail(core_id: int) -> MediaDetail`
    - 电影：名称、背景/海报、评分/时长、类型/地区/语言、主文件路径、演员表（cast/crew）、简介、版本列表（MediaVersion）。
    - 剧集：系列信息（series）、季/集概要（如该集或该季）、封面/背景、评分/类型/地区/语言、主文件/集文件路径、演员表、简介、版本列表。
  - `get_type_counts(filters: MediaFilters) -> Dict[str,int>`（可选，若不与列表共返回）。
- 过滤参数结构 `MediaFilters`：
  - `type: Optional[str]`（movie/tv/variety/documentary/animation）
  - `genres: Optional[List[str]]`
  - `year: Optional[int] | year_range: Optional[Tuple[int,int]]`
  - `countries: Optional[List[str]]`
  - `q: Optional[str]`（标题关键字）
  - 组合条件为 AND 交集；多值为 IN。
- 查询实现：
  - 基于 `SQLModel.select` + 条件拼接；`JOIN Artwork/Genre/MediaCoreGenre/Credit` 按需选择。
  - 计数与分页：`count()` 与 `limit/offset`；避免 N+1，适度 `JOIN` 或二次查询。

## API 路由（routes_media.py）
- 新增/修改：
  - `GET /media/cards?page=&page_size=&type=&genres=&countries=&year=&q=` → `MediaCardsResponse`
  - `GET /media/{id}/detail` → `MediaDetail`
  - 可选：`GET /media/counts?type=` → `{movie: X, tv: Y}` 或合并在卡片响应中。
- 请求/响应模型（Pydantic）：
  - `MediaFiltersModel`（解析 query）
  - `MediaCardModel`（id/name/rating/release_date/cover_url/media_type）
  - `MediaCardsResponseModel`（items/total_count/type_counts）
  - `MediaDetailModel`（分电影/剧集数据结构，含 artworks、credits、versions、paths 等）
- 错误处理：
  - 404 当 `core_id` 未找到；400 参数非法；500 内部错误统一。

## 逻辑要点
- 类型映射：`MediaCore.kind` → movie/tv_series/tv_season/tv_episode；卡片列表只展示 movie 与 tv（系列或单集按业务选择：推荐以系列为单位）。
- 评分与发布时间：优先从扩展表读取；缺失时尝试回退。
- 路径返回：电影返回主文件路径；剧集返回系列/季/集对应文件路径（若存在）。
- 安全与性能：
  - 防止长 JOIN：卡片列表字段尽量从主表/简单 JOIN 获取；详情再做完整 JOIN。
  - 对大数据集分页查询添加索引建议（title/year/updated_at）。

## 交付步骤
1. 重构 `media_service.py`：移除旧方法，添加服务类与数据模型（内部 dataclass/Pydantic）。
2. 修改 `routes_media.py`：引入服务实例，新增卡片与详情路由，解析 filters 与分页，返回标准响应。
3. 简单验证：本地运行，查询卡片列表与详情；若项目有测试框架，添加基本路由测试用例。

## 验收
- 能通过筛选条件分页返回卡片，含总数与电影/剧集数量。
- 能按 id 返回完整详情（电影或剧集），包含海报/背景/评分/类型/地区/路径/演员表/简介/版本。
- 路由参数健壮，错误返回合理。