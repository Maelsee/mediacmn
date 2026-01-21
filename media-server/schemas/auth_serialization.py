"""JWT刷新令牌相关模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求模型"""
    refresh_token: str = Field(description="刷新令牌")


class RefreshTokenResponse(BaseModel):
    """刷新令牌响应模型"""
    access_token: str = Field(description="新的访问令牌")
    refresh_token: Optional[str] = Field(default=None, description="新的刷新令牌（如果启用了令牌轮换）")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(description="访问令牌过期时间（秒）")


class RevokeTokenRequest(BaseModel):
    """吊销令牌请求模型"""
    refresh_token: str = Field(description="要吊销的刷新令牌")


class TokenInfoResponse(BaseModel):
    """令牌信息响应模型"""
    user_id: int = Field(description="用户ID")
    active_tokens: int = Field(description="活跃的刷新令牌数量")
    expires_at: datetime = Field(description="当前令牌过期时间")
    issued_at: datetime = Field(description="令牌签发时间")


class LoginRequest(BaseModel):
    """登录请求模型"""
    email: EmailStr = Field(description="邮箱")
    password: str = Field(description="密码")
    language: Optional[str] = Field(default=None, description="用户语言选择")