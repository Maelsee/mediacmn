from __future__ import annotations

import json
from typing import Any, Dict, Optional

import redis.asyncio as redis

from core.config import get_settings


_settings = get_settings()
_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            _settings.REDIS_URL,
            db=_settings.REDIS_DB,
            decode_responses=True,
        )
    return _redis_client


def _progress_key(user_id: int, job_id: str) -> str:
    return f"scan_progress:{user_id}:{job_id}"


CHANNEL_NAME = "scan_progress_events"


async def init_scan_progress(user_id: int, job_id: str) -> None:
    r = _get_redis()
    key = _progress_key(user_id, job_id)
    await r.hset(
        key,
        mapping={
            "status": "running",
            "scanned_count": "0",
            "pending_update_count": "0",
            "updated_count": "0",
        },
    )


async def update_scan_progress(
    user_id: int,
    job_id: str,
    *,
    scanned: Optional[int] = None,
    pending_update: Optional[int] = None,
    updated_delta: Optional[int] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    r = _get_redis()
    key = _progress_key(user_id, job_id)
    pipe = r.pipeline()
    if scanned is not None:
        pipe.hset(key, "scanned_count", scanned)
    if pending_update is not None:
        pipe.hset(key, "pending_update_count", pending_update)
    if updated_delta is not None:
        pipe.hincrby(key, "updated_count", updated_delta)
    if status is not None:
        pipe.hset(key, "status", status)
    if error is not None:
        pipe.hset(key, "last_error", error)
    pipe.hgetall(key)
    results = await pipe.execute()
    snapshot = results[-1] or {}
    scanned_count = int(snapshot.get("scanned_count") or 0)
    pending_count = int(snapshot.get("pending_update_count") or 0)
    updated_count = int(snapshot.get("updated_count") or 0)
    payload: Dict[str, Any] = {
        "type": "scan_progress",
        "user_id": user_id,
        "job_id": job_id,
        "status": snapshot.get("status") or "running",
        "scanned_count": scanned_count,
        "pending_update_count": pending_count,
        "updated_count": updated_count,
    }
    await r.publish(CHANNEL_NAME, json.dumps(payload, ensure_ascii=False))
    return payload


async def get_scan_progress(user_id: int, job_id: str) -> Optional[Dict[str, Any]]:
    r = _get_redis()
    data = await r.hgetall(_progress_key(user_id, job_id))
    if not data:
        return None
    scanned_count = int(data.get("scanned_count") or 0)
    pending_count = int(data.get("pending_update_count") or 0)
    updated_count = int(data.get("updated_count") or 0)
    return {
        "scan_job_id": job_id,
        "status": data.get("status") or "running",
        "scanned_count": scanned_count,
        "pending_update_count": pending_count,
        "updated_count": updated_count,
    }

