from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from core.db import get_session
from core.security import get_current_subject
from services.media.media_service import MediaService
from models.media_models import FileAsset
from models.storage_models import StorageConfig, WebdavStorageConfig
import base64
from core.config import get_settings
import time
from schemas.media_serialization import HomeCardsResponse, FilterCardsResponse, MediaDetailResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
media_service = MediaService()


@router.get("/cards", response_model=FilterCardsResponse)
def filter_media_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
    q: Optional[str] = Query(None, description="关键字"),
    type: Optional[str] = Query(None, description="movie|tv"),
    genres: Optional[str] = Query(None, description="逗号分隔的分类"),
    year: Optional[int] = Query(None),
    year_start: Optional[int] = Query(None),
    year_end: Optional[int] = Query(None),
    countries: Optional[str] = Query(None, description="逗号分隔的地区"),
    sort: Optional[str] = Query(None, description="updated|released|added|rating"),
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """
    过滤卡片
    - req:
        - page: int
        - page_size: int
        - q: Optional[str]
        - type: Optional[str] = Query(None, description="movie|tv")
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
    return media_service.filter_media_cards(
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
def list_home_cards(
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """
    首页卡片
    - resp: 
        - HomeCardsResponse
    """
    user_id = int(current_subject)
    return media_service.list_media_cards(db=db, user_id=user_id)


@router.get("/{id}/detail", response_model=MediaDetailResponse)
def media_detail(
    id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """
    媒体详情
    
    """
    user_id = int(current_subject)
    return media_service.get_media_detail(db=db, user_id=user_id, core_id=id)


def _compose_playinfo_inline(db: Session, fa: FileAsset) -> dict:
    source_type = None
    playurl = None
    try:
        sc = db.exec(select(StorageConfig).where(StorageConfig.id == fa.storage_id)).first() if fa.storage_id else None
        source_type = getattr(sc, 'storage_type', None)
        if source_type == 'webdav':
            wc = db.exec(select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == sc.id)).first() if sc else None
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
            wc = db.exec(select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == fa.storage_id)).first()
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
def get_play_url(
    file_id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    user_id = int(current_subject)
    fa = db.exec(
        select(FileAsset).where(FileAsset.id == file_id, FileAsset.user_id == user_id)
    ).first()
    if not fa:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": "文件不存在或无权限"})
    info = _compose_playinfo_inline(db, fa)
    url = (info or {}).get("playurl")
    if not url:
        raise HTTPException(status_code=400, detail={"code": "compose_playurl_failed", "message": "无法生成播放链接"})
    return info


class RefreshPlayRequest(BaseModel):
    file_id: int

@router.post("/play/refresh")
def refresh_play_url(
    req: RefreshPlayRequest,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    user_id = int(current_subject)
    fa = db.exec(
        select(FileAsset).where(FileAsset.id == req.file_id, FileAsset.user_id == user_id)
    ).first()
    if not fa:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": "文件不存在或无权限"})
    info = _compose_playinfo_inline(db, fa)
    if not info or not info.get("playurl"):
        raise HTTPException(status_code=400, detail={"code": "compose_playurl_failed", "message": "无法生成播放链接"})
    return info
