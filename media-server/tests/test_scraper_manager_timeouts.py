import os
import asyncio

import pytest

from core.config import get_settings
from services.scraper.base import MediaType, ScraperPlugin
from services.scraper.manager import ScraperManager


class _HangingTestConnectionPlugin(ScraperPlugin):
    name = "hang_test"
    supported_media_types = [MediaType.MOVIE]

    @property
    def default_language(self) -> str:
        return "zh-CN"

    async def test_connection(self) -> bool:
        await asyncio.sleep(3600)
        return True

    async def search(self, title: str, year: int | None = None, media_type: MediaType = MediaType.MOVIE, language: str = ""):
        return []

    async def get_movie_details(self, movie_id: int, language: str = ""):
        return None

    async def get_series_details(self, series_id: int, language: str = ""):
        return None

    async def get_season_details(self, series_id: int, season_number: int, language: str = ""):
        return None

    async def get_episode_details(self, series_id: int, season_number: int, episode_number: int, language: str = ""):
        return None


class _HangingStartupPlugin(ScraperPlugin):
    name = "hang_startup"
    supported_media_types = [MediaType.MOVIE]

    @property
    def default_language(self) -> str:
        return "zh-CN"

    async def startup(self) -> None:
        await asyncio.sleep(3600)

    async def search(self, title: str, year: int | None = None, media_type: MediaType = MediaType.MOVIE, language: str = ""):
        return []

    async def get_movie_details(self, movie_id: int, language: str = ""):
        return None

    async def get_series_details(self, series_id: int, language: str = ""):
        return None

    async def get_season_details(self, series_id: int, season_number: int, language: str = ""):
        return None

    async def get_episode_details(self, series_id: int, season_number: int, episode_number: int, language: str = ""):
        return None


@pytest.mark.asyncio
async def test_load_plugin_times_out_test_connection_but_loads():
    os.environ["SCRAPER_PLUGIN_TEST_TIMEOUT_SECONDS"] = "0.01"
    get_settings.cache_clear()
    ScraperManager._instance = None
    ScraperManager._init_done = False
    mgr = ScraperManager()
    mgr.register_plugin(_HangingTestConnectionPlugin)
    ok = await mgr.load_plugin(_HangingTestConnectionPlugin.name)
    assert ok is True
    assert mgr.get_plugin(_HangingTestConnectionPlugin.name) is not None


@pytest.mark.asyncio
async def test_startup_times_out_plugin_startup_but_manager_starts():
    os.environ["TMDB_API_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["TMDB_TIMEOUT"] = "1"
    os.environ["SCRAPER_PLUGIN_TEST_TIMEOUT_SECONDS"] = "0.01"
    os.environ["SCRAPER_PLUGIN_STARTUP_TIMEOUT_SECONDS"] = "0.01"
    os.environ["ENABLE_SCRAPERS"] = '["tmdb","hang_startup"]'
    get_settings.cache_clear()
    ScraperManager._instance = None
    ScraperManager._init_done = False
    mgr = ScraperManager()
    mgr.register_plugin(_HangingStartupPlugin)
    await mgr.startup()
    assert mgr.is_running is True
    assert _HangingStartupPlugin.name in mgr.get_loaded_plugins()
