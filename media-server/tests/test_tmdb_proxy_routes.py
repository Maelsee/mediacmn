import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import create_app
from core.security import get_current_subject
from services.tmdb_proxy_service import TmdbProxyNotConfiguredError, TmdbProxyTimeoutError


@pytest.fixture
def app():
    app = create_app()
    app.dependency_overrides[get_current_subject] = lambda: "1"
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_tmdb_search_tv_success(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.search_tv",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = {
            "page": 1,
            "total_pages": 3,
            "total_results": 50,
            "items": [
                {
                    "tmdb_id": 12345,
                    "name": "极限挑战",
                    "original_name": "Go Fighting",
                    "first_air_date": "2015-06-14",
                    "origin_country": ["CN"],
                    "overview": "...",
                    "poster_path": "/xxx.jpg",
                    "backdrop_path": "/yyy.jpg",
                }
            ],
        }

        resp = client.get("/api/tmdb/search/tv", params={"q": "极限挑战"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["items"][0]["tmdb_id"] == 12345
        mock_search.assert_awaited_once()


def test_tmdb_tv_seasons_success(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.get_tv_seasons",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = {
            "tmdb_id": 12345,
            "name": "极限挑战",
            "seasons": [
                {
                    "season_number": 1,
                    "name": "第 1 季",
                    "episode_count": 12,
                    "air_date": "2015-06-14",
                    "poster_path": "/s1.jpg",
                }
            ],
        }

        resp = client.get("/api/tmdb/tv/12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tmdb_id"] == 12345
        assert data["seasons"][0]["season_number"] == 1
        mock_get.assert_awaited_once()


def test_tmdb_tv_season_episodes_success(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.get_tv_season_episodes",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = {
            "series_tmdb_id": 12345,
            "season_number": 1,
            "episodes": [
                {
                    "episode_number": 1,
                    "episode_tmdb_id": 90001,
                    "name": "时间战争",
                    "air_date": "2015-06-14",
                    "overview": "...",
                    "still_path": "/e1.jpg",
                    "runtime": 90,
                }
            ],
        }

        resp = client.get("/api/tmdb/tv/12345/season/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["series_tmdb_id"] == 12345
        assert data["episodes"][0]["episode_tmdb_id"] == 90001
        mock_get.assert_awaited_once()


def test_tmdb_search_tv_not_configured(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.search_tv",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.side_effect = TmdbProxyNotConfiguredError("TMDB 未配置")
        resp = client.get("/api/tmdb/search/tv", params={"q": "极限挑战"})
        assert resp.status_code == 503


def test_tmdb_search_movie_success(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.search_movie",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = {
            "page": 1,
            "total_pages": 2,
            "total_results": 20,
            "items": [
                {
                    "tmdb_id": 550,
                    "title": "Fight Club",
                    "original_title": "Fight Club",
                    "release_date": "1999-10-15",
                    "overview": "...",
                    "poster_path": "/p.jpg",
                    "backdrop_path": "/b.jpg",
                }
            ],
        }

        resp = client.get("/api/tmdb/search/movie", params={"q": "Fight Club"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["tmdb_id"] == 550
        assert data["items"][0]["title"] == "Fight Club"
        mock_search.assert_awaited_once()


def test_tmdb_search_movie_not_configured(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.search_movie",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.side_effect = TmdbProxyNotConfiguredError("TMDB 未配置")
        resp = client.get("/api/tmdb/search/movie", params={"q": "Fight Club"})
        assert resp.status_code == 503


def test_tmdb_search_movie_timeout(client):
    with patch(
        "services.tmdb_proxy_service.tmdb_proxy_service.search_movie",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.side_effect = TmdbProxyTimeoutError("TMDB 代理请求超时")
        resp = client.get("/api/tmdb/search/movie", params={"q": "长安"})
        assert resp.status_code == 504
