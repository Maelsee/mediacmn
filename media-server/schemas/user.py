"""用户请求/响应模式。"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
    is_active: bool



class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"