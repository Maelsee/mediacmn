"""
媒体相关模型统一文件 - 合并所有媒体相关模型

功能说明：
- 统一管理媒体相关的所有数据模型
- 包含媒体核心、电影扩展、剧集扩展、文件资源、艺术作品、外部ID、流派、人员信用、扫描任务等
- 保持与原有独立模型文件的功能一致性
- 提供统一的导入接口，简化模型管理

模型分类：
1. 媒体核心模型：MediaCore, MediaVersion
2. 电影扩展模型：MovieExt  
3. 剧集扩展模型：SeriesExt, SeasonExt, EpisodeExt
4. 文件资源模型：FileAsset
5. 艺术作品模型：Artwork
6. 外部ID模型：ExternalID
7. 流派模型：Genre, MediaCoreGenre
8. 人员信用模型：Person, Credit


关联关系：
- 所有模型都通过 user_id 关联到 User 模型
- MediaCore 是所有媒体类型的基础，其他模型通过 core_id 关联
- 支持用户隔离，确保不同用户的数据独立
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from utils.time_compat import get_utc_now_factory

from sqlmodel import UniqueConstraint, BigInteger, Column, Field, SQLModel, JSON



# ==================== 媒体核心模型 ====================
class MediaCore(SQLModel, table=True):
    """媒体核心模型 - 所有媒体类型的基础实体"""
    __tablename__ = "media_core"
    __table_args__ = (UniqueConstraint("user_id", "kind", "tmdb_id",name="uix_media_core_user_id_kind_tmdb_id"),)
    

    id: Optional[int] = Field(default=None, primary_key=True, description="媒体核心记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    
    # 基础信息
    kind: str = Field(index=True, description="媒体类型：movie|series|season|episode")
    subtype: Optional[str] = Field(default=None, index=True, description="系类媒体子类型：scripted|reality|animation|documentary|news|talk|other等")
    title: str = Field(index=True, description="标题")
    original_title: Optional[str] = Field(default=None, description="原始标题")
    # origin_country: Optional[List[str]] = Field(default=None, description="原产国家/地区，多个值以列表形式存储")
    year: Optional[int] = Field(default=None, description="年份")
    plot: Optional[str] = Field(default=None, description="剧情简介")

    # 展示层缓存（只读口径，来源于扩展表）
    display_rating: Optional[float] = Field(default=None, description="用于列表展示的评分缓存")
    display_poster_path: Optional[str] = Field(default=None, description="用于列表展示的海报路径缓存")
    display_date: Optional[datetime] = Field(default=None, description="用于列表展示的日期缓存（上映/首播）")
    
    # 分组与规范化
    # group_key: Optional[str] = Field(default=None, index=True, description="分组键，用于媒体分组")
    tmdb_id: Optional[str] = Field(default=None, index=True, description="TMDB ID")
    # canonical_source: Optional[str] = Field(default=None, index=True, description="规范化主来源，如tmdb|douban|tvdb|imdb")
    # canonical_external_key: Optional[str] = Field(default=None, index=True, description="规范化主来源ID值")
    
    
    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now_factory(), description="更新时间")

class MediaVersion(SQLModel, table=True):
    """媒体版本模型 - 新增父版本关联，支持层级管理"""
    __tablename__ = "media_version"
    __table_args__ = (
        UniqueConstraint("user_id", "core_id", "tags", name="uq_media_version"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="版本记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联媒体核心ID")

    # 版本标识
    tags: str = Field(description="版本标签（分辨率,编码,来源,Edition），如：1080p,H.264,DTS,Director's Cut,tmdb")
    quality: Optional[str] = Field(default=None, description="质量:4K|1080p|720p")
    source: Optional[str] = Field(default=None, description="版本来源（tmdb|本地|other）")
    edition: Optional[str] = Field(default=None, description="版本类型（Director's Cut|Theatrical|Standard）")

    # 版本作用域与指纹
    scope: Optional[str] = Field(default=None, description="版本作用域：movie_single|season_group|episode_child")
    variant_fingerprint: Optional[str] = Field(default=None, index=True, description="版本指纹（MD5哈希，用于去重）")
    preferred: bool = Field(default=False, description="是否默认首选版本")
    primary_file_asset_id: Optional[int] = Field(default=None, description="主视频文件ID（仅movie_single/episode_child生效）")

    # 新增：父版本ID（用于episode_child关联到season_group）
    parent_version_id: Optional[int] = Field(default=None, index=True, foreign_key="media_version.id", description="父版本ID（季版本ID）")
    # 新增：季版本路径（用于剧集关联）
    season_version_path: Optional[str] = Field(default=None, description="季版本路径（用于剧集关联）")
    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="版本创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now_factory(), description="版本更新时间")

# ==================== 电影扩展模型 ====================
class MovieExt(SQLModel, table=True):
    """电影扩展模型 - 存储电影特有的扩展字段"""
    __tablename__ = "movie_ext"
    # 唯一约束：同一用户下，电影核心记录唯一
    __table_args__ = (
        UniqueConstraint("user_id", "core_id", name="uq_movie_and_user"),
    )
    id: Optional[int] = Field(default=None, primary_key=True, description="电影扩展记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")
    title: Optional[str] = Field(default=None, description="电影标题")
    overview: Optional[str] = Field(default=None, description="电影简介")
     # 关键修改：List[str] 改为用 JSON 类型存储
    origin_country: Optional[List[str]] = Field(default=None,sa_column=Column(JSON),description="原产国家/地区，多个值以列表形式存储")
    tagline: Optional[str] = Field(default=None, description="标语/宣传语")
    collection_id: Optional[int] = Field(default=None, description="所属电影合集ID")
    rating: Optional[float] = Field(default=None, description="评分")
    release_date: Optional[datetime] = Field(default=None, description="上映日期")
    poster_path: Optional[str] = Field(default=None, description="海报路径")
    backdrop_path: Optional[str] = Field(default=None, description="背景图路径")
    imdb_id: Optional[str] = Field(default=None, description="IMDB ID")
    runtime_minutes: Optional[int] = Field(default=None, description="片长（分钟）")
    raw_data: Optional[str] = Field(default=None, description="原始数据JSON")
    nfo_path: Optional[str] = Field(default=None, description="本地NFO文件路径")
    status: Optional[str] = Field(default=None, description="电影状态")

# ==================== 剧集扩展模型 ====================
class SeriesExt(SQLModel, table=True):
    """剧集系列扩展模型"""
    __tablename__ = "series_ext"
    # 唯一约束：同一用户下，剧集系列核心记录唯一
    __table_args__ = (
        UniqueConstraint("user_id", "core_id", name="uq_series_and_user"),
    )
    

    id: Optional[int] = Field(default=None, primary_key=True, description="剧集系列扩展记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")
    
    title: Optional[str] = Field(default=None, description="系列名称")
    # 系列类型
    series_type: Optional[str] = Field(default=None, description="系列类型：Scripted|Reality|Animation|Documentary|News|Talk|Other等")
    
    # 播出信息
    aired_date: Optional[datetime] = Field(default=None, description="播出日期")
    last_aired_date: Optional[datetime] = Field(default=None, description="最后播出日期")
    
    # 关键修改：List[str] 改为用 JSON 类型存储
    origin_country: Optional[List[str]] = Field(default=None,sa_column=Column(JSON),description="原产国家/地区，多个值以列表形式存储")
    # 统计信息
    episode_count: Optional[int] = Field(default=None, description="总集数")
    season_count: Optional[int] = Field(default=None, description="总季数")
    episode_run_time: Optional[int] = Field(default=None, description="单集时长（分钟）")
    
    # 状态与评分
    status: Optional[str] = Field(default=None, description="播出状态")
    rating: Optional[float] = Field(default=None, description="评分")
    
    # 海报
    poster_path: Optional[str] = Field(default=None, description="海报路径")
    backdrop_path: Optional[str] = Field(default=None, description="背景图路径")
    overview: Optional[str] = Field(default=None, description="系列简介")
    raw_data: Optional[str] = Field(default=None, description="原始数据JSON")
    nfo_path: Optional[str] = Field(default=None, description="本地NFO文件路径")


# ==================== 电影合集模型 ====================
class Collection(SQLModel, table=True):
    """电影合集模型 - 存储电影合集信息"""
    __tablename__ = "collections"
    
    id: int = Field(primary_key=True, description="合集ID（来自TMDB）")
    name: str = Field(description="合集名称")
    poster_path: Optional[str] = Field(default=None, description="海报路径")
    backdrop_path: Optional[str] = Field(default=None, description="背景图路径")
    overview: Optional[str] = Field(default=None, description="合集简介")
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now_factory(), description="更新时间")


class SeasonExt(SQLModel, table=True):
    """季度扩展模型"""
    __tablename__ = "season_ext"
    # 唯一约束：同一用户下，系列+季度序号唯一
    __table_args__ = (
        UniqueConstraint("user_id", "series_core_id", "season_number", name="uq_season_and_user"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="季度扩展记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")

    # 关联到系列
    series_core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的系列核心记录ID")
    
    # 季度信息
    title : Optional[str] = Field(default=None, description="季度名称")
    season_number: int = Field(description="季度序号")
    episode_count: Optional[int] = Field(default=None, description="本季集数")
    
    # 播出信息
    aired_date: Optional[datetime] = Field(default=None, description="播出日期")
    runtime: Optional[int] = Field(default=None, description="本季平均时长（分钟）")
    rating: Optional[float] = Field(default=None, description="本季评分")
    
    # 海报
    poster_path: Optional[str] = Field(default=None, description="海报路径")
    auto_generated: bool = Field(default=False, description="是否系统自动生成的季（无季剧默认季1）")
    overview: Optional[str] = Field(default=None, description="季度简介")
    raw_data: Optional[str] = Field(default=None, description="原始数据JSON")
    nfo_path: Optional[str] = Field(default=None, description="本地NFO文件路径")
    # is_special: bool = Field(default=False, description="是否为特别篇（season0）")

class EpisodeExt(SQLModel, table=True):
    """剧集扩展模型"""
    __tablename__ = "episode_ext"
    __table_args__ = (
        UniqueConstraint("user_id", "series_core_id", "season_number", "episode_number", name="uq_episode_and_user"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="剧集扩展记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")

    # 关联到系列和季度
    series_core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的系列核心记录ID")
    season_core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id", description="关联的季度核心记录ID（无季剧可为空）")
    
    # 剧集信息
    title: Optional[str] = Field(default=None, description="集标题")
    episode_number: int = Field(description="集数序号")
    season_number: int = Field(description="所属季度序号")
    # absolute_episode_number: Optional[int] = Field(default=None, description="绝对集序（番剧/国产剧支持）")
    
    # 播出信息
    aired_date: Optional[datetime] = Field(default=None, description="播出日期")
    runtime: Optional[int] = Field(default=None, description="时长（分钟）")
    
    # 评分
    rating: Optional[float] = Field(default=None, description="评分")
    vote_count: Optional[int] = Field(default=None, description="评分数量")
    
    # 单集详情
    overview: Optional[str] = Field(default=None, description="单集剧情简介")
    still_path: Optional[str] = Field(default=None, description="单集剧照路径")
    episode_type: Optional[str] = Field(default=None, description="集类型：standard/finale/special")


# ==================== 文件资源模型 ====================
class FileAsset(SQLModel, table=True):
    """文件资源模型 - 统一管理所有媒体相关的物理文件"""
    __tablename__ = "file_asset"
    __table_args__ = (UniqueConstraint("user_id", "full_path", name="uq_file_asset_path"),)

    id: Optional[int] = Field(default=None, primary_key=True, description="文件资源唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    storage_id: Optional[int] = Field(default=None, index=True, foreign_key="storage_config.id", description="关联的存储配置ID")

    # 文件路径
    full_path: str = Field(description="文件的完整路径")
    filename: str = Field(description="文件名")
    relative_path: str = Field(description="相对路径")

    # 关联信息 - 可绑定到不同类型的媒体记录
    core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")
    version_id: Optional[int] = Field(default=None, index=True, foreign_key="media_version.id", description="关联的媒体版本记录ID(电影版本,集版本)")
    season_version_id: Optional[int] = Field(default=None, index=True, foreign_key="media_version.id", description="关联的季度版本记录ID")
    episode_core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id", description="关联的剧集核心记录ID")
    
    # 文件元信息
    size: int = Field(sa_column=Column(BigInteger), description="文件大小（字节）")
    mimetype: Optional[str] = Field(default=None, description="MIME类型")
    video_codec: Optional[str] = Field(default=None, description="视频编码格式")
    audio_codec: Optional[str] = Field(default=None, description="音频编码格式")
    resolution: Optional[str] = Field(default=None, description="分辨率")
    frame_rate: Optional[str] = Field(default=None, description="帧率（fps）")
    duration: Optional[int] = Field(default=None, description="时长（秒）")
    etag: Optional[str] = Field(default=None, description="存储ETag标识")
    asset_role: Optional[str] = Field(default=None, description="资源角色：video|audio|subtitle|nfo|image|other")
    bitrate_kbps: Optional[int] = Field(default=None, description="码率（kbps）")
    hdr: Optional[bool] = Field(default=None, description="是否HDR（HDR10/DV）")
    audio_channels: Optional[int] = Field(default=None, description="音频声道数")
    container: Optional[str] = Field(default=None, description="封装格式：MKV/MP4等")
    asset_fingerprint: Optional[str] = Field(default=None, index=True, description="技术指纹，用于去重与归属")
    exists: bool = Field(default=True, description="当前文件是否在存储中存在")
    status: Optional[str] = Field(default=None, description="文件状态：active|deleted|moved")
    deleted_at: Optional[datetime] = Field(default=None, description="软删除时间戳")

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now_factory(), description="更新时间")


# ==================== 艺术作品模型 ====================
class Artwork(SQLModel, table=True):
    """艺术图资源模型 - 存储媒体相关的图片资源信息"""
    __tablename__ = "artwork"
    __table_args__ = (UniqueConstraint('user_id', 'core_id', 'type', 'remote_url', name="uq_artwork_core_type_url"),)

    id: Optional[int] = Field(default=None, primary_key=True, description="图片资源唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")

    # 图片信息
    type: str = Field(index=True, description="图片类型：poster|backdrop|fanart|banner|cover|folder|still")
    remote_url: Optional[str] = Field(default=None, description="远程图片URL地址")
    local_path: Optional[str] = Field(default=None, description="本地图片存储路径")
    width: Optional[int] = Field(default=None, description="图片宽度（像素）")
    height: Optional[int] = Field(default=None, description="图片高度（像素）")
    provider: Optional[str] = Field(default=None, description="图片来源提供者")
    language: Optional[str] = Field(default=None, description="图片语言")
    preferred: bool = Field(default=False, description="是否为首选图片")
    exists_local: bool = Field(default=False, description="本地文件是否存在")
    # exists_remote: bool = Field(default=True, description="远程URL是否可访问")


# ==================== 外部ID模型 ====================
class ExternalID(SQLModel, table=True):
    """外部ID映射模型 - 存储媒体在外部数据源中的标识符"""
    __tablename__ = "external_ids"
    __table_args__ = (
        UniqueConstraint("user_id", "core_id", "source", name="uq_external_ids_core_source"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="外部ID映射记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")

    # 外部数据源
    source: str = Field(index=True, description="外部数据源类型：tmdb|imdb|tvdb|douban 等")
    key: str = Field(index=True, description="外部数据源中的ID值")


# ==================== 流派模型 ====================
class Genre(SQLModel, table=True):
    """流派模型 - 管理媒体类型和分类标签"""
    __tablename__ = "genre"
    __table_args__ = (UniqueConstraint("name", name="uq_genre_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True, description="流派标签唯一标识")
    # user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    name: str = Field(index=True, description="流派名称（如动作、喜剧、科幻等）")


class MediaCoreGenre(SQLModel, table=True):
    """媒体流派关联模型"""
    __tablename__ = "media_core_genre"
    __table_args__ = (UniqueConstraint("user_id", "core_id", "genre_id", name="uq_core_genre_link"),)

    id: Optional[int] = Field(default=None, primary_key=True, description="媒体流派关联记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")
    genre_id: int = Field(index=True, foreign_key="genre.id", description="关联的流派标签ID")


# ==================== 人员信用模型 ====================
class Person(SQLModel, table=True):
    """人员基础模型 - 存储人员基本信息"""
    __tablename__ = "person"
    __table_args__ = (UniqueConstraint("provider", "provider_id", "name", name="uq_person_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True, description="人员记录唯一标识")
    # user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    name: str = Field(index=True, description="人员姓名")
    original_name: Optional[str] = Field(default=None, description="人员原始姓名")
    provider_id: Optional[int] = Field(default=None, index=True, description="TMDB人员ID（用于外部关联）")
    profile_url: Optional[str] = Field(default=None, description="人员头像URL（规范化: http(s)绝对路径）")
    provider: Optional[str] = Field(default=None, description="数据来源提供者")

class Credit(SQLModel, table=True):
    """演职员关联模型 - 关联人员与媒体作品"""
    __tablename__ = "credit"
    __table_args__ = (UniqueConstraint("user_id", "core_id", "person_id", "role", "job", name="uq_credit_unique"),)

    id: Optional[int] = Field(default=None, primary_key=True, description="演职员关联记录唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    core_id: int = Field(index=True, foreign_key="media_core.id", description="关联的媒体核心记录ID")
    person_id: int = Field(index=True, foreign_key="person.id", description="关联的人员记录ID")

    # 角色信息
    role: str = Field(index=True, description="角色类型：cast（演员/常驻）|crew（剧组人员）|guest（客串）")
    character: Optional[str] = Field(default=None, description="饰演的角色名称（仅演员）")
    job: Optional[str] = Field(default=None, description="具体职位：导演、编剧、摄影、演员等")
    order: Optional[int] = Field(default=None, description="排序索引（用于 Crew 角色）")
    # guest: Optional[bool] = Field(default=False, description="是否为 Guest 角色")
# ==================== 播放历史模型 ====================
class PlaybackHistory(SQLModel, table=True):
    __tablename__ = "playback_history"
    __table_args__ = (
        UniqueConstraint("user_id", "file_asset_id", name="uq_playback_user_file"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="users.id")
    core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id")
    file_asset_id: int = Field(index=True, foreign_key="file_asset.id")
    media_type: Optional[str] = Field(default=None)
    series_core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id")
    season_core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id")
    episode_core_id: Optional[int] = Field(default=None, index=True, foreign_key="media_core.id")
    version_id: Optional[int] = Field(default=None, index=True, foreign_key="media_version.id")
    position_ms: int = Field(default=0)
    duration_ms: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None)
    device_id: Optional[str] = Field(default=None)
    platform: Optional[str] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=get_utc_now_factory())
    updated_at: datetime = Field(default_factory=get_utc_now_factory())
