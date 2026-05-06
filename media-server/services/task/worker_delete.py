"""删除任务 Worker

处理 delete 队列中的文件删除对齐任务。
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


@actor(queue_name="delete", broker=broker)
async def delete_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到删除任务：task_id={task_id}，storage_id={payload.get('storage_id')}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        from services.scan.file_asset_repository import get_file_asset_repo
        repo = await get_file_asset_repo()

        to_delete_ids = payload.get("to_delete_ids", [])
        user_id = payload.get("user_id")
        cleanup_stats = await repo.delete_files_by_ids(to_delete_ids, user_id)
        logger.info(f"清理完成，删除文件数: {cleanup_stats.get('deleted_assets', 0)}，清理孤立核心数: {cleanup_stats.get('cleaned_cores', 0)}")

        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"deleted_file_count": cleanup_stats.get('deleted_assets', 0), "cleaned_cores": cleanup_stats.get('cleaned_cores', 0)})
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 删除任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now()
        )
