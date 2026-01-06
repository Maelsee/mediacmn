"""健康检查路由。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
import redis

from core.db import engine
from core.config import get_settings

router = APIRouter()


@router.get("/live")
def liveness() -> dict[str, str]:
    """检查应用是否存活。

    通常在应用启动时调用，确认基础服务（如 HTTP 服务器）已启动。
    """
    return {"status": "live"}


@router.get("/ready")
def readiness() -> dict[str, Any]:
    """检查应用是否准备好接收请求。

    通常在启动完成后调用，确保所有依赖服务（如数据库、缓存）已就绪。
    """
    checks: dict[str, str] = {}
    is_ready = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        is_ready = False
        checks["database"] = f"error:{type(e).__name__}"

    settings = get_settings()

    try:
        queue_redis = redis.Redis.from_url(
            f"{settings.REDIS_URL}/{settings.REDIS_DB}",
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        queue_redis.ping()
        checks["redis_queue"] = "ok"
    except Exception as e:
        is_ready = False
        checks["redis_queue"] = f"error:{type(e).__name__}"

    try:
        cache_redis = redis.Redis.from_url(
            f"{settings.SCRAPER_CACHE_REDIS_URL}/{settings.SCRAPER_CACHE_REDIS_DB}",
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        cache_redis.ping()
        checks["redis_cache"] = "ok"
    except Exception as e:
        is_ready = False
        checks["redis_cache"] = f"error:{type(e).__name__}"

    return {"status": "ready" if is_ready else "not_ready", "checks": checks}
