"""
刮削器插件基础接口和数据模型

"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional


# 原有枚举类不变
class MediaType(Enum):
    MOVIE = "movie"
    TV_SERIES = "tv_series"
    TV_SEASON = "tv_season"
    TV_EPISODE = "tv_episode"

class ArtworkType(Enum):
    POSTER = "poster"
    BACKDROP = "backdrop"
    BANNER = "banner"
    THUMB = "thumb"
    LOGO = "logo"
    CLEARART = "clearart"
    DISC = "disc"

class CreditType(Enum):
    DIRECTOR = "director"
    WRITER = "writer"
    ACTOR = "actor"
    PRODUCER = "producer"
    COMPOSER = "composer"
    CINEMATOGRAPHER = "cinematographer"
    EDITOR = "editor"


# 1. 基础数据类（补充综艺独有字段）
@dataclass
class ScraperExternalId:
    provider: str
    external_id: str
    url: Optional[str] = None

@dataclass
class ScraperArtwork:
    type: ArtworkType
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    language: Optional[str] = None
    rating: Optional[float] = None
    vote_count: Optional[int] = None

@dataclass
class ScraperCredit:
    type: CreditType
    name: str
    role: Optional[str] = None
    order: Optional[int] = None
    image_url: Optional[str] = None
    provider_id: Optional[int] = None
    is_flying: Optional[bool] = None  # 综艺独有：是否为飞行嘉宾


# 2. 搜索详情（无独有字段，保持原有结构）
@dataclass
class ScraperSearchResult:
    id: str
    title: str
    original_name: Optional[str] = None
    original_language: Optional[str] = None
    release_date: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    origin_country: List[str] = field(default_factory=list)
    original_languages: List[str] = field(default_factory=list)
    popularity: Optional[float] = None
    provider: Optional[str] = None
    media_type: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    year: Optional[int] = None
    provider_url: Optional[str] = None


# 3. 电影详情（无关联，保持原有结构）
@dataclass
class ScraperMovieDetail:
    movie_id: str
    title: str
    original_title: Optional[str] = None
    original_language: Optional[str] = None
    origin_country: List[str] = field(default_factory=list)
    overview: Optional[str] = None
    release_date: Optional[str] = None
    runtime: Optional[int] = None
    tagline: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    imdb_id: Optional[str] = None
    status: Optional[str] = None
    belongs_to_collection: Optional[Dict] = None
    popularity: Optional[float] = None
    provider: Optional[str] = None
    provider_url: Optional[str] = None
    artworks: List[ScraperArtwork] = field(default_factory=list)
    credits: List[ScraperCredit] = field(default_factory=list)
    external_ids: List[ScraperExternalId] = field(default_factory=list)
    raw_data: Optional[Dict] = None


# 4. 系列详情（新增综艺独有字段）
# @dataclass
# class ScraperSeasonBrief:
#     """系列详情中的季概要（含综艺特别篇标识）"""
#     season_id: str
#     season_number: int
#     name: Optional[str] = None
#     overview: Optional[str] = None
#     poster_path: Optional[str] = None
#     episode_count: Optional[int] = None
#     air_date: Optional[str] = None
#     vote_average: Optional[float] = None
#     is_special: Optional[bool] = None  # 综艺独有：是否为特别篇（season0）

@dataclass
class ScraperSeriesDetail:
    series_id: str
    name: str
    original_name: Optional[str] = None
    origin_country: List[str] = field(default_factory=list)
    overview: Optional[str] = None
    tagline: Optional[str] = None
    status: Optional[str] = None
    first_air_date: Optional[str] = None
    last_air_date: Optional[str] = None
    episode_run_time: List[int] = field(default_factory=list)
    number_of_episodes: Optional[int] = None
    number_of_seasons: Optional[int] = None
    genres: List[str] = field(default_factory=list)
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    popularity: Optional[float] = None
    provider: Optional[str] = None
    provider_url: Optional[str] = None
    artworks: List[ScraperArtwork] = field(default_factory=list)
    credits: List[ScraperCredit] = field(default_factory=list)
    external_ids: List[ScraperExternalId] = field(default_factory=list)
    raw_data: Optional[Dict] = None
    # 新增独有字段
    type: Optional[str] = None  # 综艺：Reality；剧集/动画：Scripted
    # seasons: List[ScraperSeasonBrief] = field(default_factory=list)  # 季概要列表


# 5. 季详情（新增综艺/动画独有字段）
@dataclass
class ScraperEpisodeItem:
    """季详情中的集概要（含综艺期数部分、动画篇章名）"""
    episode_id: Optional[str]
    episode_number: int
    season_number: int
    name: str
    overview: Optional[str] = None
    air_date: Optional[str] = None
    runtime: Optional[int] = None
    still_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    # 新增独有字段
    # episode_part: Optional[str] = None  # 综艺：期数部分（上/下）
    # chapter_name: Optional[str] = None  # 动画：篇章名（如风起天南）

@dataclass
class ScraperSeasonDetail:
    season_id: Optional[str]
    season_number: int
    name: Optional[str] = None
    poster_path: Optional[str] = None
    overview: Optional[str] = None
    episode_count: Optional[int] = None
    air_date: Optional[str] = None
    episodes: List[ScraperEpisodeItem] = field(default_factory=list)
    vote_average: Optional[float] = None
    provider: Optional[str] = None
    provider_url: Optional[str] = None
    artworks: List[ScraperArtwork] = field(default_factory=list)
    credits: List[ScraperCredit] = field(default_factory=list)
    external_ids: List[ScraperExternalId] = field(default_factory=list)
    raw_data: Optional[Dict] = None
    # is_special: Optional[bool] = None  # 综艺独有：是否为特别篇（season0）

    # 新增字段（TMDB原生，现有类缺失）
    # _id: Optional[str] = None  # 季唯一标识（如ObjectId）


# 6. 集详情（新增综艺/动画独有字段）
@dataclass
class ScraperEpisodeDetail:
    episode_id: Optional[str]
    episode_number: int
    season_number: int
    name: str
    overview: Optional[str] = None
    air_date: Optional[str] = None
    runtime: Optional[int] = None
    still_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    provider: Optional[str] = None
    provider_url: Optional[str] = None
    artworks: List[ScraperArtwork] = field(default_factory=list)
    credits: List[ScraperCredit] = field(default_factory=list)
    external_ids: List[ScraperExternalId] = field(default_factory=list)
    raw_data: Optional[Dict] = None
    series: Optional["ScraperSeriesDetail"] = None
    season: Optional["ScraperSeasonDetail"] = None
    # 新增独有字段
    episode_type: Optional[str] = None  # TMDB集类型（standard/finale）
    # episode_part: Optional[str] = None  # 综艺：期数部分（上/下）
    # chapter_name: Optional[str] = None  # 动画：篇章名（如风起天南）

class ScraperPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @property
    @abstractmethod
    def supported_media_types(self) -> List[MediaType]:
        pass
    
    @property
    @abstractmethod
    def default_language(self) -> str:
        pass
    
    @property
    def priority(self) -> int:
        return 100
    
    @property
    def enabled(self) -> bool:
        return True
    
    @abstractmethod
    async def search(self, title: str, year: Optional[int] = None,
                    media_type: MediaType = MediaType.MOVIE,
                    language: str = "zh-CN") -> List[ScraperSearchResult]:
        pass
    
    @abstractmethod
    async def get_movie_details(self, movie_id: str, language: str = "zh-CN") -> Optional[ScraperMovieDetail]:
        pass
    
    @abstractmethod
    async def get_series_details(self, series_id: str, language: str = "zh-CN") -> Optional[ScraperSeriesDetail]:
        pass
    
    @abstractmethod
    async def get_season_details(self, series_id: str, season_number: int, language: str = "zh-CN") -> Optional[ScraperSeasonDetail]:
        pass
    
    @abstractmethod
    async def get_episode_details(self, series_id: str, season_number: int, episode_number: int, language: str = "zh-CN") -> Optional[ScraperEpisodeDetail]:
        pass
    
    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "batch_series": False,
            "batch_season": False,
            "hierarchical_cache": False,
            "multi_lang": True,
            "rate_limit_exposed": True,
        }
    
    async def get_series_details_many(self, series_ids: List[str], language: str = "zh-CN") -> Dict[str, ScraperSeriesDetail]:
        return {}
    
    async def get_season_details_many(self, requests: List[tuple], language: str = "zh-CN") -> Dict[tuple, ScraperSeasonDetail]:
        return {}
    
    async def get_artworks(self, provider_id: str, media_type: MediaType,
                          language: str = "zh-CN") -> List[ScraperArtwork]:
        if media_type == MediaType.MOVIE:
            d = await self.get_movie_details(provider_id, language)
            return d.artworks if d else []
        elif media_type == MediaType.TV_SERIES:
            d = await self.get_series_details(provider_id, language)
            return d.artworks if d else []
        else:
            return []
    
    async def get_credits(self, provider_id: str, media_type: MediaType,
                        language: str = "zh-CN") -> List[ScraperCredit]:
        if media_type == MediaType.MOVIE:
            d = await self.get_movie_details(provider_id, language)
            return d.credits if d else []
        elif media_type == MediaType.TV_SERIES:
            d = await self.get_series_details(provider_id, language)
            return d.credits if d else []
        else:
            return []
    
    def configure(self, config: Dict[str, any]) -> bool:
        return True
    
    async def test_connection(self) -> bool:
        return True
    
    async def startup(self) -> None:
        return None
    
    async def shutdown(self) -> None:
        return None
    
    def get_config_schema(self) -> Dict[str, any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
