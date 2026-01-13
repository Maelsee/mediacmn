from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from core.security import get_current_subject
from schemas.tmdb_proxy import (
    TmdbSearchMovieResponse,
    TmdbSearchTvResponse,
    TmdbTvSeasonsResponse,
    TmdbSeasonEpisodesResponse,
)
from services.tmdb_proxy_service import (
    TmdbProxyError,
    TmdbProxyNotConfiguredError,
    TmdbProxyTimeoutError,
    TmdbProxyUpstreamError,
    tmdb_proxy_service,
)

router = APIRouter()


@router.get("/search/tv", response_model=TmdbSearchTvResponse)
async def tmdb_search_tv(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    language: str = Query("zh-CN"),
    _: str = Depends(get_current_subject),
):
    try:
        return await tmdb_proxy_service.search_tv(q=q, page=page, language=language)
    except TmdbProxyNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TmdbProxyUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.message)
    except TmdbProxyTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except TmdbProxyError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/movie", response_model=TmdbSearchMovieResponse)
async def tmdb_search_movie(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    language: str = Query("zh-CN"),
    _: str = Depends(get_current_subject),
):
    try:
        return await tmdb_proxy_service.search_movie(q=q, page=page, language=language)
    except TmdbProxyNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TmdbProxyUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.message)
    except TmdbProxyTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except TmdbProxyError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tv/{series_tmdb_id}", response_model=TmdbTvSeasonsResponse)
async def tmdb_tv_seasons(
    series_tmdb_id: int = Path(..., ge=1),
    language: str = Query("zh-CN"),
    _: str = Depends(get_current_subject),
):
    try:
        return await tmdb_proxy_service.get_tv_seasons(series_tmdb_id=series_tmdb_id, language=language)
    except TmdbProxyNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TmdbProxyUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.message)
    except TmdbProxyTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except TmdbProxyError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tv/{series_tmdb_id}/season/{season_number}", response_model=TmdbSeasonEpisodesResponse)
async def tmdb_tv_season_episodes(
    series_tmdb_id: int = Path(..., ge=1),
    season_number: int = Path(..., ge=0),
    language: str = Query("zh-CN"),
    _: str = Depends(get_current_subject),
):
    try:
        return await tmdb_proxy_service.get_tv_season_episodes(
            series_tmdb_id=series_tmdb_id,
            season_number=season_number,
            language=language,
        )
    except TmdbProxyNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TmdbProxyUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.message)
    except TmdbProxyTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except TmdbProxyError as e:
        raise HTTPException(status_code=500, detail=str(e))
