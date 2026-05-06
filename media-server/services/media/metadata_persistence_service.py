"""元数据持久化服务（re-export facade）

实际实现已拆分到 persistence/ 包中：
- persistence/base.py          — 公共工具函数
- persistence/artwork_repo.py  — Artwork + ExternalID 持久化
- persistence/credit_repo.py   — Credit + Person 持久化
- persistence/genre_repo.py    — Genre + MediaCoreGenre 持久化
- persistence/version_repo.py  — MediaVersion 持久化
- persistence/core_repo.py     — MediaCore + Extension 表 CRUD
- persistence/orchestration.py — MetadataPersistenceService 编排入口

保持此文件以兼容现有导入路径。
"""
from services.media.persistence import MetadataPersistenceService

__all__ = ["MetadataPersistenceService"]
