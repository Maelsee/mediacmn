"""弹幕绑定关系模型"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from utils.time_compat import get_utc_now_factory
from sqlmodel import UniqueConstraint, BigInteger, Field, SQLModel, Index, String


class DanmuBinding(SQLModel, table=True):
    """弹幕绑定关系模型"""
    __tablename__ = "danmu_bindings"
    id: Optional[int] = Field(default=None, primary_key=True, description="主键ID")
    file_id: str = Field(max_length=255, nullable=False, unique=True, index=True, description="文件ID")
    episode_id: str = Field(max_length=255, nullable=False, index=True, description="剧集ID")
    anime_id: Optional[str] = Field(max_length=255, default=None, description="番剧ID")
    anime_title: Optional[str] = Field(max_length=500, default=None, description="番剧标题")
    episode_title: Optional[str] = Field(max_length=500, default=None, description="剧集标题")
    platform: Optional[str] = Field(max_length=50, default=None, description="弹幕平台")
    offset: float = Field(default=0.0, description="时间偏移量(秒)")
    is_manual: int = Field(default=0, description="是否手动绑定 0=否 1=是")
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now_factory(), description="更新时间")
    __table_args__ = (Index("idx_danmu_binding_file_id", "file_id"), Index("idx_danmu_binding_episode_id", "episode_id"),)


class DanmuBindingHistory(SQLModel, table=True):
    """弹幕绑定历史记录模型"""
    __tablename__ = "danmu_binding_history"
    id: Optional[int] = Field(default=None, primary_key=True, description="主键ID")
    file_id: str = Field(max_length=255, nullable=False, index=True, description="文件ID")
    episode_id: str = Field(max_length=255, nullable=False, description="剧集ID")
    anime_title: Optional[str] = Field(max_length=500, default=None, description="番剧标题")
    episode_title: Optional[str] = Field(max_length=500, default=None, description="剧集标题")
    platform: Optional[str] = Field(max_length=50, default=None, description="弹幕平台")
    action: str = Field(max_length=50, nullable=False, description="操作类型: bind/unbind/update")
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")
    __table_args__ = (Index("idx_danmu_binding_history_file_id", "file_id"),)