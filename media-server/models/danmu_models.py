"""
弹幕绑定关系模型（优化版）

优化点：
1. file_id 保持 str 类型（与前端传参一致，实际存储 FileAsset.id 的字符串形式）
2. 新增 source_info: JSON 字段，存储搜索/匹配时的完整源信息
3. 新增 match_confidence: float 字段，记录自动匹配的置信度
4. 新增 DanmuBindingHistory.extra: str 字段，记录操作附加信息
5. 增加 user_id 字段支持多租户隔离（可选，暂不启用外键约束）
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from utils.time_compat import get_utc_now_factory
from sqlmodel import UniqueConstraint, BigInteger, Field, SQLModel, Index, String, Column, Text
# from sqlalchemy import JSON


class DanmuBinding(SQLModel, table=True):
    """弹幕绑定关系模型

    一个文件（file_id）绑定一个弹幕源（episode_id）。
    file_id 对应 file_asset 表的主键 id。
    episode_id 对应 danmu_api 返回的 episodeId。
    """
    __tablename__ = "danmu_bindings"

    id: Optional[int] = Field(default=None, primary_key=True, description="主键ID")

    # ---- 核心绑定关系 ----
    file_id: str = Field(max_length=255, nullable=False, unique=True, index=True,
                         description="文件ID（对应 file_asset.id）")
    episode_id: str = Field(max_length=255, nullable=False, index=True,
                            description="弹幕剧集ID（danmu_api 的 episodeId）")

    # ---- 弹幕源信息 ----
    anime_id: Optional[str] = Field(max_length=255, default=None,
                                    description="番剧ID（danmu_api 的 animeId）")
    anime_title: Optional[str] = Field(max_length=500, default=None,
                                       description="番剧标题")
    episode_title: Optional[str] = Field(max_length=500, default=None,
                                         description="剧集标题")
    type: Optional[str] = Field(max_length=50, default=None,
                                    description="弹幕类型（danmu_api 的 type）")
    typeDescription: Optional[str] = Field(max_length=500, default=None,
                                    description="弹幕类型描述（danmu_api 的 typeDescription）")
    imageUrl: Optional[str] = Field(max_length=500, default=None,
                                    description="弹幕图片URL（danmu_api 的 imageUrl）")
    # platform: Optional[str] = Field(max_length=50, default=None,
                                    # description="弹幕来源平台（bilibili/iqiyi/tencent 等）")

    # ---- 时间偏移 ----
    offset: float = Field(default=0.0, description="时间偏移量(秒)，弹幕时间 = 原始时间 + offset")

    # ---- 绑定元信息 ----
    is_manual: int = Field(default=0, description="是否手动绑定 0=自动 1=手动")
    match_confidence: Optional[float] = Field(default=None,
                                              description="匹配置信度（自动匹配时记录，0.0~1.0）")
    # source_info: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True),
    #                                    description="搜索/匹配时的完整源信息（JSON 字符串）")

    # ---- 时间戳 ----
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now_factory(), description="更新时间")

    __table_args__ = (
        Index("idx_danmu_binding_file_id", "file_id", unique=True),
        Index("idx_danmu_binding_episode_id", "episode_id"),
        Index("idx_danmu_binding_anime_id", "anime_id"),
    )


class DanmuBindingHistory(SQLModel, table=True):
    """弹幕绑定历史记录模型

    每次绑定/解绑/更新操作都会记录一条历史。
    用于用户查看操作记录和问题排查。
    """
    __tablename__ = "danmu_binding_history"

    id: Optional[int] = Field(default=None, primary_key=True, description="主键ID")
    file_id: str = Field(max_length=255, nullable=False, index=True, description="文件ID")
    episode_id: str = Field(max_length=255, nullable=False, description="剧集ID")
    anime_title: Optional[str] = Field(max_length=500, default=None, description="番剧标题")
    episode_title: Optional[str] = Field(max_length=500, default=None, description="剧集标题")
    # platform: Optional[str] = Field(max_length=50, default=None, description="弹幕平台")
    action: str = Field(max_length=50, nullable=False,
                        description="操作类型: bind/unbind/update/update_offset")
    extra: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True),
                                  description="操作附加信息（如偏移量变更详情）")
    created_at: datetime = Field(default_factory=get_utc_now_factory(), description="创建时间")

    __table_args__ = (
        Index("idx_danmu_binding_history_file_id", "file_id"),
        Index("idx_danmu_binding_history_created_at", "created_at"),
    )
