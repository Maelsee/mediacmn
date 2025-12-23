"""存储配置服务层 - 统一管理所有存储类型配置。"""
# from __future__ import annotations

# from typing import Dict, List, Optional, Union, Any
# from sqlmodel import Session, select
# import logging
# logger = logging.getLogger(__name__)

# from models.storage_models import (
#     StorageConfig,
#     WebdavStorageConfig,
#     SmbStorageConfig,
#     LocalStorageConfig,
#     CloudStorageConfig,
#     StorageStatus
# )
# from schemas.storage_serialization import (
#     WebdavConfig,
#     SmbConfig,
#     LocalConfig,
#     CloudConfig,
#     CreateStorageRequest,
#     ListUserStoragesResponse,
#     WebdavConfigUpdate,
#     SmbConfigUpdate,
#     LocalConfigUpdate,
#     CloudConfigUpdate,
#     UpdateStorageRequest
# )



# class StorageConfigService:
#     """存储配置统一服务类。"""
    
#     def __init__(self):
#         pass
    
#     def get_storage_config(self, db: Session, storage_id: int, user_id: int) -> Optional[Dict[str, Any]]:
#         """获取存储配置的完整信息。"""
#         # 获取基础配置
#         stmt = select(StorageConfig).where(
#             StorageConfig.id == storage_id,
#             StorageConfig.user_id == user_id
#         )
#         storage_config = db.exec(stmt).first()
#         # logger.info(f"storage_config: {storage_config}")
#         if not storage_config:
#             return None
        
#         # 根据存储类型获取详细配置
#         detail_config = None
#         if storage_config.storage_type == "webdav":
#             detail_stmt = select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#             # logger.info(f"detail_config: {detail_config}")
#         elif storage_config.storage_type == "smb":
#             detail_stmt = select(SmbStorageConfig).where(SmbStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#         elif storage_config.storage_type == "local":
#             detail_stmt = select(LocalStorageConfig).where(LocalStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#         elif storage_config.storage_type == "cloud":
#             detail_stmt = select(CloudStorageConfig).where(CloudStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#         logger.info(f"查询的详细配置: {detail_config}")
        
#         if not detail_config:
#             return None 
#         return {
#             "id": storage_config.id,
#             "user_id": storage_config.user_id,
#             "name": storage_config.name,
#             "storage_type": storage_config.storage_type,       
#             "created_at": storage_config.created_at,
#             "updated_at": storage_config.updated_at,            
#             "detail": detail_config
#         }
    
#     def list_user_storages(self, db: Session, user_id: int, storage_type: Optional[str] = None) -> ListUserStoragesResponse:
#         """列出用户的所有存储配置。"""   
#         stmt = select(StorageConfig).where(StorageConfig.user_id == user_id)
        
#         if storage_type:
#             stmt = stmt.where(StorageConfig.storage_type == storage_type)
        
#         # 按创建时间降序排序，最新的在前面
#         stmt = stmt.order_by(StorageConfig.created_at.asc())
        
#         storage_configs = db.exec(stmt).all()
        
#         results = []
#         for config in storage_configs:
#             result = {
#                 "id": config.id,
#                 "user_id": config.user_id,
#                 "name": config.name,
#                 "storage_type": config.storage_type,
#             }
            
#             # 获取状态信息
#             status_stmt = select(StorageStatus).where(StorageStatus.storage_id == config.id)
#             status = db.exec(status_stmt).first()
#             if status:
#                 result["status"] =  status.status
#             else:
#                 result["status"] = None

#             results.append(result)
     
#         return results
    
#     def create_storage_config(self, db: Session, user_id: int, name: str, storage_type: str, ) -> StorageConfig:
#         """创建基础存储配置。"""
#         # 检查名称是否已存在
#         existing_stmt = select(StorageConfig).where(
#             StorageConfig.user_id == user_id,
#             StorageConfig.name == name
#         )
#         if db.exec(existing_stmt).first():
#             raise ValueError(f"存储配置名称 '{name}' 已存在")
        
#         storage_config = StorageConfig(
#             user_id=user_id,
#             name=name,
#             storage_type=storage_type,
            
#         )
        
#         db.add(storage_config)
#         db.commit()
#         db.refresh(storage_config)
        
#         return storage_config
    
#     def create_storage_with_config(self, db: Session, user_id: int, request: CreateStorageRequest) -> StorageConfig:
#         """创建完整的存储配置（包含基础信息和详细配置）。"""
#         # 首先创建基础配置
#         storage_config = self.create_storage_config(
#             db, user_id, request.name, request.storage_type
#         )
        
#         # 然后根据存储类型创建详细配置
#         try:
#             if request.storage_type == "webdav":
#                 self._create_webdav_config(db, storage_config.id, request.config)
#             elif request.storage_type == "smb":
#                 self._create_smb_config(db, storage_config.id, request.config)
#             elif request.storage_type == "local":
#                 self._create_local_config(db, storage_config.id, request.config)
#             elif request.storage_type == "cloud":
#                 self._create_cloud_config(db, storage_config.id, request.config)
#             else:
#                 raise ValueError(f"不支持的存储类型: {request.storage_type}")
#         except Exception as e:
#             # 如果详细配置创建失败，回滚基础配置
#             db.delete(storage_config)
#             db.commit()
#             raise ValueError(f"创建详细配置失败: {str(e)}")
        
#         return storage_config
    
#     def _create_webdav_config(self, db: Session, storage_config_id: int, config: WebdavConfig) -> WebdavStorageConfig:
#         """创建WebDAV详细配置。"""
#         import json
#         webdav_config = WebdavStorageConfig(
#             storage_config_id=storage_config_id,
#             hostname=config.hostname,
#             login=config.login,
#             password=config.password,
#             # token=config.token,
#             root_path=config.root_path,
#             select_path=json.dumps(config.select_path),  # 将列表转换为JSON字符串
            
#             timeout_seconds=config.timeout_seconds,
#             verify_ssl=config.verify_ssl,
#             pool_connections=config.pool_connections,
#             pool_maxsize=config.pool_maxsize,
#             retries_total=config.retries_total,
#             retries_backoff_factor=config.retries_backoff_factor,
#             retries_status_forcelist=config.retries_status_forcelist,
#             custom_headers=config.custom_headers,
#             proxy_config=config.proxy_config
#         )
        
#         db.add(webdav_config)
#         db.commit()
#         db.refresh(webdav_config)
        
#         return webdav_config
    
#     def _create_smb_config(self, db: Session, storage_config_id: int, config: SmbConfig) -> SmbStorageConfig:
#         """创建SMB详细配置。"""
#         smb_config = SmbStorageConfig(
#             storage_config_id=storage_config_id,
#             server_host=config.server_host,
#             server_port=config.server_port,
#             share_name=config.share_name,
#             username=config.username,
#             password=config.password,
#             domain=config.domain,
#             client_name=config.client_name,
#             use_ntlm_v2=config.use_ntlm_v2,
#             sign_options=config.sign_options,
#             is_direct_tcp=config.is_direct_tcp
#         )
        
#         db.add(smb_config)
#         db.commit()
#         db.refresh(smb_config)
        
#         return smb_config
    
#     def _create_local_config(self, db: Session, storage_config_id: int, config: LocalConfig) -> LocalStorageConfig:
#         """创建本地存储详细配置。"""
#         local_config = LocalStorageConfig(
#             storage_config_id=storage_config_id,
#             base_path=config.base_path,
#             auto_create_dirs=config.auto_create_dirs,
#             use_symlinks=config.use_symlinks,
#             follow_symlinks=config.follow_symlinks,
#             scan_depth_limit=config.scan_depth_limit,
#             exclude_patterns=config.exclude_patterns
#         )
        
#         db.add(local_config)
#         db.commit()
#         db.refresh(local_config)
        
#         return local_config
    
#     def _create_cloud_config(self, db: Session, storage_config_id: int, config: CloudConfig) -> CloudStorageConfig:
#         """创建云盘存储详细配置。"""
#         cloud_config = CloudStorageConfig(
#             storage_config_id=storage_config_id,
#             cloud_provider=config.cloud_provider,
#             access_token=config.access_token,
#             refresh_token=config.refresh_token,
#             client_id=config.client_id,
#             client_secret=config.client_secret,
#             root_folder_id=config.root_folder_id,
#             sync_interval=config.sync_interval,
#             max_file_size=config.max_file_size
#         )
        
#         db.add(cloud_config)
#         db.commit()
#         db.refresh(cloud_config)
        
#         return cloud_config
    
#     def update_storage_config(self, db: Session, storage_id: int, user_id: int, 
#                              name: Optional[str] = None, is_active: Optional[bool] = None,
#                              priority: Optional[int] = None, 
#                              webdav_config: Optional[Dict[str, Any]] = None) -> Optional[StorageConfig]:
#         """更新基础存储配置和详细配置。"""
#         stmt = select(StorageConfig).where(
#             StorageConfig.id == storage_id,
#             StorageConfig.user_id == user_id
#         )
#         storage_config = db.exec(stmt).first()
        
#         if not storage_config:
#             return None
        
#         if name is not None:
#             # 检查新名称是否已存在
#             name_stmt = select(StorageConfig).where(
#                 StorageConfig.user_id == user_id,
#                 StorageConfig.name == name,
#                 StorageConfig.id != storage_id
#             )
#             if db.exec(name_stmt).first():
#                 raise ValueError(f"存储配置名称 '{name}' 已存在")
#             storage_config.name = name
        
#         if is_active is not None:
#             storage_config.is_active = is_active
        
#         if priority is not None:
#             storage_config.priority = priority
        
#         # 更新WebDAV详细配置
#         if webdav_config and storage_config.storage_type == "webdav":
#             detail_stmt = select(WebdavStorageConfig).where(
#                 WebdavStorageConfig.storage_config_id == storage_id
#             )
#             detail_config = db.exec(detail_stmt).first()
            
#             if detail_config:
#                 # 更新现有配置
#                 for key, value in webdav_config.items():
#                     if value is not None and hasattr(detail_config, key):
#                         # 特殊处理select_path：如果是数组则转换为JSON字符串
#                         if key == "select_path" and isinstance(value, list):
#                             import json
#                             value = json.dumps(value)
#                         setattr(detail_config, key, value)
#                 db.add(detail_config)
        
#         db.add(storage_config)
#         db.commit()
#         db.refresh(storage_config)
        
#         return storage_config

#     def update_storage_config_unified(
#         self,
#         db: Session,
#         storage_id: int,
#         user_id: int,
#         name: Optional[str] = None,
#         is_active: Optional[bool] = None,
#         priority: Optional[int] = None,
#         config: Optional[Union[WebdavConfigUpdate, SmbConfigUpdate, LocalConfigUpdate, CloudConfigUpdate]] = None,
#     ) -> Optional[StorageConfig]:
#         """统一更新基础配置与详细配置，支持多类型。"""
#         stmt = select(StorageConfig).where(
#             StorageConfig.id == storage_id,
#             StorageConfig.user_id == user_id
#         )
#         storage_config = db.exec(stmt).first()
#         if not storage_config:
#             return None

#         if name is not None:
#             name_stmt = select(StorageConfig).where(
#                 StorageConfig.user_id == user_id,
#                 StorageConfig.name == name,
#                 StorageConfig.id != storage_id
#             )
#             if db.exec(name_stmt).first():
#                 raise ValueError(f"存储配置名称 '{name}' 已存在")
#             storage_config.name = name

#         if is_active is not None:
#             storage_config.is_active = is_active

#         if priority is not None:
#             storage_config.priority = priority

#         if config is not None:
#             st = storage_config.storage_type
#             if st == "webdav" and isinstance(config, WebdavConfigUpdate):
#                 detail_stmt = select(WebdavStorageConfig).where(
#                     WebdavStorageConfig.storage_config_id == storage_id
#                 )
#                 detail_config = db.exec(detail_stmt).first()
#                 if detail_config:
#                     import json
#                     for key, value in config.model_dump(exclude_unset=True).items():
#                         if key == "select_path" and isinstance(value, list):
#                             value = json.dumps(value)
#                         setattr(detail_config, key, value)
#                     db.add(detail_config)
#             elif st == "smb" and isinstance(config, SmbConfigUpdate):
#                 detail_stmt = select(SmbStorageConfig).where(
#                     SmbStorageConfig.storage_config_id == storage_id
#                 )
#                 detail_config = db.exec(detail_stmt).first()
#                 if detail_config:
#                     for key, value in config.model_dump(exclude_unset=True).items():
#                         setattr(detail_config, key, value)
#                     db.add(detail_config)
#             elif st == "local" and isinstance(config, LocalConfigUpdate):
#                 detail_stmt = select(LocalStorageConfig).where(
#                     LocalStorageConfig.storage_config_id == storage_id
#                 )
#                 detail_config = db.exec(detail_stmt).first()
#                 if detail_config:
#                     for key, value in config.model_dump(exclude_unset=True).items():
#                         setattr(detail_config, key, value)
#                     db.add(detail_config)
#             elif st == "cloud" and isinstance(config, CloudConfigUpdate):
#                 detail_stmt = select(CloudStorageConfig).where(
#                     CloudStorageConfig.storage_config_id == storage_id
#                 )
#                 detail_config = db.exec(detail_stmt).first()
#                 if detail_config:
#                     for key, value in config.model_dump(exclude_unset=True).items():
#                         setattr(detail_config, key, value)
#                     db.add(detail_config)
#             else:
#                 raise ValueError(f"更新的配置类型与存储类型不匹配: {st}")

#         db.add(storage_config)
#         db.commit()
#         db.refresh(storage_config)
#         return storage_config
    
#     def delete_storage_config(self, db: Session, storage_id: int, user_id: int) -> bool:
#         """删除存储配置（级联删除相关配置）。"""
#         stmt = select(StorageConfig).where(
#             StorageConfig.id == storage_id,
#             StorageConfig.user_id == user_id
#         )
#         storage_config = db.exec(stmt).first()
        
#         if not storage_config:
#             return False
        
#         # 根据存储类型删除对应的详细配置
#         if storage_config.storage_type == "webdav":
#             detail_stmt = select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#             if detail_config:
#                 db.delete(detail_config)
#         elif storage_config.storage_type == "smb":
#             detail_stmt = select(SmbStorageConfig).where(SmbStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#             if detail_config:
#                 db.delete(detail_config)
#         elif storage_config.storage_type == "local":
#             detail_stmt = select(LocalStorageConfig).where(LocalStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#             if detail_config:
#                 db.delete(detail_config)
#         elif storage_config.storage_type == "cloud":
#             detail_stmt = select(CloudStorageConfig).where(CloudStorageConfig.storage_config_id == storage_id)
#             detail_config = db.exec(detail_stmt).first()
#             if detail_config:
#                 db.delete(detail_config)
        
#         # 删除状态记录
#         status_stmt = select(StorageStatus).where(StorageStatus.storage_id == storage_id)
#         status = db.exec(status_stmt).first()
#         if status:
#             db.delete(status)
        
#         # 删除基础配置
#         db.delete(storage_config)
#         db.commit()
        
#         return True
    
#     def get_storage_statistics(self, db: Session, user_id: int) -> Dict[str, Any]:
#         """获取用户存储配置的统计信息。"""
#         stmt = select(StorageConfig).where(StorageConfig.user_id == user_id)
#         all_storages = db.exec(stmt).all()
        
#         total_count = len(all_storages)
#         active_count = sum(1 for s in all_storages if s.is_active)
        
#         type_counts = {}
#         for storage in all_storages:
#             type_counts[storage.storage_type] = type_counts.get(storage.storage_type, 0) + 1
        
#         # 获取状态统计
#         status_stmt = select(StorageStatus).where(
#             StorageStatus.storage_id.in_([s.id for s in all_storages])
#         )
#         statuses = db.exec(status_stmt).all()
        
#         healthy_count = sum(1 for s in statuses if s.status == "healthy")
#         error_count = sum(1 for s in statuses if s.status == "error")
        
#         return {
#             "total_storages": total_count,
#             "active_storages": active_count,
#             "storage_types": type_counts,
#             "healthy_storages": healthy_count,
#             "error_storages": error_count,
#         }

import json
import logging
from typing import Dict, List, Optional, Union, Any, Type
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from models.storage_models import (
    StorageConfig, WebdavStorageConfig, SmbStorageConfig,
    LocalStorageConfig, CloudStorageConfig, StorageStatus
)
from schemas.storage_serialization import (
    CreateStorageRequest, UpdateStorageRequest, 
    WebdavConfig, SmbConfig, LocalConfig, CloudConfig
)

logger = logging.getLogger(__name__)

class StorageConfigService:
    """优化后的异步存储配置统一服务类"""

    # 类型到模型的映射字典，用于消除重复逻辑
    TYPE_MAP: Dict[str, Type] = {
        "webdav": WebdavStorageConfig,
        "smb": SmbStorageConfig,
        "local": LocalStorageConfig,
        "cloud": CloudStorageConfig
    }

    async def get_storage_config(self, db: AsyncSession, storage_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """获取存储配置的完整异步信息"""
        # 获取基础配置
        stmt = select(StorageConfig).where(StorageConfig.id == storage_id, StorageConfig.user_id == user_id)
        storage_config = (await db.exec(stmt)).first()
        if not storage_config:
            return None
        
        # 自动获取详细配置
        detail_model = self.TYPE_MAP.get(storage_config.storage_type)
        detail_stmt = select(detail_model).where(detail_model.storage_config_id == storage_id)
        detail_config = (await db.exec(detail_stmt)).first()
        
        return {
            **storage_config.model_dump(),
            "detail": detail_config
        }

    async def list_user_storages(self, db: AsyncSession, user_id: int, storage_type: Optional[str] = None) -> List[Dict]:
        """异步列出用户的所有存储配置及其状态"""
        stmt = select(StorageConfig).where(StorageConfig.user_id == user_id)
        if storage_type:
            stmt = stmt.where(StorageConfig.storage_type == storage_type)
        
        storage_configs = (await db.exec(stmt.order_by(StorageConfig.created_at.asc()))).all()
        
        results = []
        for config in storage_configs:
            # 使用 Join 或子查询优化性能，此处暂保逻辑清晰
            status_stmt = select(StorageStatus).where(StorageStatus.storage_id == config.id)
            status = (await db.exec(status_stmt)).first()
            
            res = config.model_dump()
            res["status"] = status.status if status else None
            results.append(res)
        return results

    async def create_storage_config(self, db: AsyncSession, user_id: int, request: CreateStorageRequest) -> StorageConfig:
        """异步创建完整存储配置（含事务处理）"""
        # 1. 检查重名
        existing = await db.exec(select(StorageConfig).where(
            StorageConfig.user_id == user_id, StorageConfig.name == request.name
        ))
        if existing.first():
            raise ValueError(f"存储配置名称 '{request.name}' 已存在")

        # 2. 开启事务创建
        storage_config = StorageConfig(
            user_id=user_id,
            name=request.name,
            storage_type=request.storage_type
        )
        db.add(storage_config)
        await db.flush() # 获取生成的 ID

        try:
            detail_model = self.TYPE_MAP.get(request.storage_type)
            # 统一参数预处理
            config_data = request.config.model_dump()
            
            # 特殊逻辑合并：处理需要序列化的字段
            if "select_path" in config_data and isinstance(config_data["select_path"], list):
                config_data["select_path"] = json.dumps(config_data["select_path"])
            
            detail_config = detail_model(storage_config_id=storage_config.id, **config_data)
            db.add(detail_config)
            
            await db.commit()
            await db.refresh(storage_config)
            return storage_config
        except Exception as e:
            await db.rollback()
            logger.error(f"创建详细配置失败: {e}")
            raise ValueError(f"详细配置写入失败: {str(e)}")

    async def update_storage_config(
        self, db: AsyncSession, storage_id: int, user_id: int, **kwargs
    ) -> Optional[StorageConfig]:
        """统一异步更新接口"""
        stmt = select(StorageConfig).where(StorageConfig.id == storage_id, StorageConfig.user_id == user_id)
        storage_config = (await db.exec(stmt)).first()
        if not storage_config:
            return None

        # 更新基础字段
        for field in ["name", "is_active", "priority"]:
            if (val := kwargs.get(field)) is not None:
                setattr(storage_config, field, val)

        # 更新详细字段
        config_update = kwargs.get("config")
        if config_update:
            detail_model = self.TYPE_MAP.get(storage_config.storage_type)
            detail_stmt = select(detail_model).where(detail_model.storage_config_id == storage_id)
            detail_config = (await db.exec(detail_stmt)).first()
            
            if detail_config:
                update_data = config_update.model_dump(exclude_unset=True)
                for k, v in update_data.items():
                    if k == "select_path" and isinstance(v, list):
                        v = json.dumps(v)
                    setattr(detail_config, k, v)
                db.add(detail_config)

        db.add(storage_config)
        await db.commit()
        await db.refresh(storage_config)
        return storage_config

    async def delete_storage_config(self, db: AsyncSession, storage_id: int, user_id: int) -> bool:
        """异步删除配置及关联数据"""
        stmt = select(StorageConfig).where(StorageConfig.id == storage_id, StorageConfig.user_id == user_id)
        storage_config = (await db.exec(stmt)).first()
        if not storage_config:
            return False

        # 自动识别类型并删除关联表
        detail_model = self.TYPE_MAP.get(storage_config.storage_type)
        await db.exec(delete(detail_model).where(detail_model.storage_config_id == storage_id))
        await db.exec(delete(StorageStatus).where(StorageStatus.storage_id == storage_id))
        
        await db.delete(storage_config)
        await db.commit()
        return True

    async def get_storage_statistics(self, db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """异步统计信息"""
        stmt = select(StorageConfig).where(StorageConfig.user_id == user_id)
        all_storages = (await db.exec(stmt)).all()
        
        ids = [s.id for s in all_storages]
        status_stmt = select(StorageStatus).where(StorageStatus.storage_id.in_(ids))
        statuses = (await db.exec(status_stmt)).all() if ids else []

        return {
            "total_storages": len(all_storages),
            "active_storages": sum(1 for s in all_storages if s.is_active),
            "healthy_storages": sum(1 for s in statuses if s.status == "healthy"),
            "error_storages": sum(1 for s in statuses if s.status == "error"),
            "storage_types": {t: sum(1 for s in all_storages if s.storage_type == t) for t in self.TYPE_MAP.keys()}
        }