"""
统一存储API路由

提供统一的存储操作接口，支持多种存储后端
"""

from ast import stmt
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlmodel import select
# 关键：导入 AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession  # ✅ 导入SQLModel的AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime
# 关键：使用异步 Session 获取函数
from core.db import AsyncSessionLocal
from core.security import get_current_subject, get_user_id
from services.storage.storage_service import storage_service
from models.storage_models import StorageConfig
from services.storage.storage_client import  StorageEntry
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# 请求/响应模型
class StorageListRequest(BaseModel):
    path: str = Field(default="/", description="目录路径")
    depth: int = Field(default=1, ge=1, le=5, description="递归深度")


class StorageListResponse(BaseModel):
    entries: List[StorageEntry] = Field(description="存储条目列表")
    path: str = Field(description="当前路径")
    total_count: int = Field(description="条目总数")
    


class StorageTestResponse(BaseModel):
    success: bool = Field(description="连接测试结果")
    message: Optional[str] = Field(None, description="错误信息（如果有）")
    response_time_ms: Optional[float] = Field(None, description="响应时间（毫秒）")


class StorageFileInfoResponse(BaseModel):
    name: str = Field(description="文件/目录名称")
    path: str = Field(description="完整路径")
    is_dir: bool = Field(description="是否为目录")
    size: Optional[int] = Field(None, description="文件大小（字节）")
    modified: Optional[datetime] = Field(None, description="修改时间")
    content_type: Optional[str] = Field(None, description="内容类型")
    etag: Optional[str] = Field(None, description="ETag")


class StorageInfoResponse(BaseModel):
    total_space: Optional[int] = Field(None, description="总空间（字节）")
    used_space: Optional[int] = Field(None, description="已用空间（字节）")
    free_space: Optional[int] = Field(None, description="可用空间（字节）")
    readonly: bool = Field(False, description="是否只读")
    supports_resume: bool = Field(False, description="是否支持断点续传")
    max_file_size: Optional[int] = Field(None, description="最大文件大小（字节）")


@router.get("/{storage_id}/test", response_model=StorageTestResponse)
async def test_storage_connection(
    storage_id: int = Path(..., description="存储配置ID"),
    # current_user: str = Depends(get_current_subject)
):
    """
    测试存储连接
    
    需要权限: storage:read
    """
    # user_id = get_user_id(current_user)
    
    import time
    start_time = time.time()
    try:
        success, error_message = await storage_service.test_connection(storage_id)
        response_time_ms = (time.time() - start_time) * 1000
        
        return StorageTestResponse(
            success=success,
            message=error_message,
            response_time_ms=round(response_time_ms, 2) if success else None
        )
        
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        return StorageTestResponse(
            success=False,
            message=f"连接测试异常: {str(e)}",
            response_time_ms=round(response_time_ms, 2)
        )


@router.get("/{storage_id}/list", response_model=StorageListResponse)
async def list_storage_directory(
    storage_id: int = Path(..., description="存储配置ID"),
    path: str = Query("/", description="目录路径"),
    depth: int = Query(1, description="递归深度, 默认1"),  
    # current_user: str = Depends(get_current_subject),
):
    """
    列出存储目录内容
    
    需要权限: storage:read
    """

    try:
        entries = await storage_service.list_directory(storage_id, path, depth)
   
        return StorageListResponse(
            entries=entries,
            path=path,
            total_count=len(entries), 
        )
        
    except Exception as e:
        logger.error(f"列出目录失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出目录失败: {str(e)}")

# /api/storage-server/{storage_id}/listdir
@router.get("/{storage_id}/listdir", response_model=StorageListResponse)
async def list_storage_only_directory(
    storage_id: int = Path(..., description="存储配置ID"),
    path: str = Query("/", description="目录路径"),
    depth: int = Query(1, description="递归深度, 默认1"),  
    # current_user: str = Depends(get_current_subject),
):
    """
    列出存储目录中的文件夹
    
    需要权限: storage:read
    """
    # logger.info(f"列出目录: {storage_id}, {path}, {depth}")
    # if path == "/":
    #     path = "/dav"
    if path == "/":
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(StorageConfig).where(StorageConfig.id == storage_id)
                storage_config = await session.exec(
                    stmt
                )
                storage_config = storage_config.first()
                path = storage_config.root_path or "/"
                
            except Exception as e:
                logger.error(f"列出目录失败: {e}")
    try:
        entries = await storage_service.list_directory(storage_id, path, depth)
        # 过滤出目录
        entries = [entry for entry in entries if entry.is_dir]
        return StorageListResponse(
            entries=entries,
            path=path,
            total_count=len(entries), 
        )
        
    except Exception as e:
        logger.error(f"列出目录失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出目录失败: {str(e)}")
    


@router.get("/{storage_id}/info", response_model=StorageInfoResponse)
async def get_storage_info(
    storage_id: int = Path(..., description="存储配置ID"),
    path: str = Query("/", description="路径"),
    # current_user: str = Depends(get_current_subject),
):
    """
    获取存储系统信息
    
    需要权限: storage:read
    """
    try:
        storage_info = await storage_service.get_storage_info(storage_id, path)
        
        return StorageInfoResponse(
            total_space=storage_info.total_space,
            used_space=storage_info.used_space,
            free_space=storage_info.free_space,
            readonly=storage_info.readonly,
            supports_resume=storage_info.supports_resume,
            max_file_size=storage_info.max_file_size
        )
    except Exception as e:
        logger.error(f"获取存储信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取存储信息失败: {str(e)}")


@router.get("/{storage_id}/file-info", response_model=StorageFileInfoResponse)
async def get_file_info(
    storage_id: int = Path(..., description="存储配置ID"),
    path: str = Query(..., description="文件或目录路径"),
    # current_user: str = Depends(get_current_subject),

):
    """
    获取文件/目录详细信息
    
    需要权限: storage:read
    """
    try:
        file_info = await storage_service.get_file_info(storage_id, path)
        
        return StorageFileInfoResponse(
            name=file_info.name,
            path=file_info.path,
            is_dir=file_info.is_dir,
            size=file_info.size,
            modified=file_info.modified,
            content_type=file_info.content_type,
            etag=file_info.etag
        )
        
    except Exception as e:
        logger.error(f"获取文件信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文件信息失败: {str(e)}")


@router.post("/{storage_id}/create-directory")
async def create_directory(
    storage_id: int = Path(..., description="存储配置ID"),
    path: str = Query(..., description="目录路径"),
):
    """
    创建目录
    
    需要权限: storage:write
    """
  
    try:
        success = await storage_service.create_directory(storage_id, path)
        
        if success:
            return {"message": "目录创建成功", "path": path}
        else:
            raise HTTPException(status_code=500, detail="目录创建失败")
            
    except Exception as e:
        logger.error(f"创建目录失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建目录失败: {str(e)}")


@router.delete("/{storage_id}/delete")
async def delete_path(
    storage_id: int = Path(..., description="存储配置ID"),
    path: str = Query(..., description="要删除的路径"),
 
):
    """
    删除文件或目录
    
    需要权限: storage:delete
    """
    try:
        success = await storage_service.delete_path(storage_id, path)

        if success:
            return {"message": "删除成功", "path": path}
        else:
            raise HTTPException(status_code=500, detail="删除失败")
            
    except Exception as e:
        logger.error(f"删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/{storage_id}/enable")
async def enable_storage(
    storage_id: int = Path(..., description="存储配置ID"),
    current_user: str = Depends(get_current_subject)
):
    """
    启用存储配置
    """
    user_id = get_user_id(current_user)
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(StorageConfig).where(
                StorageConfig.id == storage_id,
                StorageConfig.user_id == user_id
            )
            result = await session.exec(stmt)
            storage = result.first()

            if not storage:
                raise HTTPException(status_code=404, detail="未找到指定的存储配置")

            storage.is_active = True
            session.add(storage)
            await session.commit()
            await session.refresh(storage)

            return {
                "success": True,
                "message": "存储配置已启用",
                "id": storage.id,
                "is_active": storage.is_active
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用存储配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启用存储配置失败: {str(e)}")


@router.post("/{storage_id}/disable")
async def disable_storage(
    storage_id: int = Path(..., description="存储配置ID"),
    current_user: str = Depends(get_current_subject)
):
    """
    禁用存储配置
    """
    user_id = get_user_id(current_user)
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(StorageConfig).where(
                StorageConfig.id == storage_id,
                StorageConfig.user_id == user_id
            )
            result = await session.exec(stmt)
            storage = result.first()

            if not storage:
                raise HTTPException(status_code=404, detail="未找到指定的存储配置")

            storage.is_active = False
            session.add(storage)
            await session.commit()
            await session.refresh(storage)

            return {
                "success": True,
                "message": "存储配置已禁用",
                "id": storage.id,
                "is_active": storage.is_active
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"禁用存储配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"禁用存储配置失败: {str(e)}")


