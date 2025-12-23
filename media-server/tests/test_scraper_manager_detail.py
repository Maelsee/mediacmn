import asyncio
import time

from services.scraper import scraper_manager
from services.scraper.base import (
    MediaType,
    ScraperEpisodeDetail,
    ScraperMovieDetail,
    ScraperPlugin,
    ScraperSearchResult,
    ScraperSeasonDetail,
    ScraperSeriesDetail,
)
from services.scraper.manager import ScraperManager, _LocalDetailCache


class DummyPlugin(ScraperPlugin):
    name = "dummy"
    supported_media_types = [MediaType.MOVIE, MediaType.TV_SERIES, MediaType.TV_SEASON, MediaType.TV_EPISODE]

    def __init__(self):
        super().__init__()
        self.calls = []
        self.movie_calls = 0
        self.series_calls = 0
        self.season_calls = 0
        self.episode_calls = 0
        self.sleep_seconds = 0.0

    @property
    def default_language(self) -> str:
        return "zh-CN"

    async def search(self, title: str, year=None, media_type: MediaType = MediaType.MOVIE, language: str = ""):
        return []

    async def get_movie_details(self, movie_id: int, language: str = ""):
        self.movie_calls += 1
        self.calls.append(("movie", movie_id, language))
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        return ScraperMovieDetail(movie_id=movie_id, title="m", provider=self.name)

    async def get_series_details(self, series_id: int, language: str = ""):
        self.series_calls += 1
        self.calls.append(("series", series_id, language))
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        return ScraperSeriesDetail(series_id=series_id, name="s", provider=self.name)

    async def get_season_details(self, series_id: int, season_number: int, language: str = ""):
        self.season_calls += 1
        self.calls.append(("season", series_id, season_number, language))
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        return ScraperSeasonDetail(season_id=None, season_number=season_number, provider=self.name, episodes=[])

    async def get_episode_details(self, series_id: int, season_number: int, episode_number: int, language: str = ""):
        self.episode_calls += 1
        self.calls.append(("episode", series_id, season_number, episode_number, language))
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        return ScraperEpisodeDetail(
            episode_id=None,
            season_number=season_number,
            episode_number=episode_number,
            name="e",
            provider=self.name,
        )


def test_plugin_get_details_dispatch():
    async def _run():
        p = DummyPlugin()
        await p.get_details("1", MediaType.MOVIE, language="en-US")
        await p.get_details("2", MediaType.TV_SERIES, language="en-US")
        await p.get_details("2:3", MediaType.TV_SEASON, language="en-US")
        await p.get_details("2:3:4", MediaType.TV_EPISODE, language="en-US")
        return p.calls

    calls = asyncio.run(_run())
    assert calls[0] == ("movie", 1, "en-US")
    assert calls[1] == ("series", 2, "en-US")
    assert calls[2] == ("season", 2, 3, "en-US")
    assert calls[3] == ("episode", 2, 3, 4, "en-US")

class FakeRedis:
    def __init__(self):
        self._data = {}
        self._expires = {}

    async def get(self, key: str):
        now = time.monotonic()
        exp = self._expires.get(key)
        if exp is not None and exp <= now:
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return None
        return self._data.get(key)

    async def set(self, key: str, value: bytes, ex: int = 0, nx: bool = False):
        now = time.monotonic()
        if nx and await self.get(key) is not None:
            return False
        self._data[key] = value
        if ex:
            self._expires[key] = now + float(ex)
        else:
            self._expires.pop(key, None)
        return True

    async def delete(self, key: str):
        self._data.pop(key, None)
        self._expires.pop(key, None)
        return 1


def test_manager_get_detail_caches_series_and_season_and_times_out():
    async def _run():
        await scraper_manager.clear()
        scraper_manager._started = True  # type: ignore
        scraper_manager._timeout_seconds = 0.01  # type: ignore

        plugin = DummyPlugin()
        plugin.sleep_seconds = 0.0
        scraper_manager._plugins["dummy"] = plugin  # type: ignore
        scraper_manager._enabled_plugins = ["dummy"]  # type: ignore

        bm = ScraperSearchResult(id=100, title="x", provider="dummy", year=2024)
        await asyncio.gather(
            scraper_manager.get_detail(bm, MediaType.TV_EPISODE, language="en-US", season=1, episode=1),
            scraper_manager.get_detail(bm, MediaType.TV_EPISODE, language="en-US", season=1, episode=2),
            scraper_manager.get_detail(bm, MediaType.TV_EPISODE, language="en-US", season=1, episode=3),
        )

        assert plugin.series_calls == 1
        assert plugin.season_calls == 1
        assert plugin.episode_calls == 3

        await scraper_manager.get_detail(bm, MediaType.TV_EPISODE, language="en-US", season=1, episode=1)
        assert plugin.series_calls == 1
        assert plugin.season_calls == 1
        assert plugin.episode_calls == 4

        plugin2 = DummyPlugin()
        plugin2.sleep_seconds = 0.05
        scraper_manager._plugins["dummy"] = plugin2  # type: ignore

        ct, obj = await scraper_manager.get_detail(bm, MediaType.MOVIE, language="en-US")
        assert ct == "search_result"
        assert obj is bm

        await scraper_manager.clear()

    asyncio.run(_run())


def test_distributed_singleflight_prevents_cross_process_stampede():
    class SharedCounter:
        def __init__(self):
            self.series_calls = 0

    class Plugin1(DummyPlugin):
        def __init__(self, counter: SharedCounter, sleep_seconds: float):
            super().__init__()
            self._counter = counter
            self.sleep_seconds = sleep_seconds

        async def get_series_details(self, series_id: int, language: str = ""):
            self._counter.series_calls += 1
            if self.sleep_seconds:
                await asyncio.sleep(self.sleep_seconds)
            return ScraperSeriesDetail(series_id=series_id, name="s", provider=self.name)

    async def _run():
        fake = FakeRedis()
        counter = SharedCounter()

        ScraperManager._instance = None
        ScraperManager._init_done = False
        m1 = ScraperManager()
        ScraperManager._instance = None
        ScraperManager._init_done = False
        m2 = ScraperManager()

        for m in (m1, m2):
            m._started = True  # type: ignore
            m._timeout_seconds = 1.0  # type: ignore
            m._use_redis_cache = True  # type: ignore
            m._redis = fake  # type: ignore
            m._cache_ttl_seconds = 60  # type: ignore
            m._lock_ttl_seconds = 5  # type: ignore
            m._lock_wait_ms = 2000  # type: ignore
            m._lock_poll_ms = 10  # type: ignore
            m._detail_cache = _LocalDetailCache(maxsize=16, ttl_seconds=60)  # type: ignore

        m1._plugins["dummy"] = Plugin1(counter, sleep_seconds=0.05)  # type: ignore
        m2._plugins["dummy"] = Plugin1(counter, sleep_seconds=0.0)  # type: ignore

        bm = ScraperSearchResult(id=100, title="x", provider="dummy", year=2024)
        await asyncio.gather(
            m1.get_detail(bm, MediaType.TV_SERIES, language="en-US"),
            m2.get_detail(bm, MediaType.TV_SERIES, language="en-US"),
        )

        assert counter.series_calls == 1

    asyncio.run(_run())
