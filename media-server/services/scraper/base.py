"""
刮削器插件基础接口和数据模型

"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, List, Optional, Any
from enum import Enum

class ScraperBaseModel(BaseModel):
    """基础配置模型(可选orjson 的加速配置)"""
    model_config = ConfigDict(
        use_enum_values=True,     # 序列化时自动将 Enum 转为 value
        from_attributes=True,    # 支持从类对象/ORM中创建
        validate_assignment=True # 赋值时进行校验
    )

# 原有枚举类不变
class MediaType(Enum):
    MOVIE = "movie"
    TV_SERIES = "series"
    TV_SEASON = "season"
    TV_EPISODE = "episode"

class ArtworkType(Enum):
    POSTER = "poster"
    BACKDROP = "backdrop"
    BANNER = "banner"
    THUMB = "thumb"
    STILL = "still"
    LOGO = "logo"
    CLEARART = "clearart"
    DISC = "disc"

class CreditType(Enum):
    DIRECTOR = "director"
    WRITER = "writer"
    ACTOR = "actor"
    GUEST = "guest"
    PRODUCER = "producer"
    COMPOSER = "composer"
    CINEMATOGRAPHER = "cinematographer"
    EDITOR = "editor"

# --- 基础数据类 ---
class ScraperExternalId(ScraperBaseModel):
    provider: str
    external_id: str
    url: Optional[str] = None

class ScraperArtwork(ScraperBaseModel):
    type: ArtworkType
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    language: Optional[str] = None
    rating: Optional[float] = None
    vote_count: Optional[int] = None
    is_primary: Optional[bool] = None

class ScraperCredit(ScraperBaseModel):
    type: CreditType
    name: str
    original_name: Optional[str] = None
    character: Optional[str] = None
    order: Optional[int] = None
    image_url: Optional[str] = None
    provider_id: Optional[int] = None
    is_flying: Optional[bool] = None

# --- 业务详情类 ---

class ScraperSearchResult(ScraperBaseModel):
    id: int
    title: str
    original_name: Optional[str] = None
    original_language: Optional[str] = None
    release_date: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    origin_country: List[str] = []
    popularity: Optional[float] = None
    provider: Optional[str] = None
    media_type: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    year: Optional[int] = None
    provider_url: Optional[str] = None

class ScraperMovieDetail(ScraperBaseModel):
    movie_id: int
    title: str
    original_title: Optional[str] = None
    original_language: Optional[str] = None
    origin_country: List[str] = []
    overview: Optional[str] = None
    release_date: Optional[str] = None
    runtime: Optional[int] = None
    tagline: Optional[str] = None
    genres: List[str] = []
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
    artworks: List[ScraperArtwork] = []
    credits: List[ScraperCredit] = []
    external_ids: List[ScraperExternalId] = []
    raw_data: Optional[Dict] = None

class ScraperSeriesDetail(ScraperBaseModel):
    series_id: int
    name: str
    original_name: Optional[str] = None
    origin_country: List[str] = []
    overview: Optional[str] = None
    tagline: Optional[str] = None
    status: Optional[str] = None
    first_air_date: Optional[str] = None
    last_air_date: Optional[str] = None
    episode_run_time: List[int] = []
    number_of_episodes: Optional[int] = None
    number_of_seasons: Optional[int] = None
    genres: List[str] = []
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    popularity: Optional[float] = None
    provider: Optional[str] = None
    provider_url: Optional[str] = None
    artworks: List[ScraperArtwork] = []
    credits: List[ScraperCredit] = []
    external_ids: List[ScraperExternalId] = []
    raw_data: Optional[Dict] = None
    type: Optional[str] = None

class ScraperEpisodeItem(ScraperBaseModel):
    episode_id: Optional[int]
    episode_number: int
    season_number: int
    name: str
    overview: Optional[str] = None
    air_date: Optional[str] = None
    runtime: Optional[int] = None
    still_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None

class ScraperSeasonDetail(ScraperBaseModel):
    season_id: Optional[int]
    season_number: int
    name: Optional[str] = None
    poster_path: Optional[str] = None
    overview: Optional[str] = None
    episode_count: Optional[int] = None
    air_date: Optional[str] = None
    episodes: List[ScraperEpisodeItem] = []
    vote_average: Optional[float] = None
    provider: Optional[str] = None
    provider_url: Optional[str] = None
    artworks: List[ScraperArtwork] = []
    credits: List[ScraperCredit] = []
    genres: List[str] = []
    external_ids: List[ScraperExternalId] = []
    raw_data: Optional[Dict] = None

class ScraperEpisodeDetail(ScraperBaseModel):
    episode_id: Optional[int]
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
    artworks: List[ScraperArtwork] = []
    credits: List[ScraperCredit] = []
    external_ids: List[ScraperExternalId] = []
    raw_data: Optional[Dict] = None
    series: Optional[ScraperSeriesDetail] = None
    season: Optional[ScraperSeasonDetail] = None
    episode_type: Optional[str] = None

class ScraperPlugin(ABC):
    """
    刮削器插件抽象基类
    """
    # 类属性定义，方便 Manager 快速读取
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    supported_media_types: List[MediaType] = field(default_factory=list)
    def __init__(self):
        self.config: Dict[str, any] = {}
    

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
    # ================= 配置系统 =================

    def configure(self, config: Dict[str, Any]) -> bool:
        """
        配置入口：Manager 调用此方法注入配置。
        """
        self.config.update(config)
        return self._on_config_updated()

    def _on_config_updated(self) -> bool:
        """配置更新后的钩子，子类可在此验证 API Key 或重连"""
        return True

    def get_config_schema(self) -> Dict[str, Any]:
        """返回 Pydantic 模型或 JSON Schema，描述所需配置项"""
        return {}

    # ================= 核心刮削接口 =================
    
    @abstractmethod
    async def search(self, title: str, year: Optional[int] = None,media_type: MediaType = MediaType.MOVIE,language: str = "") -> List[ScraperSearchResult]:
        """搜索媒体"""            
        pass  
    
    @abstractmethod
    async def get_movie_details(self, movie_id: int, language: str = "") -> Optional[ScraperMovieDetail]:
        pass   
    
    @abstractmethod
    async def get_series_details(self, series_id: int, language: str = "") -> Optional[ScraperSeriesDetail]:
        pass 
    
    @abstractmethod
    async def get_season_details(self, series_id: int, season_number: int, language: str = "") -> Optional[ScraperSeasonDetail]:
        pass
    
    @abstractmethod
    async def get_episode_details(self, series_id: int, season_number: int, episode_number: int, language: str = "") -> Optional[ScraperEpisodeDetail]:
        pass
    

    async def get_details(self, provider_id: str, media_type: MediaType, language: str = "") -> Optional[Any]:
        lang = language or self.default_language
        try:
            if media_type == MediaType.MOVIE:
                return await self.get_movie_details(int(provider_id), lang)
            if media_type == MediaType.TV_SERIES:
                return await self.get_series_details(int(provider_id), lang)
            if media_type == MediaType.TV_SEASON:
                parts = str(provider_id).split(":")
                if len(parts) != 2:
                    return None
                series_id = int(parts[0])
                season_number = int(parts[1])
                return await self.get_season_details(series_id, season_number, lang)
            if media_type == MediaType.TV_EPISODE:
                parts = str(provider_id).split(":")
                if len(parts) != 3:
                    return None
                series_id = int(parts[0])
                season_number = int(parts[1])
                episode_number = int(parts[2])
                return await self.get_episode_details(series_id, season_number, episode_number, lang)
            return None
        except Exception:
            return None
    
    async def get_by_external_id(self, external_id: str, external_source: str, 
                                 media_type: MediaType, language: str = "") -> Optional[any]:
        """
        通过外部 ID (如 imdb_id) 直接获取详情
        这对于跨插件元数据补全非常有用
        """
        return None
    
    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "batch_series": False,
            "batch_season": False,
            "hierarchical_cache": False,
            "multi_lang": True,
            "rate_limit_exposed": True,
        }

    async def get_series_details_many(self, series_ids: List[int], language: str = "") -> Dict[int, ScraperSeriesDetail]:
        return {}  
    async def get_season_details_many(self, season_ids: List[int], language: str = "") -> Dict[int, ScraperSeasonDetail]:
        return {}

    # ================= 生命周期钩子 =================  
    async def test_connection(self) -> bool:
        return True
    
    async def startup(self) -> None:
        return None
    
    async def shutdown(self) -> None:
        return None
