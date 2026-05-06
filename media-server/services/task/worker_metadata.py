"""元数据任务 Worker

处理 metadata 队列中的元数据刮削任务，完成后自动触发 persist_batch 任务链。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from dramatiq import actor

from .broker import broker
from .state_store import get_state_store, TaskStatus

import logging
logger = logging.getLogger(__name__)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat()


@actor(queue_name="metadata", broker=broker)
async def metadata_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到元数据任务：task_id={task_id}，file_ids={payload.get('file_ids', [])}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        from services.media.metadata_enricher import metadata_enricher
        from .producer import create_persist_batch_task

        from services.scraper.manager import scraper_manager
        if not scraper_manager.is_running:
            logger.warning("插件系统未在项目启动时初始化，尝试执行补救启动...")
            from core.config import get_settings
            settings = get_settings()
            timeout_s = float(getattr(settings, "SCRAPER_PLUGIN_STARTUP_TIMEOUT_SECONDS", 20.0))
            try:
                await asyncio.wait_for(scraper_manager.startup(), timeout=timeout_s)
            except asyncio.TimeoutError:
                raise RuntimeError(f"插件系统启动超时（{timeout_s}s）")

        user_id = payload.get("user_id")
        file_ids = payload.get("file_ids", [])
        if not user_id or not file_ids:
            raise ValueError(f"元数据任务缺少必要参数：user_id={user_id}, file_ids={file_ids}")

        logger.info(f"📦 开始批量处理元数据：共 {len(file_ids)} 个文件")

        persist_task_count = 0
        valid_result_count = 0

        batch_items: List[Dict[str, Any]] = []
        BATCH_SIZE = 100
        batch_number = 1

        async for result in metadata_enricher.iter_enrich_multiple_files(
            file_ids=file_ids, user_id=user_id, max_concurrency=20
        ):
            if not result.get("success") or not result.get("contract_payload") or result.get("file_id") not in file_ids:
                logger.warning(f"⚠️ 跳过无效元数据结果：file_id={result.get('file_id')}, contract_payload={bool(result.get('contract_payload'))}")
                continue
            valid_result_count += 1
            batch_items.append(
                {
                    "file_id": result.get("file_id"),
                    "contract_type": result.get("contract_type"),
                    "contract_payload": result.get("contract_payload"),
                    "path_info": result.get("path_info") or {},
                }
            )

            if len(batch_items) >= BATCH_SIZE:
                try:
                    idempotency_key = f"persist_batch:{user_id}:{task_id}:batch_{batch_number}"
                    await create_persist_batch_task(
                        user_id=user_id,
                        items=batch_items,
                        scan_task_id=payload.get("scan_task_id"),
                        idempotency_key=idempotency_key,
                    )
                    persist_task_count += len(batch_items)
                    logger.info(
                        f"✅ 元数据任务 {task_id} 已创建第 {batch_number} 批持久化任务："
                        f"批次大小={len(batch_items)}, 累计持久化={persist_task_count}"
                    )
                    batch_items.clear()
                    batch_number += 1
                except Exception:
                    logger.error(
                        f"❌ 元数据任务 {task_id} 创建第 {batch_number} 批持久化任务失败",
                        exc_info=True
                    )
                    batch_items.clear()
                    batch_number += 1

        # 处理剩余不足100条的最后一批数据
        if batch_items:
            try:
                idempotency_key = f"persist_batch:{user_id}:{task_id}:batch_{batch_number}"
                await create_persist_batch_task(
                    user_id=user_id,
                    items=batch_items,
                    scan_task_id=payload.get("scan_task_id"),
                    idempotency_key=idempotency_key,
                )
                persist_task_count += len(batch_items)
                logger.info(
                    f"✅ 元数据任务 {task_id} 已创建第 {batch_number} 批（最后一批）持久化任务："
                    f"批次大小={len(batch_items)}, 累计持久化={persist_task_count}"
                )
            except Exception:
                logger.error(
                    f"❌ 元数据任务 {task_id} 创建第 {batch_number} 批（最后一批）持久化任务失败",
                    exc_info=True
                )

        if valid_result_count > 0:
            final_status = TaskStatus.SUCCESS
            status_msg = f"部分成功（有效结果 {valid_result_count}/{len(file_ids)} 个，持久化任务 {persist_task_count} 个）"
        else:
            final_status = TaskStatus.FAILED
            status_msg = "全部失败（无有效元数据结果）"

        await store.update_status(
            task_id,
            final_status,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({
                "processed_file_count": len(file_ids),
                "valid_metadata_count": valid_result_count,
                "persist_task_count": persist_task_count,
                "status_msg": status_msg
            })
        )
        logger.info(f"🏁 元数据任务 {task_id} 完成：{status_msg}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 元数据任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"processed_file_count": len(payload.get("file_ids", [])), "error": error_msg})
        )
