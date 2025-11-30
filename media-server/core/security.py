"""安全与JWT工具。

提供生成与验证 JWT 的工具方法，以及FastAPI依赖。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import Settings, get_settings

# 认证依赖
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(subject: str, settings: Settings | None = None) -> str:
    """创建访问令牌。

    Args:
        subject: 令牌主体，通常是用户ID。
        settings: 应用配置，默认从环境变量加载。

    Returns:
        str: 编码后的 JWT 访问令牌。
    """
    settings = settings or get_settings()
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode: Dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str, settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def decode_access_token(token: str, settings: Settings | None = None) -> Dict[str, Any]:
    """解码访问令牌（兼容旧代码）"""
    return verify_token(token, settings)


def get_current_subject(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]) -> str:
    """从 Authorization: Bearer 中解析当前主体。"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_token(credentials.credentials)
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return str(subject)


def get_current_subject_or_query(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    """解析当前主体：优先使用 Authorization: Bearer，若无则回退到查询参数 token。

    设计考虑与错误处理：
    - Flutter Web 的 <video> 或 HtmlElementView 发起的请求无法注入自定义 Header（Authorization），
      因此下载直链需支持通过查询参数传递 JWT：token、access_token 或 t。
    - 当同时存在 Header 与 Query 时，优先使用 Header。
    - Token 校验沿用 verify_token，一致的过期与签名策略。
    """
    # 优先使用 Bearer
    if credentials is not None:
        payload = verify_token(credentials.credentials)
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return str(subject)

    # 回退查询参数
    qp = request.query_params
    token = qp.get("token") or qp.get("access_token") or qp.get("t")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_token(token)
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return str(subject)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT 认证中间件。

    如果请求包含 Bearer Token，则验证并将主体写入 `request.state.subject`。
    不强制所有请求必须携带令牌，供受保护路由通过依赖单独校验。
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                payload = verify_token(token)
                subject = payload.get("sub")
                if subject:
                    request.state.subject = str(subject)
            except HTTPException:
                # 令牌无效时，不阻塞请求，交由受保护端点的依赖判断
                request.state.subject = None
        return await call_next(request)