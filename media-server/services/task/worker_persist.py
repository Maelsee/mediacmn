"""持久化任务 Worker

处理 persist 和 persist_batch 队列中的元数据持久化任务。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from dramatiq import actor

from .broker import broker
from .state_store import get_state_store, TaskStatus
from .scan_progress import update_scan_progress

import logging
logger = logging.getLogger(__name__)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat()


@actor(queue_name="persist", broker=broker)
async def persist_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到持久化任务：task_id={task_id}，file_id={payload.get('file_id')}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        file_id = payload.get("file_id")
        if not file_id:
            raise ValueError("持久化任务缺少 file_id 参数")

        from services.media.metadata_persistence_service import MetadataPersistenceService
        from core.db import AsyncSessionLocal
        from models.media_models import FileAsset

        svc = MetadataPersistenceService()

        def _sync_persist(sync_session):
            media_file = sync_session.get(FileAsset, file_id)
            if not media_file:
                raise ValueError(f"文件 {file_id} 不存在")

            contract_type = payload.get("contract_type", "unknown")
            contract_payload = payload.get("contract_payload", {})
            path_info = payload.get("path_info", {})

            svc.apply_metadata(sync_session, media_file, metadata=contract_payload, metadata_type=contract_type, path_info=path_info)
            sync_session.commit()
            logger.info(f"持久化任务 {task_id}：文件 {file_id} 元数据已保存")

        async with AsyncSessionLocal() as async_session:
            await async_session.run_sync(_sync_persist)

        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"file_id": file_id, "contract_type": payload.get("contract_type")})
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 持久化任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now()
        )


@actor(queue_name="persist_batch", broker=broker)
async def persist_batch_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到批量持久化任务：task_id={task_id}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        items = payload.get("items", [])
        if not items:
            raise ValueError("持久化批量任务缺少 items 参数")

        from services.media.metadata_persistence_async_service import MetadataPersistenceAsyncService

        svc = MetadataPersistenceAsyncService()
        result = await svc.apply_metadata_batch(items)
        logger.info(f"批量持久化任务 {task_id}：{result}")
        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps(result),
        )

        scan_task_id = payload.get("scan_task_id")
        user_id = payload.get("user_id")
        if scan_task_id and user_id is not None and items:
            try:
                await update_scan_progress(int(user_id), scan_task_id, updated_delta=len(items))
            except Exception as e:
                logger.error(
                    f"更新扫描进度已更新数量失败 scan_task_id={scan_task_id} user_id={user_id}: {e}",
                    exc_info=True,
                )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 批量持久化任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now(),
        )
