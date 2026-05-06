"""
任务API路由 - 内部/开发者接口

提供统一的任务创建接口：scan/metadata/persist/delete/localize
以及任务状态查询接口。

注意：此路由面向开发者和内部系统调用。面向终端用户的扫描操作请使用
routes_scan.py（POST /scan/start），它提供多存储扫描和 WebSocket 进度推送。
"""
from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from core.security import get_current_subject
from services.task.producer import (
    create_scan_task,
    create_metadata_task,
    create_persist_task,
    create_delete_task,
    create_localize_task,
)
from services.task.state_store import get_state_store
from services.task.state_store import TaskStatus as _TS


logger = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])


class TaskCreateResponse(BaseModel):
    success: bool
    message: str
    task_id: str
    task_type: str
    status: str = Field(default="pending")


@router.post("/scan")
async def create_scan(
    storage_id: str = Query(..., description="存储ID"),
    scan_path: str = Query(..., description="扫描路径"),
    current_user: str = Depends(get_current_subject),
):
    try:
        logger.info(f"创建扫描任务: user_id={int(current_user)}, storage_id={int(storage_id)}, scan_path={scan_path}")
        task_id = await create_scan_task(int(current_user), int(storage_id), scan_path)
        logger.info(f"创建扫描任务成功: {task_id}")
        return TaskCreateResponse(success=True, message="扫描任务已创建", task_id=task_id, task_type="scan")
    except Exception as e:
        logger.error(f"创建扫描任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class MetadataBody(BaseModel):
    file_ids: List[int]
    storage_id: Optional[int] = None


@router.post("/metadata")
async def create_metadata(
    body: MetadataBody,
    current_user: str = Depends(get_current_subject),
):
    try:
        task_id = await create_metadata_task(int(current_user), body.file_ids, storage_id=body.storage_id)
        return TaskCreateResponse(success=True, message="元数据任务已创建", task_id=task_id, task_type="metadata")
    except Exception as e:
        logger.error(f"创建元数据任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PersistBody(BaseModel):
    file_id: int
    contract_type: str
    contract_payload: Dict[str, Any]
    path_info: Dict[str, Any] = Field(default_factory=dict)


@router.post("/persist")
async def create_persist(
    body: PersistBody,
    current_user: str = Depends(get_current_subject),
):
    try:
        task_id = await create_persist_task(
            int(current_user), 
            body.file_id, 
            body.contract_type, 
            body.contract_payload,
            body.path_info
        )
        return TaskCreateResponse(success=True, message="持久化任务已创建", task_id=task_id, task_type="persist")
    except Exception as e:
        logger.error(f"创建持久化任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DeleteBody(BaseModel):
    to_delete_ids: List[int]


@router.post("/delete")
async def create_delete(
    body: DeleteBody,
    current_user: str = Depends(get_current_subject),
):
    try:
        task_id = await create_delete_task(int(current_user), body.to_delete_ids)
        return TaskCreateResponse(success=True, message="删除同步任务已创建", task_id=task_id, task_type="delete")
    except Exception as e:
        logger.error(f"创建删除同步任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LocalizeBody(BaseModel):
    file_id: int
    storage_id: int

@router.post("/localize")
async def create_localize(
    body: LocalizeBody,
    current_user: str = Depends(get_current_subject),
):
    try:
        task_id = await create_localize_task(int(current_user), body.file_id, body.storage_id)
        return TaskCreateResponse(success=True, message="侧车本地化任务已创建", task_id=task_id, task_type="localize")
    except Exception as e:
        logger.error(f"创建侧车本地化任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_tasks(
    status: Optional[str] = Query(None, description="任务状态: pending/running/success/failed/deadletter"),
    type: Optional[str] = Query(None, description="任务类型: scan/metadata/persist/delete/localize"),
    limit: int = Query(50, ge=1, le=500, description="返回数量上限"),
):
    try:
        store = get_state_store()
        data = await store.list_tasks(status=status, task_type=type, limit=limit)
        return {"success": True, **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    try:
        store = get_state_store()
        data = await store.get_task(task_id)
        if not data:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True, "task": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dlq/requeue/{task_id}")
async def requeue_deadletter(task_id: str):
    try:
        store = get_state_store()
        data = await store.get_task(task_id)
        if not data:
            raise HTTPException(status_code=404, detail="任务不存在")
        if data.get("status") not in (_TS.DEADLETTER, _TS.FAILED):
            raise HTTPException(status_code=400, detail="任务不在可重入队状态")
        # 重置状态并重新入队
        await store.update_status(task_id, _TS.PENDING, updated_at=None, finished_at=None, error_code="", error_message="")
        from services.task.producer import _enqueue
        await _enqueue(data.get("queue"), data.get("task_type"), data.get("payload") or {})
        return {"success": True, "message": "任务已重新入队"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
