"""Genre 与 MediaCoreGenre 持久化

提供 upsert_genres 方法。
"""
from __future__ import annotations

import logging

from sqlmodel import Session, select
from sqlalchemy.dialects.postgresql import insert

from models.media_models import Genre, MediaCoreGenre

logger = logging.getLogger(__name__)


def upsert_genres(session: Session, user_id: int, core_id: int, genres) -> None:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理 Genre 和 MediaCoreGenre 的创建，
    解决并发环境下的竞态条件。
    """
    if not genres:
        return

    for genre_name in genres:
        savepoint = session.begin_nested()
        try:
            if not genre_name or "&" in genre_name:
                continue

            stmt_genre = insert(Genre).values(name=genre_name).on_conflict_do_nothing(
                index_elements=['name']
            )
            session.execute(stmt_genre)

            genre = session.exec(select(Genre).where(Genre.name == genre_name)).first()

            if not genre:
                logger.error(f"UPSERT Genre 后仍无法获取到记录: {genre_name}")
                continue

            stmt_link = insert(MediaCoreGenre).values(
                user_id=user_id,
                core_id=core_id,
                genre_id=genre.id
            ).on_conflict_do_nothing(
                index_elements=['user_id', 'core_id', 'genre_id']
            )
            session.execute(stmt_link)

            savepoint.commit()

        except Exception as e:
            logger.error(f"处理 Genre 失败（name={genre_name if 'genre_name' in locals() else 'N/A'}）: {str(e)}", exc_info=True)
            savepoint.rollback()
            continue
