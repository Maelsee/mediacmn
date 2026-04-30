
"""
弹幕数据模型

定义弹幕相关的请求和响应数据模型。
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field


# ==================== 枚举类型 ====================

class DanmuType(str, Enum):
    """弹幕类型"""
    SCROLL = "scroll"      # 滚动弹幕
    TOP = "top"            # 顶部弹幕
    BOTTOM = "bottom"      # 底部弹幕


class SearchType(str, Enum):
    """搜索类型"""
    ANIME = "anime"        # 动漫
    EPISODES = "episodes"  # 剧集


class DanmuLoadMode(str, Enum):
    """弹幕加载模式"""
    FULL = "full"          # 全量
    SEGMENT = "segment"    # 分段

class DanmuFormat(str, Enum):
    """弹幕数据格式"""
    JSON = "json"          # JSON 格式
    XML = "xml"            # XML 格式

# ==================== 弹幕数据模型 ====================


class NextSegmentInput(BaseModel):
    type: str
    segment_start: int
    segment_end: int
    url: str


# class DanmuComment(BaseModel):
#     """单条弹幕"""
#     id: str = Field(..., description="弹幕唯一标识")
#     time: int = Field(..., description="出现时间(毫秒)")
#     content: str = Field(..., description="弹幕内容")
#     color: str = Field(default="#FFFFFF", description="弹幕颜色")
#     type: DanmuType = Field(default=DanmuType.SCROLL, description="弹幕类型")
#     font_size: float = Field(default=1.0, description="字体大小比例")
#     source: Optional[str] = Field(default=None, description="来源平台")


class DanmuData(BaseModel):
    """弹幕数据"""
    episode_id: int = Field(..., description="剧集ID")
    count: int = Field(default=0, description="弹幕数量")
    comments: List[Dict[str, Any]] = Field(default_factory=list, description="弹幕列表")
    offset: float = Field(default=0.0, description="时间偏移量")
    video_duration: int = Field(default=0, description="视频时长(秒)")
    load_mode: DanmuLoadMode = Field(default=DanmuLoadMode.FULL, description="加载模式")
    segment_list: List[Dict[str, Any]] = Field(default_factory=list, description="分片描述列表")
    binding: Optional["BindingInfo"] = Field(default=None, description="自动创建的绑定信息（首次获取弹幕时返回）")
# class DanmuData(BaseModel):
#     """弹幕数据"""
#     episode_id: int = Field(..., description="剧集ID")
#     count: int = Field(default=0, description="弹幕数量")
#     comments: List[Dict[str, Any]] = Field(default_factory=list, description="弹幕列表")
#     offset: float = Field(default=0.0, description="时间偏移量")
#     video_duration: int = Field(default=0, description="视频时长(秒)")
#     load_mode: DanmuLoadMode = Field(default=DanmuLoadMode.FULL, description="加载模式")
#     segment_list: List[Dict[str, Any]] = Field(default_factory=list, description="分片描述列表")

# ==================== 匹配相关模型 ====================

class DanmuSource(BaseModel):
    """弹幕源"""
    episodeId: int = Field(..., description="剧集ID")
    animeId: int = Field(default="", description="番剧ID")
    animeTitle: str = Field(default="", description="番剧标题")
    episodeTitle: str = Field(default="", description="剧集标题")
    type: str = Field(default="", description="类型")
    typeDescription: str = Field(default="", description="类型描述")
    shift: float = Field(default=0, description="时间偏移量")
    imageUrl: str = Field(default="", description="封面图URL")

class AutoMatchRequest(BaseModel):
    """自动匹配请求

    两种调用方式：
    1. 直接传 title（可选 season/episode）
    2. 传 file_id，后端自动从数据库解析 title/season/episode
    """
    title: Optional[str] = Field(default=None, description="视频标题（与 file_id 二选一）")
    season: Optional[int] = Field(default=None, description="季数")
    episode: Optional[int] = Field(default=None, description="集数")
    file_id: Optional[str] = Field(default=None, description="文件ID（与 title 二选一）")


class AutoMatchResponse(BaseModel):
    """自动匹配响应"""
    is_matched: bool = Field(default=False, description="是否匹配成功")
    confidence: float = Field(default=0.0, description="匹配置信度")
    sources: List[DanmuSource] = Field(default_factory=list, description="匹配结果列表")
    best_match: Optional[DanmuSource] = Field(default=None, description="最佳匹配")
    binding: Optional["BindingInfo"] = Field(default=None, description="自动绑定信息（高置信度时返回）")
    danmu_data: Optional["DanmuData"] = Field(default=None, description="弹幕数据（高置信度自动绑定时返回）")


# ==================== 搜索相关模型 ====================

class SearchRequest(BaseModel):
    """搜索请求"""
    keyword: str = Field(..., description="搜索关键词")
    type: SearchType = Field(default=SearchType.ANIME, description="搜索类型")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量限制")


class SearchAnimeItem(BaseModel):
    """动漫搜索结果项 — 对应 danmu_api /api/v2/search/anime 返回的 animes 数组元素"""
    animeId: int = Field(..., description="番剧ID")
    bangumiId: Optional[str] = Field(default=None, description="番剧ID(字符串)")
    animeTitle: str = Field(..., description="番剧标题")
    type: Optional[str] = Field(default=None, description="类型(动漫/电视剧/综艺等)")
    typeDescription: Optional[str] = Field(default=None, description="类型描述")
    imageUrl: Optional[str] = Field(default=None, description="封面图URL")
    startDate: Optional[str] = Field(default=None, description="开播日期")
    episodeCount: Optional[int] = Field(default=None, description="总集数")
    rating: Optional[float] = Field(default=None, description="评分")
    isFavorited: Optional[bool] = Field(default=None, description="是否收藏")
    source: Optional[str] = Field(default=None, description="来源平台")


class SearchEpisodeItem(BaseModel):
    """剧集搜索结果项"""
    episode_id: str = Field(..., description="剧集ID")
    anime_id: Optional[str] = Field(default=None, description="番剧ID")
    anime_title: Optional[str] = Field(default=None, description="番剧标题")
    episode_title: Optional[str] = Field(default=None, description="剧集标题")
    episode_number: Optional[int] = Field(default=None, description="集数")
    platform: Optional[str] = Field(default=None, description="平台")


class SearchResponse(BaseModel):
    """搜索响应"""
    keyword: str = Field(..., description="搜索关键词")
    type: SearchType = Field(..., description="搜索类型")
    items: List[Any] = Field(default_factory=list, description="搜索结果")
    has_more: bool = Field(default=False, description="是否有更多结果")


# ==================== 番剧详情相关模型 ====================

class BangumiSeason(BaseModel):
    """番剧季信息"""
    id: str = Field(..., description="季ID (如 season-333038)")
    airDate: Optional[str] = Field(default=None, description="播出日期")
    name: str = Field(default="", description="季名称")
    episodeCount: Optional[int] = Field(default=None, description="该季集数")


class BangumiEpisode(BaseModel):
    """番剧剧集信息 — 对应 danmu_api /api/v2/bangumi/:animeId 返回的 episodes 数组元素"""
    seasonId: str = Field(default="", description="所属季ID")
    episodeId: int = Field(..., description="剧集ID (用于获取弹幕)")
    episodeTitle: str = Field(default="", description="剧集标题")
    episodeNumber: str = Field(default="", description="集数编号")
    airDate: Optional[str] = Field(default=None, description="播出日期")


class BangumiDetail(BaseModel):
    """番剧详情 — 对应 danmu_api /api/v2/bangumi/:animeId 返回的 bangumi 对象"""
    animeId: int = Field(..., description="番剧ID")
    bangumiId: Optional[str] = Field(default=None, description="番剧ID(字符串)")
    animeTitle: str = Field(default="", description="番剧标题")
    imageUrl: Optional[str] = Field(default=None, description="封面图URL")
    isOnAir: Optional[bool] = Field(default=None, description="是否在播")
    airDay: Optional[int] = Field(default=None, description="每周几更新")
    isFavorited: Optional[bool] = Field(default=None, description="是否收藏")
    rating: Optional[float] = Field(default=None, description="评分")
    type: Optional[str] = Field(default=None, description="类型")
    typeDescription: Optional[str] = Field(default=None, description="类型描述")
    seasons: List[BangumiSeason] = Field(default_factory=list, description="季列表")
    episodes: List[BangumiEpisode] = Field(default_factory=list, description="剧集列表")


class BangumiDetailResponse(BaseModel):
    """番剧详情响应"""
    animeId: int = Field(..., description="番剧ID")
    animeTitle: str = Field(default="", description="番剧标题")
    type: Optional[str] = Field(default=None, description="类型")
    typeDescription: Optional[str] = Field(default=None, description="类型描述")
    imageUrl: Optional[str] = Field(default=None, description="封面图URL")
    episodeCount: Optional[int] = Field(default=None, description="总集数")
    seasons: List[BangumiSeason] = Field(default_factory=list, description="季列表")
    episodes: List[BangumiEpisode] = Field(default_factory=list, description="剧集列表")


# ==================== 绑定相关模型 ====================

class BindRequest(BaseModel):
    """绑定请求"""
    file_id: str = Field(..., description="文件ID")
    episode_id: str = Field(..., description="剧集ID")
    anime_id: Optional[str] = Field(default=None, description="番剧ID")
    anime_title: Optional[str] = Field(default=None, description="番剧标题")
    episode_title: Optional[str] = Field(default=None, description="剧集标题")
    platform: Optional[str] = Field(default=None, description="弹幕平台")
    offset: float = Field(default=0.0, description="时间偏移量(秒)")


class BindResponse(BaseModel):
    """绑定响应"""
    id: int = Field(..., description="绑定ID")
    file_id: str = Field(..., description="文件ID")
    episode_id: str = Field(..., description="剧集ID")
    anime_id: Optional[str] = Field(default=None, description="番剧ID")
    anime_title: Optional[str] = Field(default=None, description="番剧标题")
    episode_title: Optional[str] = Field(default=None, description="剧集标题")
    platform: Optional[str] = Field(default=None, description="弹幕平台")
    offset: float = Field(default=0.0, description="时间偏移量")
    is_manual: bool = Field(default=False, description="是否手动绑定")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    updated_at: Optional[str] = Field(default=None, description="更新时间")


class UpdateOffsetRequest(BaseModel):
    """更新偏移量请求"""
    offset: float = Field(..., description="新的时间偏移量(秒)")


class BindingInfo(BaseModel):
    """绑定信息"""
    id: int
    file_id: str
    episode_id: str
    anime_id: Optional[str] = None
    anime_title: Optional[str] = None
    episode_title: Optional[str] = None
    type: Optional[str] = None
    typeDescription: Optional[str] = None
    imageUrl: Optional[str] = None
    offset: float = 0.0
    is_manual: bool = False
    match_confidence: Optional[float] = None
    # created_at: Optional[str] = None
    # updated_at: Optional[str] = None


# ==================== 平台相关模型 ====================

class PlatformInfo(BaseModel):
    """平台信息"""
    id: str = Field(..., description="平台ID")
    name: str = Field(..., description="平台名称")
    enabled: bool = Field(default=True, description="是否启用")


class PlatformStatus(BaseModel):
    """平台状态"""
    platform: str = Field(..., description="平台ID")
    available: bool = Field(..., description="是否可用")
    latency: Optional[int] = Field(default=None, description="延迟(ms)")
    error: Optional[str] = Field(default=None, description="错误信息")


# ==================== 弹幕获取相关模型 ====================

class DanmuSegmentRequest(BaseModel):
    """分段获取弹幕请求"""
    from_time: int = Field(default=0, ge=0, description="开始时间(秒)")
    to_time: int = Field(default=300, ge=0, description="结束时间(秒)")


class DanmuByFileRequest(BaseModel):
    """按文件获取弹幕请求"""
    file_id: str = Field(..., description="文件ID")
    from_time: Optional[int] = Field(default=None, description="开始时间(秒)")
    to_time: Optional[int] = Field(default=None, description="结束时间(秒)")


class MergeDanmuRequest(BaseModel):
    """合并弹幕请求"""
    episode_ids: List[str] = Field(..., description="剧集ID列表")
    from_time: Optional[int] = Field(default=None, description="开始时间(秒)")
    to_time: Optional[int] = Field(default=None, description="结束时间(秒)")


class MergeDanmuResponse(BaseModel):
    """合并弹幕响应"""
    count: int = Field(default=0, description="弹幕总数")
    comments: List[Dict[str, Any]] = Field(default_factory=list, description="弹幕列表")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="来源信息")


# ==================== 通用响应模型 ====================

class ErrorResponse(BaseModel):
    """错误响应"""
    code: int = Field(default=500, description="错误码")
    message: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(default=None, description="详细信息")


class SuccessResponse(BaseModel):
    """成功响应"""
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Optional[Any] = Field(default=None, description="数据")
