"""JWT刷新令牌服务"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlmodel import Session, select
import logging

from core.config import Settings, get_settings
from core.security import create_access_token, verify_token
from models.refresh_token import RefreshToken
from models.user import User
logger = logging.getLogger(__name__)

class RefreshTokenService:
    """JWT刷新令牌服务"""
    
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
    
    def create_refresh_token(self, user_id: int, session: Session) -> Tuple[str, RefreshToken]:
        """创建刷新令牌
        
        Args:
            user_id: 用户ID
            session: 数据库会话
            
        Returns:
            Tuple[str, RefreshToken]: (刷新令牌字符串, 刷新令牌模型)
        """
        # 生成安全的随机令牌
        token = secrets.token_urlsafe(32)
        
        # 计算过期时间
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        # 创建刷新令牌记录
        refresh_token = RefreshToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            is_revoked=False
        )
        
        session.add(refresh_token)
        session.commit()
        session.refresh(refresh_token)
        
        logger.info(f"为用户 {user_id} 创建刷新令牌")
        return token, refresh_token
    
    def refresh_access_token(self, refresh_token_str: str, session: Session) -> Tuple[str, User]:
        """使用刷新令牌获取新的访问令牌
        
        Args:
            refresh_token_str: 刷新令牌字符串
            session: 数据库会话
            
        Returns:
            Tuple[str, User]: (新的访问令牌, 用户对象)
            
        Raises:
            ValueError: 刷新令牌无效或已过期
        """
        # 查询刷新令牌
        stmt = select(RefreshToken).where(RefreshToken.token == refresh_token_str)
        refresh_token = session.exec(stmt).first()
        
        if not refresh_token:
            logger.warning(f"刷新令牌不存在: {refresh_token_str[:10]}...")
            raise ValueError("无效的刷新令牌")
        
        # 检查令牌是否有效
        if not refresh_token.is_valid:
            logger.warning(f"刷新令牌无效或已过期: {refresh_token_str[:10]}...")
            raise ValueError("刷新令牌无效或已过期")
        
        # 获取用户（避免依赖被移除的关系，显式加载）
        user = session.get(User, refresh_token.user_id)
        if not user:
            logger.error(f"刷新令牌对应的用户不存在: {refresh_token.user_id}")
            raise ValueError("用户不存在")
        
        # 创建新的访问令牌
        access_token = create_access_token(str(user.id))
        
        # 如果启用令牌轮换，创建新的刷新令牌并吊销旧的
        if self.settings.REFRESH_TOKEN_ROTATION:
            # 吊销旧令牌
            refresh_token.is_revoked = True
            refresh_token.updated_at = datetime.now(timezone.utc)
            session.add(refresh_token)
            
            # 创建新令牌
            new_token, new_refresh_token = self.create_refresh_token(user.id, session)
            logger.info(f"刷新令牌轮换: 用户 {user.id} 的旧令牌已吊销，新令牌已创建")
        
        logger.info(f"为用户 {user.id} 刷新访问令牌")
        return access_token, user
    
    def revoke_refresh_token(self, refresh_token_str: str, session: Session) -> bool:
        """吊销刷新令牌
        
        Args:
            refresh_token_str: 刷新令牌字符串
            session: 数据库会话
            
        Returns:
            bool: 是否成功吊销
        """
        stmt = select(RefreshToken).where(RefreshToken.token == refresh_token_str)
        refresh_token = session.exec(stmt).first()
        
        if not refresh_token:
            return False
        
        refresh_token.is_revoked = True
        refresh_token.updated_at = datetime.now(timezone.utc)
        session.add(refresh_token)
        session.commit()
        
        logger.info(f"刷新令牌已吊销: {refresh_token_str[:10]}...")
        return True
    
    def revoke_all_user_refresh_tokens(self, user_id: int, session: Session) -> int:
        """吊销用户的所有刷新令牌
        
        Args:
            user_id: 用户ID
            session: 数据库会话
            
        Returns:
            int: 吊销的令牌数量
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False
        )
        tokens = session.exec(stmt).all()
        
        count = 0
        for token in tokens:
            token.is_revoked = True
            token.updated_at = datetime.now(timezone.utc)
            session.add(token)
            count += 1
        
        if count > 0:
            session.commit()
            logger.info(f"用户 {user_id} 的 {count} 个刷新令牌已吊销")
        
        return count
    
    def cleanup_expired_tokens(self, session: Session) -> int:
        """清理过期的刷新令牌
        
        Args:
            session: 数据库会话
            
        Returns:
            int: 清理的令牌数量
        """
        now = datetime.now(timezone.utc)
        stmt = select(RefreshToken).where(
            RefreshToken.expires_at < now,
            RefreshToken.is_revoked == False
        )
        expired_tokens = session.exec(stmt).all()
        
        count = 0
        for token in expired_tokens:
            token.is_revoked = True
            token.updated_at = now
            session.add(token)
            count += 1
        
        if count > 0:
            session.commit()
            logger.info(f"清理了 {count} 个过期的刷新令牌")
        
        return count
    
    def get_user_active_tokens_count(self, user_id: int, session: Session) -> int:
        """获取用户活跃的刷新令牌数量
        
        Args:
            user_id: 用户ID
            session: 数据库会话
            
        Returns:
            int: 活跃的令牌数量
        """
        now = datetime.now(timezone.utc)
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > now
        )
        return len(session.exec(stmt).all())
