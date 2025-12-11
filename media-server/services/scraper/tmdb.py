import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict

import aiohttp

from core.config import get_settings
from .base import (
    MediaType,
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
    ArtworkType,
    CreditType,
)

logger = logging.getLogger(__name__)


class TmdbScraper(ScraperPlugin):
    def __init__(self):
        self._settings = get_settings()
        self._api_key = getattr(self._settings, "TMDB_API_KEY", None)
        self._v4_token = getattr(self._settings, "TMDB_V4_TOKEN", None)
        self._proxy = getattr(self._settings, "TMDB_PROXY", None)
        self._base_url = "https://api.themoviedb.org/3"
        self._image_base = "https://image.tmdb.org/t/p"
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        return "tmdb"

    @property
    def version(self) -> str:
        return "2.0.0"

    @property
    def description(self) -> str:
        return "The Movie Database (TMDB) 刮削器"

    @property
    def supported_media_types(self) -> List[MediaType]:
        return [MediaType.MOVIE, MediaType.TV_SERIES, MediaType.TV_SEASON, MediaType.TV_EPISODE]

    @property
    def default_language(self) -> str:
        return getattr(self._settings, "TMDB_LANGUAGE", "zh-CN")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _auth(self) -> Dict[str, any]:
        headers = {}
        params = {}
        if self._api_key:
            params["api_key"] = self._api_key
        elif self._v4_token:
            headers["Authorization"] = f"Bearer {self._v4_token}"
        return {"headers": headers, "params": params}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if not self._session:
            timeout = aiohttp.ClientTimeout(total=int(getattr(self._settings, "TMDB_TIMEOUT", 30)))
            self._session = aiohttp.ClientSession(timeout=timeout, trust_env=True)
        return self._session

    async def _get(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> aiohttp.ClientResponse:
        session = await self._ensure_session()
        merged_headers = {"Accept": "application/json"}
        if headers:
            merged_headers.update(headers)
        if self._proxy:
            return await session.get(url, params=params or {}, headers=merged_headers, proxy=self._proxy)
        return await session.get(url, params=params or {}, headers=merged_headers)

    async def startup(self) -> None:
        await self._ensure_session()

    async def shutdown(self) -> None:
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

    async def test_connection(self) -> bool:
        try:
            auth = self._auth()
            endpoints = [
                f"{self._base_url}/configuration",
                f"{self._base_url}/trending/movie/day",
                f"{self._base_url}/movie/550",
            ]
            for ep in endpoints:
                try:
                    async with await self._get(ep, params=auth["params"], headers=auth["headers"]) as resp:
                        if resp.status == 200:
                            return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    async def search(self, title: str, year: Optional[int], media_type: MediaType = MediaType.MOVIE, language: str = "zh-CN") -> List[ScraperSearchResult]:
        try:
            session = await self._ensure_session()
            auth = self._auth()
            params = {**auth["params"], "language": language, "query": title}
            url = f"{self._base_url}/search/movie" if media_type == MediaType.MOVIE else f"{self._base_url}/search/tv"
            if year is not None:
                if media_type == MediaType.MOVIE:
                    params["year"] = year
                else:
                    params["first_air_date_year"] = year
            async with await self._get(url, params=params, headers=auth["headers"]) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                # logger.info(f"TMDB search 结果元数据: {data.get('results', [])}")
                results = []
                for it in data.get("results", []) or []:
                    sr = self._convert_search_result(it, media_type, language)
                    if sr:
                        results.append(sr)
                results.sort(key=lambda x: (x.vote_average or 0, x.year or 0), reverse=True)
                return results
        except Exception:
            return []

    def _convert_search_result(self, it: Dict, media_type: MediaType, language: str) -> Optional[ScraperSearchResult]:
        """将 TMDB 搜索结果转换为 ScraperSearchResult 格式"""
        try:
            if media_type == MediaType.MOVIE:
                title = it.get("title") or ""
                original_title = it.get("original_title") or None
                release_date = it.get("release_date") or None
            else:
                title = it.get("name") or ""
                original_title = it.get("original_name") or None
                release_date = it.get("first_air_date") or None
            year = None
            if release_date and release_date.strip():
                try:
                    year = datetime.strptime(release_date[:10], "%Y-%m-%d").year
                except Exception:
                    year = None
            eid = str(it.get("id")) if it.get("id") is not None else None
            return ScraperSearchResult(
                id=eid,
                title=title,
                original_name=original_title if original_title != title else None,
                original_language=(it.get("original_language") or None),
                release_date=release_date,
                vote_average=it.get("vote_average"),
                vote_count=it.get("vote_count"),
                origin_country =[c for c in (it.get("origin_country") or [])] if media_type != MediaType.MOVIE else [],
                popularity=it.get("popularity"),
                provider=self.name,
                media_type=media_type.value,
                poster_path=(f"{self._image_base}/w500{it['poster_path']}" if it.get("poster_path") else None),
                backdrop_path=(f"{self._image_base}/w1280{it['backdrop_path']}" if it.get("backdrop_path") else None),
                year=year,
                provider_url=(f"https://www.themoviedb.org/{media_type.value}/{eid}" if eid else None),
            )
        except Exception:
            return None

    async def get_movie_details(self, movie_id: str, language: str = "zh-CN") -> Optional[ScraperMovieDetail]:
        """获取 TMDB 电影详情，包含外部ID、图像、演职员"""
        try:
            session = await self._ensure_session()
            auth = self._auth()
            params = {**auth["params"], "language": language, "append_to_response": "external_ids,images,credits"}
            url = f"{self._base_url}/movie/{movie_id}"
            async with session.get(url, params=params, headers=auth["headers"]) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return self._convert_movie_details(data, language)
        except Exception:
            return None

    def _convert_movie_details(self, data: Dict, language: str) -> Optional[ScraperMovieDetail]:
        """将 TMDB 电影详细信息转换为 ScraperMovieDetail 格式"""
        try:
            title = data.get("title") or ""
            original_title = data.get("original_title") or None
            release_date = data.get("release_date") or None
            eid = str(data.get("id")) if data.get("id") is not None else None
            external_ids: List[ScraperExternalId] = []
            if eid:
                external_ids.append(ScraperExternalId(provider="tmdb", external_id=eid, url=f"https://www.themoviedb.org/movie/{eid}"))
            imdb_id = data.get("imdb_id")
            if imdb_id:
                external_ids.append(ScraperExternalId(provider="imdb", external_id=imdb_id, url=f"https://www.imdb.com/title/{imdb_id}"))
            
            arts: List[ScraperArtwork] = []
            # 写入 tmdb 提供的海报和背景图
            imgs = data.get("images") or {}
            for poster in (imgs.get("posters") or [])[:5]:
                if poster.get("file_path"):
                    arts.append(ScraperArtwork(type=ArtworkType.POSTER, url=f"{self._image_base}/w500{poster['file_path']}", width=poster.get("width"), height=poster.get("height"), language=poster.get("iso_639_1"), rating=poster.get("vote_average"), vote_count=poster.get("vote_count")))
            for backdrop in (imgs.get("backdrops") or [])[:3]:
                if backdrop.get("file_path"):
                    arts.append(ScraperArtwork(type=ArtworkType.BACKDROP, url=f"{self._image_base}/w1280{backdrop['file_path']}", width=backdrop.get("width"), height=backdrop.get("height"), language=backdrop.get("iso_639_1"), rating=backdrop.get("vote_average"), vote_count=backdrop.get("vote_count")))
            credits: List[ScraperCredit] = []
            cr = data.get("credits") or {}
            for cast in cr.get("cast", [])[:20]:
                profile_path = cast.get("profile_path")
                image_url = f"{self._image_base}/w185{profile_path}" if profile_path else None
                provider_id = cast.get("id")
                # provider = self.name
                credits.append(ScraperCredit(type=CreditType.ACTOR, name=cast.get("name"), role=cast.get("character"), order=cast.get("order"), image_url=image_url, provider_id=provider_id))
            for crew in cr.get("crew", [])[:15]:
                job = (crew.get("job") or "").lower()
                ctype = CreditType.DIRECTOR if job == "director" else CreditType.WRITER if job == "writer" else CreditType.PRODUCER if job == "producer" else CreditType.ACTOR
                profile_path = crew.get("profile_path")
                image_url = f"{self._image_base}/w185{profile_path}" if profile_path else None
                provider_id = crew.get("id")
                # provider = self.name
                credits.append(ScraperCredit(type=ctype, name=crew.get("name"), role=None, order=None, image_url=image_url, provider_id=provider_id))
            md = ScraperMovieDetail(
                movie_id=eid or "",
                title=title,
                original_title=original_title if original_title != title else None,
                original_language=(data.get("original_language") or None),
                origin_country =[c for c in (data.get("origin_country") or [])],
                overview=data.get("overview"),
                release_date=release_date,
                runtime=data.get("runtime"),
                tagline=data.get("tagline"),
                genres=[g.get("name") for g in (data.get("genres") or []) if g.get("name")],
                poster_path=(f"{self._image_base}/w500{data['poster_path']}" if data.get("poster_path") else None),
                backdrop_path=(f"{self._image_base}/w1280{data['backdrop_path']}" if data.get("backdrop_path") else None),
                vote_average=data.get("vote_average"),
                vote_count=data.get("vote_count"),
                imdb_id=data.get("imdb_id"),
                status=data.get("status"),
                belongs_to_collection=(data.get("belongs_to_collection") or None),
                popularity=data.get("popularity"),
                provider=self.name,
                provider_url=(f"https://www.themoviedb.org/movie/{eid}" if eid else None),
                artworks=arts,
                credits=credits,
                external_ids=external_ids,
                raw_data=data,
            )
            return md
        except Exception:
            return None

    async def get_series_details(self, series_id: str, language: str = "zh-CN") -> Optional[ScraperSeriesDetail]:
        try:
            session = await self._ensure_session()
            auth = self._auth()
            params = {**auth["params"], "language": language, "append_to_response": "external_ids,images,credits"}
            url = f"{self._base_url}/tv/{series_id}"
            async with session.get(url, params=params, headers=auth["headers"]) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                eid = str(data.get("id")) if data.get("id") is not None else None
                external_ids: List[ScraperExternalId] = []
                if eid:
                    external_ids.append(ScraperExternalId(provider="tmdb", external_id=eid, url=f"https://www.themoviedb.org/tv/{eid}"))
                tvdb_id = (data.get("external_ids") or {}).get("tvdb_id") if isinstance(data.get("external_ids"), dict) else None
                if tvdb_id:
                    external_ids.append(ScraperExternalId(provider="tvdb", external_id=str(tvdb_id), url=f"https://thetvdb.com/?tab=series&id={tvdb_id}"))
                arts: List[ScraperArtwork] = []
                imgs = data.get("images") or {}
                for poster in (imgs.get("posters") or [])[:5]:
                    if poster.get("file_path"):
                        arts.append(ScraperArtwork(type=ArtworkType.POSTER, url=f"{self._image_base}/w500{poster['file_path']}", width=poster.get("width"), height=poster.get("height"), language=poster.get("iso_639_1"), rating=poster.get("vote_average"), vote_count=poster.get("vote_count")))
                for backdrop in (imgs.get("backdrops") or [])[:3]:
                    if backdrop.get("file_path"):
                        arts.append(ScraperArtwork(type=ArtworkType.BACKDROP, url=f"{self._image_base}/w1280{backdrop['file_path']}", width=backdrop.get("width"), height=backdrop.get("height"), language=backdrop.get("iso_639_1"), rating=backdrop.get("vote_average"), vote_count=backdrop.get("vote_count")))
                credits: List[ScraperCredit] = []
                cr = data.get("credits") or {}
                for cast in cr.get("cast", [])[:20]:
                    profile_path = cast.get("profile_path")
                    image_url = f"{self._image_base}/w185{profile_path}" if profile_path else None
                    credits.append(ScraperCredit(type=CreditType.ACTOR, name=cast.get("name"), role=cast.get("character"), order=cast.get("order"), image_url=image_url))
                for crew in cr.get("crew", [])[:15]:
                    job = (crew.get("job") or "").lower()
                    ctype = CreditType.DIRECTOR if job == "director" else CreditType.WRITER if job == "writer" else CreditType.PRODUCER if job == "producer" else CreditType.ACTOR
                    profile_path = crew.get("profile_path")
                    image_url = f"{self._image_base}/w185{profile_path}" if profile_path else None
                    credits.append(ScraperCredit(type=ctype, name=crew.get("name"), role=None, order=None, image_url=image_url))
                sd = ScraperSeriesDetail(
                    series_id=eid or "",
                    name=data.get("name") or "",
                    original_name=(data.get("original_name") or None),
                    origin_country=[c for c in (data.get("origin_country") or [])],
                    overview=data.get("overview"),
                    tagline=data.get("tagline"),
                    status=data.get("status"),
                    first_air_date=data.get("first_air_date"),
                    last_air_date=data.get("last_air_date"),
                    episode_run_time=[int(x) for x in (data.get("episode_run_time") or []) if isinstance(x, (int, float))],
                    number_of_episodes=data.get("number_of_episodes"),
                    number_of_seasons=data.get("number_of_seasons"),
                    genres=[g.get("name") for g in (data.get("genres") or []) if g.get("name")],
                    poster_path=(f"{self._image_base}/w500{data['poster_path']}" if data.get("poster_path") else None),
                    backdrop_path=(f"{self._image_base}/w1280{data['backdrop_path']}" if data.get("backdrop_path") else None),
                    vote_average=data.get("vote_average"),
                    vote_count=data.get("vote_count"),
                    popularity=data.get("popularity"),
                    provider=self.name,
                    provider_url=(f"https://www.themoviedb.org/tv/{eid}" if eid else None),
                    artworks=arts,
                    credits=credits,
                    external_ids=external_ids,
                    raw_data=data,
                    type=data.get("type")
                )
                return sd
        except Exception:
            return None

    async def get_season_details(self, series_id: str, season_number: int, language: str = "zh-CN") -> Optional[ScraperSeasonDetail]:
        try:
            session = await self._ensure_session()
            auth = self._auth()
            params = {**auth["params"], "language": language}
            url = f"{self._base_url}/tv/{series_id}/season/{season_number}"
            async with await self._get(url, params=params, headers=auth["headers"]) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                episodes: List[ScraperEpisodeItem] = []
                for ep in data.get("episodes", []) or []:
                    episodes.append(ScraperEpisodeItem(
                        episode_id=str(ep.get("id")) if ep.get("id") else None,
                        episode_number=ep.get("episode_number") or 0,
                        season_number=season_number,
                        name=ep.get("name") or "",
                        overview=ep.get("overview"),
                        air_date=ep.get("air_date"),
                        runtime=ep.get("runtime"),
                        still_path=ep.get("still_path"),
                        vote_average=ep.get("vote_average"),
                        vote_count=ep.get("vote_count"),
                    ))
                sd = ScraperSeasonDetail(
                    season_id=str(data.get("id")) if data.get("id") else None,
                    season_number=season_number,
                    name=data.get("name"),
                    poster_path=(f"{self._image_base}/w500{data['poster_path']}" if data.get("poster_path") else None),
                    overview=data.get("overview"),
                    episode_count=len(episodes),
                    air_date=data.get("air_date"),
                    episodes=episodes,
                    vote_average=data.get("vote_average"),
                    provider=self.name,
                    provider_url=url,
                    artworks=(
                        [ScraperArtwork(type=ArtworkType.POSTER, url=f"{self._image_base}/w500{data['poster_path']}", language=language)]
                        if data.get("poster_path") else []
                    ),
                    credits=[],
                    external_ids=[],
                    raw_data=data,
                )
                return sd
        except Exception:
            return None

    async def get_episode_details(self, series_id: str, season_number: int, episode_number: int, language: str = "zh-CN") -> Optional[ScraperEpisodeDetail]:
        try:
            session = await self._ensure_session()
            auth = self._auth()
            params = {**auth["params"], "language": language}
            url = f"{self._base_url}/tv/{series_id}/season/{season_number}/episode/{episode_number}"
            async with await self._get(url, params=params, headers=auth["headers"]) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                air_date = data.get("air_date")
                title = data.get("name") or ""
                ed = ScraperEpisodeDetail(
                    episode_id=str(data.get("id")) if data.get("id") else None,
                    episode_number=episode_number,
                    season_number=season_number,
                    name=title,
                    overview=data.get("overview"),
                    air_date=air_date,
                    runtime=data.get("runtime"),
                    still_path=(f"{self._image_base}/w500{data['still_path']}" if data.get("still_path") else None),
                    vote_average=data.get("vote_average"),
                    vote_count=data.get("vote_count"),
                    provider=self.name,
                    provider_url=url,
                    artworks=(
                        [ScraperArtwork(type=ArtworkType.THUMB, url=f"{self._image_base}/w500{data['still_path']}", language=language)]
                        if data.get("still_path") else []
                    ),
                    credits=[],
                    external_ids=[ScraperExternalId(provider="tmdb", external_id=str(data.get("id"))) ] if data.get("id") else [],
                    raw_data=data,
                    episode_type=data.get("episode_type")
                )
                return ed
        except Exception:
            return None
