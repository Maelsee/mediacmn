"""元数据持久化包

拆分自 metadata_persistence_service.py，按实体类型分模块：
- base.py: 公共工具函数
- artwork_repo.py: Artwork + ExternalID 持久化
- credit_repo.py: Credit + Person 持久化
- genre_repo.py: Genre + MediaCoreGenre 持久化
- version_repo.py: MediaVersion 持久化
- core_repo.py: MediaCore + Extension 表 CRUD
- orchestration.py: MetadataPersistenceService 编排入口
"""
from .orchestration import MetadataPersistenceService

__all__ = ["MetadataPersistenceService"]
