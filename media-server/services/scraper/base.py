"""
刮削器插件基础接口和数据模型

"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional


class MediaType(Enum):
    """媒体类型"""
    MOVIE = "movie"
    TV_SERIES = "tv_series"
    TV_SEASON = "tv_season"
    TV_EPISODE = "tv_episode"


class ArtworkType(Enum):
    """艺术作品类型"""
    POSTER = "poster"
    BACKDROP = "backdrop"
    BANNER = "banner"
    THUMB = "thumb"
    LOGO = "logo"
    CLEARART = "clearart"
    DISC = "disc"


class CreditType(Enum):
    """演职员类型"""
    DIRECTOR = "director"
    WRITER = "writer"
    ACTOR = "actor"
    PRODUCER = "producer"
    COMPOSER = "composer"
    CINEMATOGRAPHER = "cinematographer"
    EDITOR = "editor"


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
    external_ids: List[ScraperExternalId] = None
    
    def __post_init__(self):
        if self.external_ids is None:
            self.external_ids = []


@dataclass
class ScraperSearchResult:
    id: str
    title: str
    original_name: Optional[str] = None
    original_language: Optional[str] = None
    release_date: Optional[str] = None
    vote_average: Optional[float] = None
    provider: Optional[str] = None
    media_type: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    year: Optional[int] = None
    rating: Optional[float] = None
    provider_url: Optional[str] = None

@dataclass
class ScraperMovieDetail:
    movie_id: str
    title: str
    original_title: Optional[str] = None
    original_language: Optional[str] = None
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

@dataclass
class ScraperEpisodeItem:
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
