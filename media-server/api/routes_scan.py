"""
统一扫描API路由 - 基于统一任务调度框架

提供现代化的扫描接口：
- 异步任务队列扫描
- 支持扫描+元数据组合任务
- 实时任务状态跟踪
- 完整的错误处理和重试机制
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlmodel import select

from core.security import get_current_subject, get_current_subject_or_query, get_user_id, verify_token
from core.db import AsyncSessionLocal
from core.config import get_settings
from models.storage_models import StorageConfig, WebdavStorageConfig, SmbStorageConfig
from services.task import producer
from services.task.state_store import TaskPriority, get_state_store
from services.task.scan_progress import get_scan_progress, CHANNEL_NAME

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# 请求与响应模型
# ============================================

class ScanRequest(BaseModel):
    """统一扫描任务请求"""
    storage_id: Optional[int] = Field(None, description="存储配置ID。如果不传则扫描所有已启用的存储。")
    scan_path: List[str] = Field(default_factory=list, description="扫描路径列表。如果扫描所有存储，此字段默认为 []。")
    priority: str = Field("normal", description="任务优先级: low|normal|high|urgent")


class TaskResponse(BaseModel):
    """任务创建响应"""
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
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ScanProgressResponse(BaseModel):
    scan_job_id: str
    status: str
    scanned_count: int
    pending_update_count: int
    updated_count: int


# ============================================
# 路由接口
# ============================================
# /api/scan/start
@router.post("/start", response_model=TaskResponse)
async def start_scan(
    request: ScanRequest,
    current_user: str = Depends(get_current_subject)
):
    """
    启动扫描任务
    
    支持两种模式：
    1. 全量扫描：不传 storage_id，扫描该用户下所有已启用的存储。
    2. 指定存储/路径扫描：传 storage_id，并配合 scan_path（默认为 "/"）进行扫描。
    """
    user_id = get_user_id(current_user)

    # 优先级映射
    priority_map = {
        "low": TaskPriority.LOW,
        "normal": TaskPriority.NORMAL,
        "high": TaskPriority.HIGH,
        "urgent": TaskPriority.URGENT
    }
    task_priority = priority_map.get(request.priority.lower(), TaskPriority.NORMAL)

    try:
        async with AsyncSessionLocal() as session:
            if request.storage_id is None:
                # 1. 全量扫描：获取用户所有已启用的存储
                stmt = select(StorageConfig).where(
                    StorageConfig.user_id == user_id,
                    StorageConfig.is_active == True
                    
                )
                result = await session.exec(stmt)
                storages = result.all()

                if not storages:
                    return TaskResponse(
                        success=True,
                        message="没有找到已启用的存储配置",
                        status="idle"
                    )

                task_ids = []
                for storage in storages:
                    scan_path = storage.root_path or "/"
                    tid = await producer.create_scan_task(
                        user_id=user_id,
                        storage_id=storage.id,
                        scan_path=scan_path,
                        priority=task_priority
                    )
                    task_ids.append(tid)

                return TaskResponse(
                    success=True,
                    message=f"已成功启动 {len(task_ids)} 个存储的全量扫描任务",
                    task_id=task_ids[0],
                    task_type="scan_batch",
                    status="pending",
                    created_at=datetime.now().isoformat()
                )

            else:
                # 2. 指定存储/路径扫描
                # 验证存储是否存在且属于该用户
                logger.info(f"request.storage_id: {request.storage_id}")
                stmt = select(StorageConfig).where(
                    StorageConfig.id == request.storage_id,
                    StorageConfig.user_id == user_id
                )
                result = await session.exec(stmt)
                storage = result.first()
                logger.info(f"storage: {storage}")

                if not storage:
                    raise HTTPException(status_code=404, detail="未找到指定的存储配置")
                
                base_root_path = storage.root_path or "/"
                target_paths = request.scan_path 
                
                task_ids = []
                logger.info(f"target_paths: {target_paths}")
                if not target_paths:
                    target_paths = [base_root_path]
                for path in target_paths:              
                    tid = await producer.create_scan_task(
                        user_id=user_id,
                        storage_id=storage.id,
                        scan_path=path,
                        priority=task_priority
                    )
                    task_ids.append(tid)

                return TaskResponse(
                    success=True,
                    message="扫描任务已成功启动",
                    task_id=task_ids[0],
                    task_type="scan",
                    status="pending",
                    created_at=datetime.now().isoformat()
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动扫描任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动扫描任务失败: {str(e)}")


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_scan_task_status(
    task_id: str,
    current_user: str = Depends(get_current_subject)
):
    """查询扫描任务状态"""
    store = get_state_store()
    task = await store.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
        
    # 安全性检查：确保任务属于当前用户
    payload = task.get("payload", {})
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except:
            payload = {}
            
    if str(payload.get("user_id")) != str(current_user):
        raise HTTPException(status_code=403, detail="无权访问该任务信息")
        
    return TaskStatusResponse(
        task_id=task.get("task_id"),
        task_type=task.get("task_type"),
        status=task.get("status"),
        created_at=task.get("created_at"),
        started_at=task.get("started_at") or None,
        finished_at=task.get("finished_at") or None,
        error_code=task.get("error_code") or None,
        error_message=task.get("error_message") or None,
        payload=payload
    )


@router.get("/progress/{task_id}", response_model=ScanProgressResponse)
async def get_scan_progress_api(
    task_id: str,
    current_user: str = Depends(get_current_subject),
):
    user_id = get_user_id(current_user)
    data = await get_scan_progress(user_id, task_id)
    if not data:
        raise HTTPException(status_code=404, detail="进度不存在")
    return ScanProgressResponse(
        scan_job_id=data["scan_job_id"],
        status=data["status"],
        scanned_count=data["scanned_count"],
        pending_update_count=data["pending_update_count"],
        updated_count=data["updated_count"],
    )


async def _authenticate_websocket(websocket: WebSocket) -> int:
    auth_header = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        qp = websocket.query_params
        token = qp.get("token") or qp.get("access_token") or qp.get("t")
    if not token:
        await websocket.close(code=4401)
        raise WebSocketDisconnect(code=4401)
    payload = verify_token(token)
    subject = payload.get("sub")
    if not subject:
        await websocket.close(code=4401)
        raise WebSocketDisconnect(code=4401)
    return get_user_id(str(subject))


@router.websocket("/ws/progress")
async def scan_progress_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        user_id = await _authenticate_websocket(websocket)
    except WebSocketDisconnect:
        return

    settings = get_settings()
    redis_client = redis.from_url(
        settings.REDIS_URL,
        db=settings.REDIS_DB,
        decode_responses=True,
    )
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNEL_NAME)

    subscribed_job_ids: set[str] = set()

    async def receiver() -> None:
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "subscribe":
                ids = data.get("job_ids") or []
                subscribed_job_ids.clear()
                for i in ids:
                    subscribed_job_ids.add(str(i))

    async def sender() -> None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                event = json.loads(message["data"])
            except Exception:
                continue
            event_user_id = event.get("user_id")
            if event_user_id is None or int(event_user_id) != int(user_id):
                continue
            job_id = str(event.get("job_id") or "")
            if subscribed_job_ids and job_id not in subscribed_job_ids:
                continue
            await websocket.send_text(json.dumps(event, ensure_ascii=False))

    try:
        await asyncio.gather(receiver(), sender())
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL_NAME)
            await pubsub.close()
        except Exception:
            pass
        await redis_client.close()
