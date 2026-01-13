from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import asyncio
import socket

import aiohttp
from core.logging import logger
from core.config import get_settings


class TmdbProxyError(Exception):
    pass


class TmdbProxyNotConfiguredError(TmdbProxyError):
    pass


class TmdbProxyUpstreamError(TmdbProxyError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"TMDB upstream error: {status_code} {message}")


class TmdbProxyTimeoutError(TmdbProxyError):
    pass


@dataclass(frozen=True)
class _TmdbAuth:
    headers: Dict[str, str]
    params: Dict[str, str]


class TmdbProxyService:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = getattr(settings, "TMDB_API_BASE_URL", "https://api.themoviedb.org/3")
        self._timeout_seconds = int(getattr(settings, "TMDB_TIMEOUT", 30))
        self._proxy: Optional[str] = getattr(settings, "TMDB_PROXY", None)
        self._force_ipv4: bool = bool(getattr(settings, "TMDB_FORCE_IPV4", False))
        self._sessions: Dict[bool, aiohttp.ClientSession] = {}

    def _build_timeout(self) -> aiohttp.ClientTimeout:
        total = float(self._timeout_seconds)
        connect = min(5.0, total)
        return aiohttp.ClientTimeout(total=total, connect=connect, sock_connect=connect, sock_read=total)

    def _build_connector(self, force_ipv4: bool) -> aiohttp.TCPConnector:
        family = socket.AF_INET if force_ipv4 else socket.AF_UNSPEC
        return aiohttp.TCPConnector(ttl_dns_cache=300, family=family)

    async def _get_session(self, force_ipv4: bool) -> aiohttp.ClientSession:
        session = self._sessions.get(force_ipv4)
        if session and not session.closed:
            return session

        timeout = self._build_timeout()
        connector = self._build_connector(force_ipv4=force_ipv4)
        session = aiohttp.ClientSession(trust_env=True, timeout=timeout, connector=connector)
        self._sessions[force_ipv4] = session
        return session

    def _auth(self) -> _TmdbAuth:
        settings = get_settings()
        api_key = getattr(settings, "TMDB_API_KEY", None)
        v4_token = getattr(settings, "TMDB_V4_TOKEN", None)

        headers: Dict[str, str] = {"Accept": "application/json"}
        params: Dict[str, str] = {}

        if api_key:
            params["api_key"] = str(api_key)
            return _TmdbAuth(headers=headers, params=params)

        if v4_token:
            headers["Authorization"] = f"Bearer {v4_token}"
            return _TmdbAuth(headers=headers, params=params)

        raise TmdbProxyNotConfiguredError("TMDB_API_KEY/TMDB_V4_TOKEN 均未配置")

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        auth = self._auth()
        url = f"{self._base_url}{path}"

        merged_params: Dict[str, Any] = {}
        merged_params.update(auth.params)
        if params:
            merged_params.update(params)

        kwargs: Dict[str, Any] = {"params": merged_params, "headers": auth.headers}
        if self._proxy:
            kwargs["proxy"] = self._proxy

        last_exc: Optional[BaseException] = None
        attempts = [self._force_ipv4, True] if not self._force_ipv4 else [True]
        for force_ipv4 in attempts:
            session = await self._get_session(force_ipv4=force_ipv4)
            try:
                logger.debug(f"TMDB Proxy Request: {url}, params={merged_params}, force_ipv4={force_ipv4}")
                async with session.get(url, **kwargs) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"TMDB Upstream Error: {resp.status}, url={url}, response={text[:500]}")
                        raise TmdbProxyUpstreamError(resp.status, text[:500])
                    data = await resp.json()
                    if not isinstance(data, dict):
                        logger.error(f"TMDB Format Error: Not a dict, url={url}")
                        raise TmdbProxyUpstreamError(502, "TMDB 返回数据格式异常")
                    return data
            except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
                last_exc = e
                logger.error(f"TMDB Timeout Error: {str(e)}, url={url}, force_ipv4={force_ipv4}")
            except (aiohttp.ClientConnectorError, aiohttp.ClientOSError, aiohttp.ClientError) as e:
                last_exc = e
                logger.error(f"TMDB Connection Error: {str(e)}, url={url}, force_ipv4={force_ipv4}")

        if isinstance(last_exc, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)):
            raise TmdbProxyTimeoutError("TMDB 代理请求超时")
        if last_exc is not None:
            raise TmdbProxyError(f"无法连接到 TMDB 服务: {str(last_exc)}")
        raise TmdbProxyError("TMDB 请求失败")

    async def search_tv(self, q: str, page: int = 1, language: str = "zh-CN") -> Dict[str, Any]:
        data = await self._get_json(
            "/search/tv",
            params={
                "query": q,
                "page": page,
                "language": language,
            },
        )

        items = []
        for it in (data.get("results") or []):
            if not isinstance(it, dict):
                continue
            tmdb_id = it.get("id")
            if not isinstance(tmdb_id, int):
                continue
            items.append(
                {
                    "tmdb_id": tmdb_id,
                    "name": it.get("name") or "",
                    "original_name": it.get("original_name"),
                    "first_air_date": it.get("first_air_date"),
                    "origin_country": it.get("origin_country") or [],
                    "overview": it.get("overview"),
                    "poster_path": it.get("poster_path"),
                    "backdrop_path": it.get("backdrop_path"),
                }
            )

        return {
            "page": int(data.get("page") or page),
            "total_pages": int(data.get("total_pages") or 0),
            "total_results": int(data.get("total_results") or 0),
            "items": items,
        }

    async def search_movie(self, q: str, page: int = 1, language: str = "zh-CN") -> Dict[str, Any]:
        data = await self._get_json(
            "/search/movie",
            params={
                "query": q,
                "page": page,
                "language": language,
            },
        )

        items = []
        for it in (data.get("results") or []):
            if not isinstance(it, dict):
                continue
            tmdb_id = it.get("id")
            if not isinstance(tmdb_id, int):
                continue
            items.append(
                {
                    "tmdb_id": tmdb_id,
                    "title": it.get("title") or "",
                    "original_title": it.get("original_title"),
                    "release_date": it.get("release_date"),
                    "overview": it.get("overview"),
                    "poster_path": it.get("poster_path"),
                    "backdrop_path": it.get("backdrop_path"),
                }
            )

        return {
            "page": int(data.get("page") or page),
            "total_pages": int(data.get("total_pages") or 0),
            "total_results": int(data.get("total_results") or 0),
            "items": items,
        }

    async def get_tv_seasons(self, series_tmdb_id: int, language: str = "zh-CN") -> Dict[str, Any]:
        data = await self._get_json(
            f"/tv/{series_tmdb_id}",
            params={"language": language},
        )

        seasons = []
        for s in (data.get("seasons") or []):
            if not isinstance(s, dict):
                continue
            season_number = s.get("season_number")
            if not isinstance(season_number, int):
                continue
            seasons.append(
                {
                    "season_number": season_number,
                    "name": s.get("name") or "",
                    "episode_count": s.get("episode_count"),
                    "air_date": s.get("air_date"),
                    "poster_path": s.get("poster_path"),
                }
            )

        return {
            "tmdb_id": data.get("id") or series_tmdb_id,
            "name": data.get("name") or "",
            "seasons": seasons,
        }

    async def get_tv_season_episodes(
        self,
        series_tmdb_id: int,
        season_number: int,
        language: str = "zh-CN",
    ) -> Dict[str, Any]:
        data = await self._get_json(
            f"/tv/{series_tmdb_id}/season/{season_number}",
            params={"language": language},
        )

        episodes = []
        for ep in (data.get("episodes") or []):
            if not isinstance(ep, dict):
                continue
            episode_number = ep.get("episode_number")
            episode_tmdb_id = ep.get("id")
            if not isinstance(episode_number, int) or not isinstance(episode_tmdb_id, int):
                continue
            episodes.append(
                {
                    "episode_number": episode_number,
                    "episode_tmdb_id": episode_tmdb_id,
                    "name": ep.get("name") or "",
                    "air_date": ep.get("air_date"),
                    "overview": ep.get("overview"),
                    "still_path": ep.get("still_path"),
                    "runtime": ep.get("runtime"),
                }
            )

        return {
            "series_tmdb_id": series_tmdb_id,
            "season_number": season_number,
            "episodes": episodes,
        }


tmdb_proxy_service = TmdbProxyService()
