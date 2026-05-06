"""MediaVersion 持久化

提供 upsert_season_version、upsert_media_version、cleanup_orphan_versions_after_rebind 方法。
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select, func
from sqlalchemy.dialects.postgresql import insert

from models.media_models import FileAsset, MediaCore, MediaVersion, PlaybackHistory
from .base import (
    _get_attr,
    _get_version_tags_and_fingerprint,
    _get_quality_level,
    _get_file_source,
    _get_season_version_path,
    _generate_season_version_tags,
)

import logging
logger = logging.getLogger(__name__)


def cleanup_orphan_versions_after_rebind(
    session: Session,
    user_id: int,
    old_version_id: Optional[int],
    new_version_id: Optional[int],
    old_season_version_id: Optional[int],
    new_season_version_id: Optional[int],
) -> None:
    """清理因版本重新绑定而产生的孤立版本"""
    if old_version_id and old_version_id != new_version_id:
        cnt = session.exec(
            select(func.count(FileAsset.id)).where(
                FileAsset.user_id == user_id,
                FileAsset.version_id == old_version_id,
            )
        ).one()
        if int(cnt or 0) == 0:
            v = session.get(MediaVersion, old_version_id)
            if v and getattr(v, "user_id", None) == user_id:
                # 清空 playback_history 对该版本的引用，避免外键约束冲突
                histories = session.exec(
                    select(PlaybackHistory).where(
                        PlaybackHistory.version_id == old_version_id
                    )
                ).all()
                for h in histories or []:
                    h.version_id = None
                if histories:
                    session.flush()
                session.delete(v)

    if old_season_version_id and old_season_version_id != new_season_version_id:
        season_cnt = session.exec(
            select(func.count(FileAsset.id)).where(
                FileAsset.user_id == user_id,
                FileAsset.season_version_id == old_season_version_id,
            )
        ).one()
        if int(season_cnt or 0) == 0:
            children = session.exec(
                select(MediaVersion).where(
                    MediaVersion.user_id == user_id,
                    MediaVersion.parent_version_id == old_season_version_id,
                )
            ).all()
            for child in children or []:
                child_id = getattr(child, "id", None)
                if not child_id:
                    continue
                child_cnt = session.exec(
                    select(func.count(FileAsset.id)).where(
                        FileAsset.user_id == user_id,
                        FileAsset.version_id == child_id,
                    )
                ).one()
                if int(child_cnt or 0) == 0:
                    # 清空 playback_history 对该子版本的引用
                    child_histories = session.exec(
                        select(PlaybackHistory).where(
                            PlaybackHistory.version_id == child_id
                        )
                    ).all()
                    for h in child_histories or []:
                        h.version_id = None
                    session.delete(child)

            if hasattr(session, "flush"):
                session.flush()

            remaining_children = session.exec(
                select(func.count(MediaVersion.id)).where(
                    MediaVersion.user_id == user_id,
                    MediaVersion.parent_version_id == old_season_version_id,
                )
            ).one()
            if int(remaining_children or 0) == 0:
                sv = session.get(MediaVersion, old_season_version_id)
                if sv and getattr(sv, "user_id", None) == user_id:
                    session.delete(sv)


def upsert_season_version(
    session: Session, media_file: FileAsset, season_core: MediaCore
) -> int:
    """
    使用数据库级别的 UPSERT 来原子化地创建/更新季版本。
    """
    season_version_path = _get_season_version_path(media_file)
    season_tags = _generate_season_version_tags(season_version_path, season_core)
    fingerprint_str = f"{season_version_path}_{season_core.id}_{media_file.user_id}"
    season_fingerprint = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()

    savepoint = session.begin_nested()
    try:
        stmt = insert(MediaVersion).values(
            user_id=media_file.user_id,
            core_id=season_core.id,
            tags=season_tags,
            scope="season_group",
            variant_fingerprint=season_fingerprint,
            preferred=True,
            primary_file_asset_id=None,
            parent_version_id=None,
            season_version_path=season_version_path,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).on_conflict_do_update(
            index_elements=['user_id', 'core_id', 'tags'],
            set_={
                'variant_fingerprint': func.coalesce(MediaVersion.variant_fingerprint, season_fingerprint),
                'season_version_path': season_version_path,
                'updated_at': datetime.now(),
            }
        ).returning(MediaVersion.id)

        result = session.execute(stmt)
        version_id = result.scalar_one()

        logger.debug(f"UPSERT 季版本: user_id={media_file.user_id}, season_core_id={season_core.id}, version_id={version_id}, path={season_version_path}")
        savepoint.commit()
        return version_id
    except Exception as e:
        logger.error(f"创建/更新季版本时发生错误: {str(e)}", exc_info=True)
        savepoint.rollback()
        raise e


def upsert_media_version(
    session: Session,
    media_file: FileAsset,
    core: MediaCore,
    metadata,
    season_version_id: Optional[int] = None,
) -> int:
    """
    使用数据库级别的 UPSERT 来原子化地创建/更新媒体版本。
    """
    if not core:
        core = session.get(MediaCore, media_file.core_id)
        if not core:
            raise ValueError(f"无法找到与文件关联的MediaCore: {media_file.id}")

    if core.kind == "movie":
        scope = "movie_single"
    elif core.kind == "episode":
        scope = "episode_child"
    else:
        scope = "movie_single"

    version_tags, variant_fingerprint = _get_version_tags_and_fingerprint(media_file, core, scope)
    quality = _get_quality_level(media_file)
    edition = _get_attr(metadata, "edition") or _get_attr(metadata, "episode_type") or "unknown"
    source = _get_file_source(session, media_file)
    savepoint = session.begin_nested()
    try:
        stmt = insert(MediaVersion).values(
            user_id=media_file.user_id,
            core_id=core.id,
            tags=version_tags,
            scope=scope,
            quality=quality,
            source=source,
            edition=edition,
            variant_fingerprint=variant_fingerprint,
            preferred=True,
            primary_file_asset_id=media_file.id,
            parent_version_id=season_version_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).on_conflict_do_update(
            index_elements=['user_id', 'core_id', 'tags'],
            set_={
                'quality': func.coalesce(MediaVersion.quality, quality),
                'source': func.coalesce(MediaVersion.source, source),
                'edition': func.coalesce(MediaVersion.edition, edition),
                'variant_fingerprint': func.coalesce(MediaVersion.variant_fingerprint, variant_fingerprint),
                'parent_version_id': season_version_id,
                'primary_file_asset_id': media_file.id,
                'updated_at': datetime.now(),
            }
        ).returning(MediaVersion.id)

        result = session.execute(stmt)
        version_id = result.scalar_one()
        savepoint.commit()
        logger.debug(f"UPSERT {scope}版本: user_id={media_file.user_id}, core_id={core.id}, version_id={version_id}")
        return version_id
    except Exception as e:
        logger.error(f"创建/更新{scope}版本时发生错误: {str(e)}", exc_info=True)
        savepoint.rollback()
        raise e
