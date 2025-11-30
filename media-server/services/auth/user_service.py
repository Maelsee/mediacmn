"""用户服务层。"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from starlette import status
from passlib.context import CryptContext
from core.errors import AppError

from models.user import User


# 密码哈希上下文 - 使用bcrypt算法，支持自动迁移
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _hash_password(password: str) -> str:
    """使用bcrypt哈希密码。
    
    Args:
        password: 明文密码
        
    Returns:
        str: bcrypt哈希后的密码
    """
    # bcrypt有72字节长度限制，超过的需要截断
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

def _verify_password(password: str, hashed: str) -> bool:
    """验证密码。
    
    Args:
        password: 明文密码
        hashed: 哈希后的密码
        
    Returns:
        bool: 密码是否匹配
    """
    # bcrypt有72字节长度限制，超过的需要截断
    if len(password) > 72:
        password = password[:72]
    return pwd_context.verify(password, hashed)

# 创建用户
def create_user(session: Session, email: str, password: str) -> User:
    """创建新用户。

    Args:
        session: SQLModel会话。
        email: 用户邮箱。
        password: 用户密码。

    Returns:
        User: 创建的用户对象。

    Raises:
        AppError: 邮箱已存在时抛出。
    """
    user = User(email=email, hashed_password=_hash_password(password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # 返回更友好的错误信息
        raise AppError("Email already exists", code="email_exists", http_status=status.HTTP_409_CONFLICT)
    session.refresh(user)
    return user

# 认证用户
def authenticate(session: Session, email: str, password: str) -> Optional[User]:
    """认证用户。

    Args:
        session: SQLModel会话。
        email: 用户邮箱。
        password: 用户密码。

    Returns:
        Optional[User]: 认证成功返回用户对象，否则返回None。
    """
    stmt = select(User).where(User.email == email)
    user = session.exec(stmt).first()
    if user and _verify_password(password, user.hashed_password):
        return user
    return None