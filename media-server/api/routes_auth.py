"""认证相关路由。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from starlette import status
from sqlmodel.ext.asyncio.session import AsyncSession
from core.logging import logger
from core.db import get_async_session
from core.security import create_access_token, get_current_subject
from schemas.user import TokenResponse, UserCreate, UserRead
from schemas.auth_serialization import LoginRequest, RefreshTokenRequest, RefreshTokenResponse, RevokeTokenRequest, TokenInfoResponse
from services.auth.user_service import authenticate, create_user
from services.auth.refresh_token_service import RefreshTokenService
from sqlmodel import select
from models.user import User


router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, session: AsyncSession = Depends(get_async_session)) -> UserRead:
    """注册新用户。"""
    logger.info(f"注册请求语言: {payload.language}")
    user = await session.run_sync(lambda s: create_user(s, email=payload.email, password=payload.password, language=payload.language))
    return UserRead(id=user.id, email=user.email, is_active=user.is_active)


@router.post("/login", response_model=RefreshTokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_async_session)) -> RefreshTokenResponse:
    """用户登录，返回 JWT 访问令牌和刷新令牌。"""
    logger.info(f"登录请求: {payload.email}")
    user = await session.run_sync(lambda s: authenticate(s, email=payload.email, password=payload.password))

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(subject=str(user.id))

    refresh_token_service = RefreshTokenService()
    refresh_token, _ = await session.run_sync(lambda s: refresh_token_service.create_refresh_token(user.id, s))

    from core.config import get_settings
    settings = get_settings()

    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=UserRead)
async def me(current_subject: str = Depends(get_current_subject), session: AsyncSession = Depends(get_async_session)) -> UserRead:
    """获取当前认证用户的详细信息。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")
    stmt = select(User).where(User.id == user_id)
    result = await session.exec(stmt)
    user = result.first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead(id=user.id, email=user.email, is_active=user.is_active)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(payload: RefreshTokenRequest, session: AsyncSession = Depends(get_async_session)) -> RefreshTokenResponse:
    """使用刷新令牌获取新的访问令牌。"""
    refresh_token_service = RefreshTokenService()

    try:
        access_token, user = await session.run_sync(lambda s: refresh_token_service.refresh_access_token(payload.refresh_token, s))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    from core.config import get_settings
    settings = get_settings()

    refresh_token = None
    if settings.REFRESH_TOKEN_ROTATION:
        from sqlmodel import select
        from models.refresh_token import RefreshToken
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.is_revoked == False
        ).order_by(RefreshToken.created_at.desc())
        result = await session.exec(stmt)
        latest_token = result.first()
        if latest_token:
            refresh_token = latest_token.token

    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/revoke", status_code=status.HTTP_200_OK)
async def revoke_token(payload: RevokeTokenRequest, session: AsyncSession = Depends(get_async_session)) -> dict:
    """吊销刷新令牌。"""
    refresh_token_service = RefreshTokenService()

    success = await session.run_sync(lambda s: refresh_token_service.revoke_refresh_token(payload.refresh_token, s))
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh token not found")

    return {"message": "Token revoked successfully"}


@router.get("/tokens/info", response_model=TokenInfoResponse)
async def get_tokens_info(current_subject: str = Depends(get_current_subject), session: AsyncSession = Depends(get_async_session)) -> TokenInfoResponse:
    """获取当前用户的令牌信息。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")

    refresh_token_service = RefreshTokenService()
    active_tokens_count = await session.run_sync(lambda s: refresh_token_service.get_user_active_tokens_count(user_id, s))

    from core.config import get_settings
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    return TokenInfoResponse(
        user_id=user_id,
        active_tokens=active_tokens_count,
        expires_at=expires_at,
        issued_at=datetime.now(timezone.utc)
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_subject: str = Depends(get_current_subject), session: AsyncSession = Depends(get_async_session)) -> dict:
    """注销当前用户的所有刷新令牌。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")

    refresh_token_service = RefreshTokenService()
    revoked_count = await session.run_sync(lambda s: refresh_token_service.revoke_all_user_refresh_tokens(user_id, s))

    logger.info(f"用户 {user_id} 登出，吊销了 {revoked_count} 个刷新令牌")

    return {"message": f"Successfully logged out. Revoked {revoked_count} tokens."}
