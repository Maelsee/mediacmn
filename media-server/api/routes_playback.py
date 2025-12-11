from __future__ import annotations

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from sqlmodel import and_

from core.db import get_session
from core.security import get_current_subject
from models.media_models import PlaybackHistory, FileAsset, MediaCore, MovieExt, SeriesExt, EpisodeExt, SeasonExt, Artwork

router = APIRouter()


class ProgressReport(BaseModel):
    file_id: int = Field(..., description="文件资产ID")
    core_id: Optional[int] = None
    position_ms: int = 0
    duration_ms: Optional[int] = None
    media_type: Optional[str] = None
    series_core_id: Optional[int] = None
    season_core_id: Optional[int] = None
    episode_core_id: Optional[int] = None
    version_id: Optional[int] = None
    status: Optional[str] = None
    device_id: Optional[str] = None
    platform: Optional[str] = None


@router.post("/progress")
def report_progress(
    payload: ProgressReport,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    user_id = int(current_subject)
    fa = db.exec(select(FileAsset).where(and_(FileAsset.id == payload.file_id, FileAsset.user_id == user_id))).first()
    if not fa:
        raise HTTPException(status_code=404, detail={"code": "file_not_found"})
    rec = db.exec(select(PlaybackHistory).where(and_(PlaybackHistory.user_id == user_id, PlaybackHistory.file_asset_id == fa.id))).first()
    if rec is None:
        rec = PlaybackHistory(user_id=user_id, file_asset_id=fa.id)
    rec.core_id = payload.core_id or fa.core_id
    rec.media_type = payload.media_type
    rec.series_core_id = payload.series_core_id
    rec.season_core_id = payload.season_core_id
    rec.episode_core_id = payload.episode_core_id
    rec.version_id = payload.version_id or fa.version_id
    rec.position_ms = max(0, int(payload.position_ms or 0))
    rec.duration_ms = payload.duration_ms
    rec.status = payload.status
    rec.device_id = payload.device_id
    rec.platform = payload.platform
    from utils.time_compat import get_utc_now_factory
    now = get_utc_now_factory()()
    if rec.started_at is None:
        rec.started_at = now
    rec.updated_at = now
    if payload.status == "completed":
        rec.finished_at = now
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"success": True}


@router.get("/progress/{file_id}")
def read_progress(
    file_id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    user_id = int(current_subject)
    rec = db.exec(select(PlaybackHistory).where(and_(PlaybackHistory.user_id == user_id, PlaybackHistory.file_asset_id == file_id))).first()
    if not rec:
        return {"position_ms": 0, "duration_ms": None}
    return {
        "position_ms": rec.position_ms,
        "duration_ms": rec.duration_ms,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


class RecentCardItem(BaseModel):
    id: int
    name: str
    cover_url: Optional[str] = None
    media_type: str
    position_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    file_id: Optional[int] = None


@router.get("/recent", response_model=List[RecentCardItem])
def recent_list(
    limit: int = Query(20, ge=1, le=200),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=200),
    sort: str = Query("updated_desc"),
    dedup: str = Query("series", description="去重维度：core|series|episode"),
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    user_id = int(current_subject)
    order_clause = PlaybackHistory.updated_at.desc() if sort != "updated_asc" else PlaybackHistory.updated_at.asc()
    base_limit = max(200, (page or 1) * (page_size or limit) * 3)
    rows = db.exec(
        select(PlaybackHistory)
        .where(PlaybackHistory.user_id == user_id)
        .order_by(order_clause)
        .limit(base_limit)
    ).all()
    seen: set[int] = set()
    all_items: List[RecentCardItem] = []
    for r in rows:
        file_id = r.file_asset_id
        core_id = r.core_id
        
        fa = db.exec(
            select(FileAsset).where(
                and_(FileAsset.id == file_id, FileAsset.user_id == user_id)
            )
        ).first()
        if not core_id:
            continue

        core = db.exec(
            select(MediaCore).where(and_(MediaCore.user_id == user_id, MediaCore.id == core_id))
        ).first()
        if not core:
            continue

        cover_url = None
        key: int
        if fa.core_id == core.id:
            # 电影
            me = db.exec(
                select(MovieExt).where(
                    and_(MovieExt.user_id == user_id, MovieExt.core_id == core.id)
                )
            ).first()
            if me:
                cover_url = getattr(me, "backdrop_path", None) or getattr(me, "poster_path", None)
            if not cover_url:
                art = db.exec(
                    select(Artwork).where(
                        and_(Artwork.user_id == user_id, Artwork.core_id == core.id, Artwork.type == "poster")
                    ).order_by(Artwork.preferred.desc())
                ).first()
                cover_url = getattr(art, "remote_url", None) if art else None
            name = core.title
            if dedup == "episode":
                key = core.id
            elif dedup == "series":
                key = core.id
            else:
                key = core.id

        else:
            # 系列的集
            ep_ext = None    
            ep_ext = db.exec(
                    select(EpisodeExt).where(
                        and_(EpisodeExt.user_id == user_id, EpisodeExt.core_id == fa.core_id)
                    )
                ).first()

            name = core.title  
            if ep_ext :
                sn = getattr(ep_ext, "season_number", None)
                en = getattr(ep_ext, "episode_number", None)
                et = getattr(ep_ext, "title", None) or ""
                name = f"{core.title} 第{sn}季 第{en}集 {et}".strip()
                cover_url = getattr(ep_ext, "still_path", None) 
                if not cover_url:
                    base_core_id = ep_ext.season_core_id or core.id
                    art = db.exec(
                        select(Artwork).where(
                            and_(Artwork.user_id == user_id, Artwork.core_id == base_core_id, Artwork.type == "backdrop")
                        ).order_by(Artwork.preferred.desc())
                    ).first()
                    cover_url = getattr(art, "remote_url", None) if art else None
            series_id = getattr(ep_ext, "series_core_id", None) if ep_ext else core.id
            if dedup == "episode":
                key = fa.core_id
            elif dedup == "series":
                key = series_id or core.id
            else:
                key = core.id

        if key in seen:
            continue
        seen.add(key)
        all_items.append(
            RecentCardItem(
                id=core_id,
                name=name,
                cover_url=cover_url,
                media_type="tv" if core.kind.startswith("tv") else "movie",
                position_ms=getattr(r, "position_ms", None),
                duration_ms=getattr(r, "duration_ms", None),
                file_id=getattr(r, "file_asset_id", None),
            )
        )
    size = (page_size or limit)
    start = ((page or 1) - 1) * size
    end = start + size
    return all_items[start:end]

@router.delete("/progress/{file_id}")
def delete_progress(
    file_id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    user_id = int(current_subject)
    rec = db.exec(
        select(PlaybackHistory).where(
            and_(PlaybackHistory.user_id == user_id, PlaybackHistory.file_asset_id == file_id)
        )
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail={"code": "progress_not_found"})
    db.delete(rec)
    db.commit()
    return {"success": True}
