"""健康检查路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/live")
def liveness() -> dict[str, str]:
    """检查应用是否存活。

    通常在应用启动时调用，确认基础服务（如 HTTP 服务器）已启动。
    """
    return {"status": "live"}


@router.get("/ready")
def readiness() -> dict[str, str]:
    """检查应用是否准备好接收请求。

    通常在启动完成后调用，确保所有依赖服务（如数据库、缓存）已就绪。
    """
    return {"status": "ready"}