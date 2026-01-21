"""认证相关路由。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from starlette import status
from sqlmodel import Session
from core.logging import  logger
from core.db import get_session
from core.security import create_access_token, get_current_subject
from schemas.user import TokenResponse, UserCreate, UserRead
from schemas.auth_serialization import LoginRequest, RefreshTokenRequest, RefreshTokenResponse, RevokeTokenRequest, TokenInfoResponse
from services.auth.user_service import authenticate, create_user
from services.auth.refresh_token_service import RefreshTokenService
from sqlmodel import select
from models.user import User


router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, session: Session = Depends(get_session)) -> UserRead:
    """注册新用户。

    - email: 唯一的用户邮箱
    - password: 密码（会被哈希存储）
    - language: 用户语言选择
    """
    logger.info(f"注册请求语言: {payload.language}")
    user = create_user(session, email=payload.email, password=payload.password, language=payload.language)
    return UserRead(id=user.id, email=user.email, is_active=user.is_active)


@router.post("/login", response_model=RefreshTokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> RefreshTokenResponse:
    """用户登录，返回 JWT 访问令牌和刷新令牌。

    - email: 邮箱
    - password: 密码
    """
    logger.info(f"登录请求: {payload.email}")
    # 使用邮箱进行认证（User模型只有email字段）
    user = authenticate(session, email=payload.email, password=payload.password)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    # 创建访问令牌
    access_token = create_access_token(subject=str(user.id))
    
    # 创建刷新令牌
    refresh_token_service = RefreshTokenService()
    refresh_token, _ = refresh_token_service.create_refresh_token(user.id, session)
    
    from core.config import get_settings
    settings = get_settings()
    
    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=UserRead)
def me(current_subject: str = Depends(get_current_subject), session: Session = Depends(get_session)) -> UserRead:
    """获取当前认证用户的详细信息。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")
    stmt = select(User).where(User.id == user_id)
    user = session.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead(id=user.id, email=user.email, is_active=user.is_active)


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token(payload: RefreshTokenRequest, session: Session = Depends(get_session)) -> RefreshTokenResponse:
    """使用刷新令牌获取新的访问令牌。
    
    - refresh_token: 刷新令牌
    """
    refresh_token_service = RefreshTokenService()
    
    try:
        access_token, user = refresh_token_service.refresh_access_token(payload.refresh_token, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    
    from core.config import get_settings
    settings = get_settings()
    
    # 如果启用了令牌轮换，需要返回新的刷新令牌
    refresh_token = None
    if settings.REFRESH_TOKEN_ROTATION:
        # 重新查询最新的刷新令牌（在refresh_access_token中创建的新令牌）
        from sqlmodel import select
        from models.refresh_token import RefreshToken
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.is_revoked == False
        ).order_by(RefreshToken.created_at.desc())
        latest_token = session.exec(stmt).first()
        if latest_token:
            refresh_token = latest_token.token
    
    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/revoke", status_code=status.HTTP_200_OK)
def revoke_token(payload: RevokeTokenRequest, session: Session = Depends(get_session)) -> dict:
    """吊销刷新令牌。
    
    - refresh_token: 要吊销的刷新令牌
    """
    refresh_token_service = RefreshTokenService()
    
    success = refresh_token_service.revoke_refresh_token(payload.refresh_token, session)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh token not found")
    
    return {"message": "Token revoked successfully"}


@router.get("/tokens/info", response_model=TokenInfoResponse)
def get_tokens_info(current_subject: str = Depends(get_current_subject), session: Session = Depends(get_session)) -> TokenInfoResponse:
    """获取当前用户的令牌信息。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")
    
    refresh_token_service = RefreshTokenService()
    active_tokens_count = refresh_token_service.get_user_active_tokens_count(user_id, session)
    
    # 获取当前令牌的过期时间（从当前会话的令牌中解析）
    # 这里简化处理，使用配置中的过期时间
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
def logout(current_subject: str = Depends(get_current_subject), session: Session = Depends(get_session)) -> dict:
    """注销当前用户的所有刷新令牌。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject")
    
    refresh_token_service = RefreshTokenService()
    revoked_count = refresh_token_service.revoke_all_user_refresh_tokens(user_id, session)
    
    logger.info(f"用户 {user_id} 登出，吊销了 {revoked_count} 个刷新令牌")
    
    return {"message": f"Successfully logged out. Revoked {revoked_count} tokens."}