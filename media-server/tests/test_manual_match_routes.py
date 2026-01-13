import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import create_app
from core.security import get_current_subject
from core.db import get_async_session
from models.media_models import MediaCore, FileAsset
from services.scraper.base import ScraperEpisodeDetail, ScraperMovieDetail, ScraperSeriesDetail, ScraperSeasonDetail


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value

    def all(self):
        return self._value

    def one(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, exec_results):
        self._exec_results = list(exec_results)

    async def exec(self, _stmt):
        if not self._exec_results:
            raise AssertionError("exec 调用次数超出预期")
        return _FakeExecResult(self._exec_results.pop(0))


@pytest.fixture
def app():
    app = create_app()
    app.dependency_overrides[get_current_subject] = lambda: "1"
    return app


def _override_async_session(fake_session):
    async def _override():
        yield fake_session

    return _override


@pytest.fixture
def client(app):
    return TestClient(app)


def test_manual_match_tv_enqueues_persist_batch(app, client):
    media = MediaCore(id=567, user_id=1, kind="season", title="S1")
    f1 = FileAsset(
        id=301,
        user_id=1,
        storage_id=1,
        full_path="/x/1.mp4",
        filename="1.mp4",
        relative_path="1.mp4",
        season_version_id=12345,
    )
    f2 = FileAsset(
        id=302,
        user_id=1,
        storage_id=1,
        full_path="/x/2.mp4",
        filename="2.mp4",
        relative_path="2.mp4",
        season_version_id=12345,
    )
    db = _FakeAsyncSession([media, f1, f2])
    app.dependency_overrides[get_async_session] = _override_async_session(db)

    series = ScraperSeriesDetail(series_id=123, name="S")
    season = ScraperSeasonDetail(season_id=1001, season_number=1, name="S1")
    detail = ScraperEpisodeDetail(
        episode_id=90001,
        episode_number=1,
        season_number=1,
        name="E1",
        series=series,
        season=season,
    )

    with patch(
        "services.scraper.scraper_manager.get_detail",
        new_callable=AsyncMock,
    ) as mock_get_detail, patch(
        "services.task.producer.create_persist_batch_task",
        new_callable=AsyncMock,
    ) as mock_create_batch:
        mock_get_detail.return_value = ("episode", detail)
        mock_create_batch.return_value = "task-1"

        resp = client.put(
            "/api/media/567/manual-match",
            json={
                "target": {
                    "local_media_id": 567,
                    "local_media_version_id": 12345,
                    "type": "tv",
                    "provider": "tmdb",
                    "tmdb_tv_id": 123,
                    "season_number": 1,
                    "tmdb_season_id": 1001,
                },
                "items": [
                    {
                        "file_id": 301,
                        "action": "bind_episode",
                        "tmdb": {
                            "tmdb_tv_id": 123,
                            "tmdb_season_id": 1001,
                            "tmdb_episode_id": 90001,
                            "season_number": 1,
                            "episode_number": 1,
                        },
                    },
                    {"file_id": 302, "action": "keep"},
                ],
                "client_request_id": "req-1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["effective_media_id"] == 567
        assert data["accepted"] == 2
        assert data["updated"] == 1
        assert data["skipped"] == 1
        assert data["errors"] == []

        mock_get_detail.assert_awaited_once()
        mock_create_batch.assert_awaited_once()
        kwargs = mock_create_batch.await_args.kwargs
        assert kwargs["user_id"] == 1
        assert kwargs["idempotency_key"] == "persist_batch:1:req-1"
        assert len(kwargs["items"]) == 1
        assert kwargs["items"][0]["file_id"] == 301
        assert kwargs["items"][0]["contract_type"] == "episode"


def test_manual_match_movie_missing_file_returns_error(app, client):
    media = MediaCore(id=567, user_id=1, kind="movie", title="M")
    db = _FakeAsyncSession([media, None])
    app.dependency_overrides[get_async_session] = _override_async_session(db)

    detail = ScraperMovieDetail(movie_id=550, title="Fight Club")

    with patch(
        "services.scraper.scraper_manager.get_detail",
        new_callable=AsyncMock,
    ) as mock_get_detail, patch(
        "services.task.producer.create_persist_batch_task",
        new_callable=AsyncMock,
    ) as mock_create_batch:
        mock_get_detail.return_value = ("movie", detail)

        resp = client.put(
            "/api/media/567/manual-match",
            json={
                "target": {
                    "local_media_id": 567,
                    "local_media_version_id": 12345,
                    "type": "movie",
                    "provider": "tmdb",
                    "tmdb_movie_id": 550,
                },
                "items": [
                    {
                        "file_id": 999,
                        "action": "bind_movie",
                        "tmdb": {"tmdb_movie_id": 550},
                    }
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["updated"] == 0
        assert len(data["errors"]) == 1
        assert data["errors"][0]["file_id"] == 999
        assert data["errors"][0]["code"] == "file_not_found"
        mock_get_detail.assert_not_awaited()
        mock_create_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_series_detail_dedupes_duplicate_episode_versions():
    from services.media.media_service import MediaService
    from models.media_models import MediaVersion, SeasonExt, SeriesExt, EpisodeExt
    from models.storage_models import StorageConfig

    service = MediaService()

    series_core = MediaCore(id=1, user_id=1, kind="series", title="S")
    series_ext = SeriesExt(id=1, user_id=1, core_id=1, title="S")

    season_core = MediaCore(id=10, user_id=1, kind="season", title="S1")
    season_ext = SeasonExt(
        id=11,
        user_id=1,
        core_id=10,
        series_core_id=1,
        season_number=1,
        title="S1",
        episode_count=1,
    )

    season_version = MediaVersion(
        id=100,
        user_id=1,
        core_id=10,
        tags="v1",
        scope="season_group",
    )

    ep_core = MediaCore(id=20, user_id=1, kind="episode", title="E1")
    ep_ext = EpisodeExt(
        id=21,
        user_id=1,
        core_id=20,
        series_core_id=1,
        season_core_id=10,
        season_number=1,
        episode_number=1,
    )

    ep_version_empty = MediaVersion(
        id=200,
        user_id=1,
        core_id=20,
        tags="e-old",
        scope="episode_child",
        parent_version_id=100,
    )
    ep_version_with_asset = MediaVersion(
        id=201,
        user_id=1,
        core_id=20,
        tags="e-new",
        scope="episode_child",
        parent_version_id=100,
    )

    asset = FileAsset(
        id=301,
        user_id=1,
        storage_id=1,
        full_path="/x/1.mp4",
        filename="1.mp4",
        relative_path="1.mp4",
        version_id=201,
        season_version_id=100,
        size=123,
    )

    db = _FakeAsyncSession(
        [
            series_core,
            series_ext,
            [(season_core, season_ext)],
            [(season_core.id, 1)],
            [season_version],
            [ep_version_empty, ep_version_with_asset],
            [(ep_core, ep_ext)],
            [asset],
            [StorageConfig(id=1, name="st", storage_type="local")],
        ]
    )

    with patch.object(service, "_get_genres", new=AsyncMock(return_value=[])), patch.object(
        service, "_get_cast", new=AsyncMock(return_value=[])
    ), patch.object(service, "_get_storage_info", new=AsyncMock(return_value={"id": 1})):
        detail = await service._get_series_detail2(db=db, user_id=1, series_core_id=1)

    episodes = detail["seasons"][0]["versions"][0]["episodes"]
    assert len(episodes) == 1
    assert episodes[0]["id"] == 20
    assert episodes[0]["episode_number"] == 1
    assert len(episodes[0]["assets"]) == 1
    assert episodes[0]["assets"][0]["file_id"] == 301
