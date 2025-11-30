"""JWT刷新令牌模型"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship

from models.user import User


class RefreshToken(SQLModel, table=True):
    """JWT刷新令牌模型"""
    __tablename__ = "refresh_tokens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token: str = Field(unique=True, index=True, description="刷新令牌")
    expires_at: datetime = Field(datetime.now(timezone.utc), description="过期时间")
    is_revoked: bool = Field(default=False, description="是否已吊销")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 关联用户 - 暂时移除以解决循环依赖问题
    # user: User = Relationship(back_populates="refresh_tokens")
    
    @property
    def is_expired(self) -> bool:
        """检查令牌是否过期"""
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        # 兼容历史数据：若为naive时间，规范为UTC
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires
    
    @property
    def is_valid(self) -> bool:
        """检查令牌是否有效（未过期且未吊销）"""
        return not self.is_expired and not self.is_revoked


# 关联关系已在User模型中定义
