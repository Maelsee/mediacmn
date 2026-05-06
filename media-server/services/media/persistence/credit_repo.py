"""Credit 与 Person 持久化

提供 upsert_credits 方法。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select
from sqlalchemy.dialects.postgresql import insert

from models.media_models import Person, Credit
from .base import _get_attr

logger = logging.getLogger(__name__)


def upsert_credits(
    session: Session, user_id: int, core_id: int, credits, provider: Optional[str]
) -> None:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理 Person 和 Credit 的创建/更新，
    彻底解决并发环境下的竞态条件问题。
    """
    if not credits:
        return

    for c in credits:
        savepoint = session.begin_nested()
        try:
            if not c:
                continue

            # --- 处理 Person ---
            name = _get_attr(c, "name")
            original_name = _get_attr(c, "original_name")
            provider_id = _get_attr(c, "provider_id")
            purl = _get_attr(c, "image_url")
            if not name:
                continue

            stmt_person = insert(Person).values(
                provider=provider,
                provider_id=provider_id,
                name=name,
                original_name=original_name,
                profile_url=purl
            ).on_conflict_do_nothing(
                index_elements=['provider', 'provider_id', 'name']
            )
            session.execute(stmt_person)

            person = session.exec(select(Person).where(
                Person.provider_id == provider_id,
                Person.name == name,
                Person.provider == provider
            )).first()

            if not person:
                logger.error(f"UPSERT Person 后仍无法获取到记录 (name={name}, provider={provider}, provider_id={provider_id})")
                continue

            person.original_name = original_name or person.original_name
            if not person.profile_url and purl:
                person.profile_url = purl

            # --- 处理 Credit ---
            c_type = _get_attr(c, "type")
            if hasattr(c_type, "value"):
                role_type = c_type.value
            else:
                role_type = c_type
            role = "cast" if role_type == "actor" else "crew"
            role = "guest" if _get_attr(c, "is_flying") else role

            character = _get_attr(c, "character") if role == "cast" else None
            job = role_type
            order = _get_attr(c, "order")

            stmt_credit = insert(Credit).values(
                user_id=user_id,
                core_id=core_id,
                person_id=person.id,
                role=role,
                character=character,
                job=job,
                order=order
            ).on_conflict_do_update(
                index_elements=['user_id', 'core_id', 'person_id', 'role', 'job'],
                set_={
                    'character': character,
                    'order': order
                }
            )
            session.execute(stmt_credit)

            savepoint.commit()

        except Exception as e:
            logger.error(f"处理 Person/Credit 失败（name={name if 'name' in locals() else 'N/A'}, provider={provider}）: {str(e)}", exc_info=True)
            savepoint.rollback()
            continue
