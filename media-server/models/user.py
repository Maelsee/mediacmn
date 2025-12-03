"""用户模型。

使用 SQLModel 定义用户表，用于认证演示。
"""
from __future__ import annotations

from typing import Optional, List


from sqlmodel import Field, SQLModel, UniqueConstraint



class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)
    id: Optional[int] = Field(default=None, primary_key=True, description="用户唯一标识")
    email: str = Field(index=True, description="用户邮箱地址（用于登录）")
    hashed_password: str = Field(description="加密后的密码哈希值")
    is_active: bool = Field(default=True, description="用户激活状态（True为激活，False为禁用）")
    
    # 关联关系 - 暂时移除以解决循环依赖问题
    # refresh_tokens: List["RefreshToken"] = Relationship(back_populates="user")