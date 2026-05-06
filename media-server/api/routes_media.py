from __future__ import annotations

from typing import Optional, List, Dict, Any, Literal

from fastapi import APIRouter, Depends, Query, HTTPException, Path, Body
from pydantic import BaseModel, conint, Field
from sqlmodel import Session, select, and_
from sqlmodel.ext.asyncio.session import AsyncSession
from core.db import get_async_session
from core.security import get_current_subject
from services.media.media_service import MediaService
from models.media_models import FileAsset, MediaCore, MediaVersion, EpisodeExt
from models.storage_models import StorageConfig, WebdavStorageConfig
import base64
from core.config import get_settings
import time
from datetime import datetime
from schemas.media_serialization import HomeCardsResponse, FilterCardsResponse, MediaDetailResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
media_service = MediaService()


@router.get("/cards", response_model=FilterCardsResponse)
async def filter_media_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
    q: Optional[str] = Query(None, description="关键字"),
    type: Optional[str] = Query(None, description="movie|tv|animation|reality"),
    genres: Optional[str] = Query(None, description="逗号分隔的分类"),
    year: Optional[int] = Query(None),
    year_start: Optional[int] = Query(None),
    year_end: Optional[int] = Query(None),
    countries: Optional[str] = Query(None, description="逗号分隔的地区"),
    sort: Optional[str] = Query(None, description="updated|released|added|rating"),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    """
    过滤卡片
    - req:
        - page: int
        - page_size: int
        - q: Optional[str]
        - type: Optional[str] = Query(None, description="movie|tv|animation|reality")
        - genres: Optional[str]
        - year: Optional[int]
        - year_start: Optional[int]
        - year_end: Optional[int]
        - countries: Optional[str]
    - resp: 
        - FilterCardsResponse
    """
    user_id = int(current_subject)
    genres_list = genres.split(",") if genres else None
    countries_list = countries.split(",") if countries else None
    return await media_service.filter_media_cards(
        db=db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        q=q,
        type_filter=type,
        genres=genres_list,
        year=year,
        year_start=year_start,
        year_end=year_end,
        countries=countries_list,
        sort=sort,
    )

@router.get("/cards/home", response_model=HomeCardsResponse)
async def list_home_cards(
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    """
    首页卡片
    - resp: 
        - HomeCardsResponse
    """
    user_id = int(current_subject)
    return await media_service.list_media_cards(db=db, user_id=user_id)


@router.get("/{id}/detail", response_model=MediaDetailResponse)
async def media_detail(
    id: int = Path(..., ge=1, le=2147483647),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    """
    媒体详情
    - 若找不到对应媒体，返回 404 而不是响应校验错误
    """
    user_id = int(current_subject)
    detail = await media_service.get_media_detail(db=db, user_id=user_id, core_id=id)
    if not detail or detail.get("error") in {"not_found", "series_not_found"}:
        raise HTTPException(
            status_code=404,
            detail={"code": "media_not_found", "message": "媒体不存在或无权限"},
        )
    if detail.get("error"):
        raise HTTPException(
            status_code=400,
            detail={"code": "media_detail_error", "message": detail.get("error")},
        )
    return detail


async def _compose_playinfo_inline(db: AsyncSession, fa: FileAsset) -> dict:
    source_type = None
    playurl = None
    try:
        sc = (await db.exec(select(StorageConfig).where(StorageConfig.id == fa.storage_id))).first() if fa.storage_id else None
        source_type = getattr(sc, 'storage_type', None)
        if source_type == 'webdav':
            wc = (await db.exec(select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == sc.id))).first() if sc else None
            head = (getattr(wc, 'hostname', '') or '').rstrip('/') if wc else ''
            path = (getattr(fa, 'full_path', '') or '')
            try:
                if path.startswith('`') and path.endswith('`'):
                    path = path[1:-1].strip()
            except Exception:
                pass
            # 确保以 / 开头，直接使用 hostname + full_path
            path = '/' + path.lstrip('/')
            try:
                from urllib.parse import quote
                path = quote(path, safe='/') if path else path
            except Exception:
                pass
            try:
                if head.startswith('`') and head.endswith('`'):
                    head = head[1:-1].strip()
            except Exception:
                pass
            playurl = f"{head}{path}" if head and path else None
    except Exception:
        playurl = None
    if not playurl:
        return {}
    headers = None
    try:
        if source_type == 'webdav' and fa.storage_id:
            wc = (await db.exec(select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == fa.storage_id))).first()
            if wc and getattr(wc, 'login', None) and getattr(wc, 'password', None):
                token = base64.b64encode(f"{wc.login}:{wc.password}".encode('utf-8')).decode('utf-8')
                headers = {"Authorization": f"Basic {token}"}
    except Exception:
        headers = None
    fmt = 'file'
    try:
        fn = (getattr(fa, 'filename', None) or '').lower()
        if fn.endswith('.m3u8'):
            fmt = 'hls_master'
        elif fn.endswith('.mpd'):
            fmt = 'dash'
    except Exception:
        pass
    expires_at = None
    try:
        settings = get_settings()
        if getattr(settings, 'URL_SIGNING_SECRET', None):
            ttl = int(getattr(settings, 'URL_SIGNING_TTL_SECONDS', 300))
            expires_at = int(time.time()) + ttl
    except Exception:
        expires_at = None
    return {
        'file_id': fa.id,
        'playurl': playurl,
        'headers': headers,
        'expires_at': expires_at,
        'format': fmt,
        'source_type': source_type,
    }


@router.get("/play/{file_id}")
async def get_play_url(
    file_id: int = Path(..., ge=1, le=2147483647),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = int(current_subject)
    fa = (await db.exec(
        select(FileAsset).where(FileAsset.id == file_id, FileAsset.user_id == user_id)
    )).first()
    if not fa:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": "文件不存在或无权限"})
    info = await _compose_playinfo_inline(db, fa)
    url = (info or {}).get("playurl")
    if not url:
        raise HTTPException(status_code=400, detail={"code": "compose_playurl_failed", "message": "无法生成播放链接"})
    return info


class SubtitleItem(BaseModel):
    id: str
    name: str
    path: str
    size: Optional[int] = None
    size_text: Optional[str] = None
    language: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    storage_type: Optional[str] = None


class SubtitleListResponse(BaseModel):
    file_id: int
    items: List[SubtitleItem] = Field(default_factory=list)


class SubtitleContentResponse(BaseModel):
    file_id: int
    path: str
    content: str

class EpisodeAssetItem(BaseModel):
    file_id: int
    path: str
    size: Optional[int] = None
    size_text: Optional[str] = None
    language: Optional[str] = None


class EpisodeItem(BaseModel):
    id: int
    episode_number: int
    title: str
    still_path: Optional[str] = None
    assets: List[EpisodeAssetItem] = Field(default_factory=list)


class EpisodeListResponse(BaseModel):
    file_id: int
    season_version_id: Optional[int] = None
    episodes: List[EpisodeItem] = Field(default_factory=list)


@router.get("/file/{file_id}/subtitles", response_model=SubtitleListResponse)
async def list_file_subtitles(
    file_id: int = Path(..., ge=1, le=2147483647),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = int(current_subject)
    asset = (
        await db.exec(
            select(FileAsset).where(
                and_(FileAsset.id == file_id, FileAsset.user_id == user_id)
            )
        )
    ).first()
    if not asset:
        raise HTTPException(
            status_code=404,
            detail={"code": "file_not_found", "message": "文件不存在或无权限"},
        )

    result = await media_service.get_file_subtitles(db=db, user_id=user_id, asset=asset)
    return result


@router.get("/file/{file_id}/subtitles/content", response_model=SubtitleContentResponse)
async def get_subtitle_content(
    file_id: int = Path(..., ge=1, le=2147483647),
    path: str = Query(..., description="字幕文件路径（与列表接口中的 path 一致）"),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = int(current_subject)
    asset = (
        await db.exec(
            select(FileAsset).where(
                and_(FileAsset.id == file_id, FileAsset.user_id == user_id)
            )
        )
    ).first()
    if not asset:
        raise HTTPException(
            status_code=404,
            detail={"code": "file_not_found", "message": "文件不存在或无权限"},
        )

    try:
        content = await media_service.download_subtitle_content(
            db=db, user_id=user_id, asset=asset, subtitle_path=path
        )
    except Exception as e:
        logger.error(f"下载字幕失败 file_id={file_id}, path={path}: {e}")
        raise HTTPException(
            status_code=502,
            detail={"code": "subtitle_download_failed", "message": "下载字幕文件失败"},
        )

    return SubtitleContentResponse(file_id=file_id, path=path, content=content)


@router.get("/file/{file_id}/episodes", response_model=EpisodeListResponse)
async def list_file_episodes(
    file_id: int = Path(..., ge=1, le=2147483647),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = int(current_subject)
    asset = (
        await db.exec(
            select(FileAsset).where(
                and_(FileAsset.id == file_id, FileAsset.user_id == user_id)
            )
        )
    ).first()
    if not asset:
        raise HTTPException(
            status_code=404,
            detail={"code": "file_not_found", "message": "文件不存在或无权限"},
        )

    result = await media_service.get_file_episode_list(
        db=db, user_id=user_id, asset=asset
    )
    return result


class RefreshPlayRequest(BaseModel):
    file_id: conint(ge=1, le=2147483647)

@router.post("/play/refresh")
async def refresh_play_url(
    req: RefreshPlayRequest,
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = int(current_subject)
    fa = (await db.exec(
        select(FileAsset).where(FileAsset.id == req.file_id, FileAsset.user_id == user_id)
    )).first()
    if not fa:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": "文件不存在或无权限"})
    info = await _compose_playinfo_inline(db, fa)
    if not info or not info.get("playurl"):
        raise HTTPException(status_code=400, detail={"code": "compose_playurl_failed", "message": "无法生成播放链接"})
    return info


class ManualMatchTarget(BaseModel):
    local_media_id: int = Field(..., ge=1, le=2147483647)
    local_media_version_id: Optional[int] = Field(default=None, ge=1, le=2147483647)
    type: Literal["tv", "movie"]
    provider: Literal["tmdb"]

    tmdb_tv_id: Optional[int] = Field(default=None, ge=1, le=2147483647)
    season_number: Optional[int] = Field(default=None, ge=0, le=1000)
    tmdb_season_id: Optional[int] = Field(default=None, ge=1, le=2147483647)

    tmdb_movie_id: Optional[int] = Field(default=None, ge=1, le=2147483647)


class ManualMatchItem(BaseModel):
    file_id: int = Field(..., ge=1, le=2147483647)
    action: Literal["bind_episode", "bind_movie", "keep", "other"]
    tmdb: Optional[Dict[str, Any]] = None


class ManualMatchRequest(BaseModel):
    target: ManualMatchTarget
    items: List[ManualMatchItem] = Field(default_factory=list)
    client_request_id: Optional[str] = None


class ManualMatchError(BaseModel):
    file_id: int
    code: str
    message: str


class ManualMatchResponse(BaseModel):
    success: bool
    effective_media_id: int
    task_id: Optional[str] = None
    accepted: int
    updated: int
    skipped: int
    errors: List[ManualMatchError] = Field(default_factory=list)


def _file_matches_target(file: FileAsset, target: ManualMatchTarget) -> bool:
    if not target.local_media_version_id:
        return True
    if target.type == "tv":
        return int(getattr(file, "season_version_id", 0) or 0) == int(target.local_media_version_id)
    if target.type == "movie":
        if int(getattr(file, "version_id", 0) or 0) == int(target.local_media_version_id):
            return True
        return int(getattr(file, "core_id", 0) or 0) == int(target.local_media_id)
    return False


@router.put("/{media_id}/manual-match", response_model=ManualMatchResponse)
async def manual_match(
    media_id: int = Path(..., ge=1, le=2147483647),
    body: ManualMatchRequest = Body(...),
    current_subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = int(current_subject)
    logger.info(f"手动匹配请求 media_id={media_id}, target={body.target}, items={body.items}")
    # if body.target.local_media_id != media_id:
    #     raise HTTPException(
    #         status_code=400,
    #         detail={"code": "media_id_mismatch", "message": "路径 media_id 与请求体 local_media_id 不一致"},
    #     )
    media = (
        await db.exec(
            select(MediaCore).where(MediaCore.id == media_id, MediaCore.user_id == user_id)
        )
    ).first()
    if not media:
        raise HTTPException(
            status_code=404,
            detail={"code": "media_not_found", "message": "媒体不存在或无权限"},
        )

    from services.scraper.base import MediaType, ScraperSearchResult
    from services.scraper import scraper_manager
    from services.task.producer import create_persist_batch_task

    accepted = len(body.items or [])
    updated = 0
    errors: List[ManualMatchError] = []
    persist_items: List[Dict[str, Any]] = []
    task_id: Optional[str] = None

    for it in body.items or []:
        file_asset = (
            await db.exec(
                select(FileAsset).where(
                    FileAsset.id == it.file_id,
                    FileAsset.user_id == user_id,
                )
            )
        ).first()
        if not file_asset:
            errors.append(
                ManualMatchError(
                    file_id=it.file_id,
                    code="file_not_found",
                    message="文件不存在或无权限",
                )
            )
            continue
        if not _file_matches_target(file_asset, body.target):
            errors.append(
                ManualMatchError(
                    file_id=it.file_id,
                    code="file_not_in_media",
                    message="文件不属于该媒体",
                )
            )
            continue
        if it.action in {"keep", "other"}:
            continue

        if it.action == "bind_movie":
            if body.target.type != "movie":
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="invalid_action",
                        message="当前 target 不支持该 action",
                    )
                )
                continue
            tmdb_movie_id = None
            if isinstance(it.tmdb, dict):
                tmdb_movie_id = it.tmdb.get("tmdb_movie_id")
            if not isinstance(tmdb_movie_id, int):
                tmdb_movie_id = body.target.tmdb_movie_id
            if not isinstance(tmdb_movie_id, int):
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="missing_tmdb_id",
                        message="缺少 tmdb_movie_id",
                    )
                )
                continue
            best_match = ScraperSearchResult(
                id=tmdb_movie_id,
                title="manual_match",
                provider="tmdb",
                media_type=MediaType.MOVIE.value,
            )
            contract_type, details_obj = await scraper_manager.get_detail(
                best_match=best_match,
                media_type=MediaType.MOVIE,
                language="zh-CN",
            )
            if contract_type != "movie" or not details_obj:
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="tmdb_detail_not_found",
                        message="无法获取 TMDB 电影详情",
                    )
                )
                continue
            persist_items.append(
                {
                    "file_id": it.file_id,
                    "contract_type": "movie",
                    "contract_payload": details_obj.model_dump(),
                    "path_info": {},
                }
            )
            updated += 1
            continue

        if it.action == "bind_episode":
            if body.target.type != "tv":
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="invalid_action",
                        message="当前 target 不支持该 action",
                    )
                )
                continue
            tmdb_tv_id = body.target.tmdb_tv_id
            season_number = body.target.season_number
            episode_number = None
            if isinstance(it.tmdb, dict):
                if isinstance(it.tmdb.get("tmdb_tv_id"), int):
                    tmdb_tv_id = it.tmdb.get("tmdb_tv_id")
                if isinstance(it.tmdb.get("season_number"), int):
                    season_number = it.tmdb.get("season_number")
                episode_number = it.tmdb.get("episode_number")
            if not isinstance(tmdb_tv_id, int) or not isinstance(season_number, int):
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="missing_tmdb_id",
                        message="缺少 tmdb_tv_id 或 season_number",
                    )
                )
                continue
            if not isinstance(episode_number, int):
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="missing_episode_number",
                        message="缺少 episode_number",
                    )
                )
                continue
            best_match = ScraperSearchResult(
                id=tmdb_tv_id,
                title="manual_match",
                provider="tmdb",
                media_type=MediaType.TV_SERIES.value,
            )
            contract_type, details_obj = await scraper_manager.get_detail(
                best_match=best_match,
                media_type=MediaType.TV_EPISODE,
                season=season_number,
                episode=episode_number,
                language="zh-CN",
            )
            if contract_type != "episode" or not details_obj:
                errors.append(
                    ManualMatchError(
                        file_id=it.file_id,
                        code="tmdb_detail_not_found",
                        message="无法获取 TMDB 单集详情",
                    )
                )
                continue
            persist_items.append(
                {
                    "file_id": it.file_id,
                    "contract_type": "episode",
                    "contract_payload": details_obj.model_dump(),
                    "path_info": {},
                }
            )
            updated += 1
            continue

    if persist_items:
        logger.info(f"手动匹配入队 {len(persist_items)} 项")
        idempotency_key = f"persist_batch:{user_id}:{body.client_request_id}"
        task_id = await create_persist_batch_task(
            user_id=user_id,
            items=persist_items,
            idempotency_key=idempotency_key,
        )
        logger.info(f"手动匹配入队任务 {task_id}")

    skipped = accepted - updated - len(errors)
    if skipped < 0:
        skipped = 0

    return ManualMatchResponse(
        success=True,
        effective_media_id=media_id,
        task_id=task_id,
        accepted=accepted,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )


@router.get("/metrics/enricher")
async def get_enricher_metrics(
    current_user: str = Depends(get_current_subject),
):
    """获取元数据丰富器性能指标"""
    from services.media.metrics import get_metrics_summary
    return await get_metrics_summary()


@router.get("/failed-parses")
async def list_failed_parses(
    limit: int = Query(50, ge=1, le=500),
    resolved: Optional[bool] = Query(None),
    current_user: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_async_session),
):
    """查询失败解析记录"""
    from models.media_models import FailedParse
    user_id = int(current_user)
    stmt = select(FailedParse).where(FailedParse.user_id == user_id)
    if resolved is not None:
        stmt = stmt.where(FailedParse.resolved == resolved)
    stmt = stmt.order_by(FailedParse.created_at.desc()).limit(limit)
    result = await db.exec(stmt)
    rows = result.all()
    return [
        {
            "id": r.id,
            "file_path": r.file_path,
            "file_asset_id": r.file_asset_id,
            "error_message": r.error_message,
            "search_attempts": r.search_attempts,
            "resolved": r.resolved,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
