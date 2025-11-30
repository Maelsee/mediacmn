"""
刮削器插件系统

提供统一的插件接口，支持多种元数据源（TMDB、豆瓣、TVMaze等）
"""

from .base import (
    ScraperPlugin,
    ScraperSearchResult,
    ScraperMovieDetail,
    ScraperSeriesDetail,
    ScraperSeasonDetail,
    ScraperEpisodeDetail,
    ScraperEpisodeItem,
    ScraperArtwork,
    ScraperCredit,
    ScraperExternalId,
    MediaType,
)
from .manager import ScraperManager, scraper_manager
from .tmdb import TmdbScraper
from .douban import DoubanScraper

__all__ = [
    'ScraperPlugin',
    'ScraperSearchResult',
    'ScraperMovieDetail',
    'ScraperSeriesDetail',
    'ScraperSeasonDetail',
    'ScraperEpisodeDetail',
    'ScraperEpisodeItem',
    'ScraperArtwork',
    'ScraperCredit',
    'ScraperExternalId',
    'MediaType',
    'ScraperManager',
    'scraper_manager',
    'TmdbScraper',
    'DoubanScraper'
]
