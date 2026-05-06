"""本地化任务 Worker

处理 localize 队列中的 sidecar 本地化任务（NFO 写入、图片下载等）。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from dramatiq import actor

from .broker import broker
from .state_store import get_state_store, TaskStatus

import logging
logger = logging.getLogger(__name__)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat()


@actor(queue_name="localize", broker=broker)
async def localize_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到本地化任务：task_id={task_id}，file_id={payload.get('file_id')}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        file_id = payload.get("file_id")
        storage_id = payload.get("storage_id")
        if not file_id or not storage_id:
            raise ValueError("本地化任务缺少 file_id 或 storage_id 参数")

        from services.media.sidecar_localize_processor import SidecarLocalizeProcessor
        proc = SidecarLocalizeProcessor()

        await proc.process(int(file_id), storage_id=int(storage_id))
        logger.info(f"本地化任务 {task_id}：文件 {file_id} 处理完成")

        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"file_id": file_id, "storage_id": storage_id})
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 本地化任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now()
        )
