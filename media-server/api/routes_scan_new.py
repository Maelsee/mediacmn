"""
统一扫描API路由 - 基于统一任务调度框架

提供现代化的扫描接口：
- 异步任务队列扫描
- 支持扫描+元数据组合任务
- 实时任务状态跟踪
- 完整的错误处理和重试机制
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from core.security import get_current_subject
from services.task import (
    get_unified_task_scheduler, TaskPriority, TaskType, TaskStatus
)
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scan"])


# 请求模型
class CreateScanTaskRequest(BaseModel):
    """创建扫描任务请求"""
    storage_id: int = Field(..., description="存储配置ID")
    scan_path: str = Field("/", description="扫描路径")
    scan_type: str = Field("full", description="扫描类型: full|incremental|quick")
    recursive: bool = Field(True, description="是否递归扫描")
    max_depth: int = Field(10, ge=1, le=20, description="最大扫描深度")
    enable_metadata_enrichment: bool = Field(True, description="是否启用元数据丰富")
    enable_delete_sync: bool = Field(True, description="是否启用删除同步")
    priority: str = Field("normal", description="任务优先级: low|normal|high|urgent")
    batch_size: int = Field(100, ge=10, le=1000, description="批量处理大小")


class CreateMetadataTaskRequest(BaseModel):
    """创建元数据任务请求"""
    storage_id: int = Field(..., description="存储配置ID")
    file_ids: List[int] = Field(..., description="文件ID列表")
    language: str = Field("zh-CN", description="语言")
    priority: str = Field("normal", description="任务优先级")
    batch_size: int = Field(50, ge=10, le=200, description="批量处理大小")


class TaskResponse(BaseModel):
    """任务响应"""
    success: bool
    message: str
    task_id: Optional[str] = None
    task_type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    task_type: str
    status: str
    priority: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    result: Optional[Dict] = None
    error: Optional[str] = None
    duration: float = 0.0


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskStatusResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


# 服务实例
task_scheduler = None


async def get_task_scheduler():
    """获取任务调度器实例"""
    global task_scheduler
    if task_scheduler is None:
        task_scheduler = await get_unified_task_scheduler()
    return task_scheduler

@router.get("/all", response_model=TaskResponse)
async def create_scan_all_task(
    current_user: str = Depends(get_current_subject),
):
    try:
        user_id = int(current_user)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid subject")

    try:
        from core.db import get_session
        from services.storage.storage_config_service import StorageConfigService
        svc = StorageConfigService()
        with next(get_session()) as db:
            storages = svc.list_user_storages(db, user_id, None)

        storages = [s for s in storages if s.get("status") in (None, "enabled", "healthy")]

        if not storages:
            return TaskResponse(success=True, message="无存储配置", task_id=None, status="idle")

        scheduler = await get_task_scheduler()
        pr = TaskPriority.NORMAL

        task_ids: List[str] = []
        for it in storages:
            sid = int(it["id"]) if not isinstance(it["id"], int) else it["id"]
            tid = await scheduler.create_scan_task(
                storage_id=sid,
                scan_path="/",
                recursive=True,
                max_depth=10,
                enable_metadata_enrichment=True,
                enable_delete_sync=True,
                user_id=user_id,
                priority=pr,
                batch_size=100,
            )
            task_ids.append(tid)

        group_id = f"grp-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"创建全量扫描任务组: {group_id}, tasks={len(task_ids)}")

        return TaskResponse(
            success=True,
            message="全量扫描任务已创建",
            task_id=group_id,
            task_type="combined_scan_group",
            status="pending",
            created_at=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建全量扫描任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建全量扫描任务失败: {str(e)}")


@router.post("/create-task", response_model=TaskResponse)
async def create_scan_task(
    request: CreateScanTaskRequest,
    current_user: str = Depends(get_current_subject)
):
    """
    创建扫描任务
    
    Args:
        request: 扫描任务请求
        current_user: 当前用户
        
    Returns:
        任务创建结果
    """
    try:
        logger.info(f"用户 {current_user} 创建扫描任务: 存储={request.storage_id}, 路径={request.scan_path}")
        
        # 获取任务调度器
        scheduler = await get_task_scheduler()
        
        # 转换优先级
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT
        }
        priority = priority_map.get(request.priority, TaskPriority.NORMAL)
        
        # 确定任务类型
        task_type = TaskType.COMBINED_SCAN if request.enable_metadata_enrichment else TaskType.SCAN
        
        # 创建任务
        task_id = await scheduler.create_scan_task(
            storage_id=request.storage_id,
            scan_path=request.scan_path,
            recursive=request.recursive,
            max_depth=request.max_depth,
            enable_metadata_enrichment=request.enable_metadata_enrichment,
            enable_delete_sync=request.enable_delete_sync,
            user_id=int(current_user),
            priority=priority,
            batch_size=request.batch_size
        )
        
        return TaskResponse(
            success=True,
            message="扫描任务已创建",
            task_id=task_id,
            task_type=task_type.value,
            status="pending",
            created_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"创建扫描任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建扫描任务失败: {str(e)}")


@router.post("/create-metadata-task", response_model=TaskResponse)
async def create_metadata_task(
    request: CreateMetadataTaskRequest,
    current_user: str = Depends(get_current_subject)
):
    """
    创建元数据丰富任务
    
    Args:
        request: 元数据任务请求
        current_user: 当前用户
        
    Returns:
        任务创建结果
    """
    try:
        logger.info(f"用户 {current_user} 创建元数据任务: 存储={request.storage_id}, 文件数={len(request.file_ids)}")
        
        # 获取任务调度器
        scheduler = await get_task_scheduler()
        
        # 转换优先级
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT
        }
        priority = priority_map.get(request.priority, TaskPriority.NORMAL)
        
        # 创建元数据任务
        task_ids = await scheduler.create_metadata_task(
            storage_id=request.storage_id,
            file_ids=request.file_ids,
            user_id=int(current_user),
            language=request.language,
            priority=priority,
            batch_size=request.batch_size
        )
        
        return TaskResponse(
            success=True,
            message=f"已创建 {len(task_ids)} 个元数据任务",
            task_id=task_ids[0] if task_ids else None,
            task_type=TaskType.METADATA_FETCH.value,
            status="pending",
            created_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"创建元数据任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建元数据任务失败: {str(e)}")


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: str = Depends(get_current_subject)
):
    """
    获取任务状态
    
    Args:
        task_id: 任务ID
        current_user: 当前用户
        
    Returns:
        任务状态
    """
    try:
        # 获取任务调度器
        scheduler = await get_task_scheduler()
        
        # 获取任务状态
        status_info = await scheduler.get_task_status(task_id, int(current_user))
        
        if not status_info:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return TaskStatusResponse(
            task_id=status_info["task_id"],
            task_type=status_info["task_type"],
            status=status_info["status"],
            priority=status_info["priority"],
            created_at=status_info["created_at"],
            started_at=status_info.get("started_at"),
            completed_at=status_info.get("completed_at"),
            progress=status_info.get("progress", 0.0),
            result=status_info.get("result"),
            error=status_info.get("error"),
            duration=status_info.get("duration", 0.0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")


@router.get("/tasks", response_model=TaskListResponse)
async def get_user_tasks(
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选: pending|running|completed|failed"),
    limit: int = Query(50, ge=1, le=200, description="限制数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: str = Depends(get_current_subject)
):
    """
    获取用户任务列表
    
    Args:
        task_type: 任务类型筛选
        status: 状态筛选
        limit: 限制数量
        offset: 偏移量
        current_user: 当前用户
        
    Returns:
        任务列表
    """
    try:
        # 获取任务调度器
        scheduler = await get_task_scheduler()
        
        # 转换任务类型
        task_type_enum = None
        if task_type:
            try:
                task_type_enum = TaskType(task_type)
            except ValueError:
                pass
        
        # 转换状态
        status_enum = None
        if status:
            try:
                status_enum = TaskStatus(status)
            except ValueError:
                pass
        
        # 获取用户任务列表
        result = await scheduler.get_user_tasks(
            user_id=int(current_user),
            task_type=task_type_enum,
            status=status_enum,
            limit=limit,
            offset=offset
        )
        
        # 转换响应格式
        tasks = []
        for task_info in result["tasks"]:
            tasks.append(TaskStatusResponse(
                task_id=task_info["task_id"],
                task_type=task_info["task_type"],
                status=task_info["status"],
                priority=task_info["priority"],
                created_at=task_info["created_at"],
                started_at=task_info.get("started_at"),
                completed_at=task_info.get("completed_at"),
                progress=task_info.get("progress", 0.0),
                result=task_info.get("result"),
                error=task_info.get("error"),
                duration=task_info.get("duration", 0.0)
            ))
        
        return TaskListResponse(
            tasks=tasks,
            total=result["total"],
            limit=limit,
            offset=offset,
            has_more=result["has_more"]
        )
        
    except Exception as e:
        logger.error(f"获取用户任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取用户任务列表失败: {str(e)}")


@router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: str = Depends(get_current_subject)
):
    """
    取消任务
    
    Args:
        task_id: 任务ID
        current_user: 当前用户
        
    Returns:
        取消结果
    """
    try:
        # 获取任务调度器
        scheduler = await get_task_scheduler()
        
        # 取消任务
        success = await scheduler.cancel_task(task_id, int(current_user))
        
        if success:
            return {
                "success": True,
                "message": "任务已取消"
            }
        else:
            raise HTTPException(status_code=400, detail="任务取消失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")



@router.get("/stats")
async def get_queue_stats(
    current_user: str = Depends(get_current_subject)
):
    """
    获取队列统计信息
    
    Args:
        current_user: 当前用户
        
    Returns:
        队列统计
    """
    try:
        # 获取任务调度器
        scheduler = await get_task_scheduler()
        
        # 获取队列统计
        stats = await scheduler.get_queue_stats()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"获取队列统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取队列统计失败: {str(e)}")
