
import json
import logging
from typing import Dict, List, Optional, Union, Any, Type
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

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
        root_path = getattr(request.config, "root_path", "/") or "/"
        storage_config = StorageConfig(
            user_id=user_id,
            name=request.name,
            storage_type=request.storage_type,
            root_path=root_path
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
                if isinstance(config_update, BaseModel):
                    update_data = config_update.model_dump(exclude_unset=True)
                elif isinstance(config_update, dict):
                    update_data = config_update
                else:
                    raise ValueError("无效的存储配置更新数据")
                for k, v in update_data.items():
                    if k == "select_path" and isinstance(v, list):
                        v = json.dumps(v)
                    setattr(detail_config, k, v)
                root_path_val = None
                if isinstance(config_update, BaseModel) and hasattr(config_update, "root_path"):
                    root_path_val = getattr(config_update, "root_path")
                elif isinstance(config_update, dict):
                    root_path_val = config_update.get("root_path")
                if root_path_val is not None:
                    storage_config.root_path = root_path_val or "/"
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
