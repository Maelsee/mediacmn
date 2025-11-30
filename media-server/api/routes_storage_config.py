"""
存储配置API路由 - 提供用户存储配置的管理接口。增删改查存储配置。

"""
from __future__ import annotations

from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlmodel import Session

import logging
from core.db import get_session
from core.security import get_current_subject
# 多租户架构：移除RBAC权限检查，仅保留用户认证
from services.storage.storage_config_service import StorageConfigService
from schemas.storage_serialization import CreateStorageRequest, CreateStorageResponse, ListUserStoragesResponse, UpdateStorageRequest
from services.storage.response_handler import StorageConfigResponseHandler
logger = logging.getLogger(__name__)

router = APIRouter()
storage_service = StorageConfigService()
response_handler = StorageConfigResponseHandler()


@router.get("/statistics", response_model=dict)
def get_storage_statistics(
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """获取用户存储配置的统计信息。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    
    statistics = storage_service.get_storage_statistics(db, user_id)
    return statistics  # 直接返回统计数据，符合response_model要求


@router.get("/", response_model=List[ListUserStoragesResponse])
def list_storages(
    storage_type: Optional[str] = Query(None, description="存储类型筛选 (webdav/smb/local/cloud)"),
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """列出当前用户的所有存储配置。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    
    storages = storage_service.list_user_storages(db, user_id, storage_type)
    return storages  # 直接返回列表，符合response_model要求


@router.get("/{storage_id}", response_model=dict)
def get_storage(
    storage_id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """获取指定存储配置的详细信息。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")

    storage_config = storage_service.get_storage_config(db, storage_id, user_id)
    if not storage_config:
        raise HTTPException(status_code=404, detail="Storage configuration not found")
    
    # 对敏感数据进行脱敏处理
    sanitized_config = response_handler.sanitize_storage_config(storage_config)
    return {"success": True, "message": "获取存储配置详情成功", "data": sanitized_config}


@router.post("/", response_model=CreateStorageResponse)
def create_storage(
    request: CreateStorageRequest,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """创建新的存储配置（包含基础信息和详细配置）。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    
    try:
        # 使用新的创建方法，同时创建基础配置和详细配置
        storage_config = storage_service.create_storage_with_config(db, user_id, request)
        
        response_data = {
            "id": storage_config.id,
            "name": storage_config.name,
            "storage_type": storage_config.storage_type,
            "created_at": storage_config.created_at.isoformat(),
            "updated_at": storage_config.updated_at.isoformat()
        }
        
        return response_data  # 直接返回响应数据，符合response_model要求
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建存储配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建存储配置失败")


@router.put("/{storage_id}", response_model=dict)
def update_storage(
    storage_id: int,
    request: UpdateStorageRequest,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """统一更新存储配置（基础信息 + 详细配置，支持多类型）。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    logger.info(f"更新存储配置 {storage_id}，请求参数：{request.model_dump()}")
    # 将请求交给服务层处理
    try:
        storage_config = storage_service.update_storage_config_unified(
            db,
            storage_id,
            user_id,
            name=request.name,
            is_active=request.is_active,
            priority=request.priority,
            config=request.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not storage_config:
        raise HTTPException(status_code=404, detail="Storage configuration not found")

    response_data = {
        "id": storage_config.id,
        "name": storage_config.name,
        "storage_type": storage_config.storage_type,
        "is_active": storage_config.is_active,
        "priority": storage_config.priority,
        "updated_at": storage_config.updated_at,
    }
    return response_data


@router.delete("/{storage_id}")
def delete_storage(
    storage_id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
):
    """删除存储配置（会级联删除相关配置）。"""
    try:
        user_id = int(current_subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")
    
    success = storage_service.delete_storage_config(db, storage_id, user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Storage configuration not found")
    
    return {"message": "Storage configuration deleted successfully"}  # 简化响应格式


