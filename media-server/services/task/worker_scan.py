"""扫描任务 Worker

处理 scan 队列中的扫描任务，完成后自动触发 delete 和 metadata 任务链。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from dramatiq import actor

from .broker import broker
from .state_store import get_state_store, TaskStatus, TaskPriority
from .scan_progress import init_scan_progress, update_scan_progress

import logging
logger = logging.getLogger(__name__)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat()


@actor(queue_name="scan", broker=broker)
async def scan_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到扫描任务：task_id={task_id}，payload={payload}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        from services.scan.unified_scan_engine import get_unified_scan_engine
        eng = await get_unified_scan_engine()

        user_id = payload.get("user_id")
        storage_id = payload.get("storage_id")
        scan_path = payload.get("scan_path")
        logger.info(f"📂 开始扫描：用户 {user_id}，存储 {storage_id}，路径 '{scan_path}'")

        if user_id is not None:
            try:
                await init_scan_progress(int(user_id), task_id)
            except Exception as e:
                logger.error(f"初始化扫描进度失败 task_id={task_id} user_id={user_id}: {e}", exc_info=True)

        async def _progress(scanned: int, media_found: int):
            try:
                await store.update_status(task_id, TaskStatus.RUNNING, updated_at=_now())
                if user_id is not None:
                    await update_scan_progress(int(user_id), task_id, scanned=scanned)
            except Exception as e:
                logger.error(f"任务 {task_id} 进度更新失败：{e}", exc_info=True)

        res = await eng.scan_storage(
            user_id=user_id,
            storage_id=storage_id,
            scan_path=scan_path,
            progress_cb=_progress,
        )
        logger.info(f"扫描任务 {task_id} 完成：新文件 {len(res.new_file_ids)} 个，已扫描文件 {res.total_files} 个，需要删除文件 {len(res.to_delete_ids)} 个")

        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps(
                {
                    "new_file_count": len(res.new_file_ids),
                    "total_files": res.total_files,
                    "media_files": res.media_files,
                }
            ),
        )

        if user_id is not None:
            try:
                pending_update = len(res.new_file_ids or []) + len(res.updated_files or [])
                await update_scan_progress(
                    int(user_id),
                    task_id,
                    scanned=res.total_files,
                    pending_update=pending_update,
                )
            except Exception as e:
                logger.error(f"更新扫描进度摘要失败 task_id={task_id} user_id={user_id}: {e}", exc_info=True)

        # 任务链：创建后续任务（删除对齐 + 元数据提取）
        from .producer import create_delete_task, create_metadata_task

        # 1. 创建删除对齐任务（幂等性保障）
        if res.to_delete_ids:
            try:
                file_key = ":".join(map(str, res.to_delete_ids if len(res.to_delete_ids) <= 5 else res.to_delete_ids[:5]))
                idempotency_key = f"delete:{user_id}:{storage_id}:{file_key}"
                await create_delete_task(
                    user_id=user_id,
                    to_delete_ids=res.to_delete_ids,
                    priority=TaskPriority.NORMAL,
                    idempotency_key=idempotency_key
                )
                logger.info(f"扫描任务 {task_id} 已创建删除任务：{idempotency_key}")
            except Exception as e:
                logger.error(f"扫描任务 {task_id} 创建删除任务失败：{e}", exc_info=True)

        # 2. 创建元数据提取任务
        logger.debug(f"扫描任务 {task_id} 准备创建元数据任务：新文件数 {len(res.new_file_ids)}")
        if res.all_file_ids:
            try:
                file_key = ":".join(map(str, res.all_file_ids[:] if len(res.all_file_ids) <= 10 else res.all_file_ids[:10]))
                idempotency_key = f"metadata:{user_id}:{storage_id}:{file_key}"
                await create_metadata_task(
                    user_id=user_id,
                    file_ids=res.all_file_ids,
                    storage_id=storage_id,
                    priority=TaskPriority.NORMAL,
                    idempotency_key=idempotency_key,
                    scan_task_id=task_id,
                )
                logger.info(f"扫描任务 {task_id} 已创建元数据任务：{idempotency_key}（{len(res.all_file_ids)} 个文件）")
            except Exception as e:
                logger.error(f"扫描任务 {task_id} 创建元数据任务失败：{e}", exc_info=True)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 扫描任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now()
        )
