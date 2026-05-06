"""Artwork 与 ExternalID 持久化

提供 _upsert_artworks 和 _upsert_external_ids 方法。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select, update
from sqlalchemy.dialects.postgresql import insert

from models.media_models import Artwork, ExternalID
from .base import _get_attr

logger = logging.getLogger(__name__)


def upsert_artworks(
    session: Session, user_id: int, core_id: int, provider: Optional[str], artworks
) -> None:
    """
    使用数据库级别的 UPSERT 和原子性 UPDATE 来处理 Artwork，
    确保"唯一首选"逻辑在并发环境下的正确性和一致性。
    """
    if not artworks:
        return

    for artwork in artworks:
        savepoint = session.begin_nested()
        try:
            a_type = _get_attr(artwork, "type")
            a_url = _get_attr(artwork, "url")
            a_language = _get_attr(artwork, "language")
            a_preferred = _get_attr(artwork, "is_primary") is True
            a_width = _get_attr(artwork, "width")
            a_height = _get_attr(artwork, "height")

            _t = a_type.value if hasattr(a_type, "value") else a_type
            if not _t or not a_url:
                continue

            values = {
                "provider": provider,
                "language": a_language,
                "width": a_width,
                "height": a_height,
            }

            if a_preferred:
                stmt = insert(Artwork).values(
                    user_id=user_id,
                    core_id=core_id,
                    type=_t,
                    remote_url=a_url,
                    preferred=True,
                    **values
                ).on_conflict_do_update(
                    index_elements=['user_id', 'core_id', 'type', 'remote_url'],
                    set_={
                        "preferred": True,
                        **values
                    }
                ).returning(Artwork.id)

                result = session.execute(stmt)
                current_artwork_id = result.scalar_one()

                session.execute(
                    update(Artwork).where(
                        Artwork.user_id == user_id,
                        Artwork.core_id == core_id,
                        Artwork.type == _t,
                        Artwork.id != current_artwork_id
                    ).values(preferred=False)
                )
            else:
                stmt = insert(Artwork).values(
                    user_id=user_id,
                    core_id=core_id,
                    type=_t,
                    remote_url=a_url,
                    preferred=False,
                    **values
                ).on_conflict_do_update(
                    index_elements=['user_id', 'core_id', 'type', 'remote_url'],
                    set_=values
                )
                session.execute(stmt)

            savepoint.commit()

        except Exception as e:
            logger.error(f"处理 Artwork 失败（URL: {a_url if 'a_url' in locals() else 'N/A'}）: {str(e)}", exc_info=True)
            savepoint.rollback()
            continue


def upsert_external_ids(
    session: Session, user_id: int, core_id: int, external_ids
) -> None:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理 ExternalID 的创建/更新。
    """
    if not external_ids:
        return

    for eid in external_ids:
        savepoint = session.begin_nested()
        try:
            if not eid:
                continue

            provider = _get_attr(eid, "provider")
            external_id_raw = _get_attr(eid, "external_id")

            if not provider or external_id_raw is None:
                logger.debug(f"跳过无效外部ID（provider={provider}, external_id={external_id_raw}）")
                continue

            external_id_str = str(external_id_raw)

            stmt = insert(ExternalID).values(
                user_id=user_id,
                core_id=core_id,
                source=provider,
                key=external_id_str
            ).on_conflict_do_update(
                index_elements=['user_id', 'core_id', 'source'],
                set_={
                    'key': external_id_str
                }
            )
            session.execute(stmt)

            savepoint.commit()

        except Exception as e:
            logger.error(f"处理 ExternalID 失败（provider={provider if 'provider' in locals() else 'N/A'}）: {str(e)}", exc_info=True)
            savepoint.rollback()
            continue
