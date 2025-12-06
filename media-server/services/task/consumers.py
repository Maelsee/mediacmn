from __future__ import annotations
from .broker import broker  # 导入全局统一 Broker

import json
from typing import Any, Dict
from dramatiq import actor  # 保持导入同步 actor，但支持异步函数
from core.config import get_settings
from .state_store import get_state_store, TaskStatus, TaskPriority

import logging
logger = logging.getLogger(__name__)

# --------------------------
# 工具函数（保持不变）
# --------------------------
def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat()

# --------------------------
# 1. 扫描任务（异步函数 + 原生同步 actor 装饰器）
# --------------------------
@actor(queue_name="scan")  # 依然用 @actor 装饰，支持异步函数
async def scan_worker(task_id: str, payload: Dict[str, Any]) -> None:  # 函数是 async def
    logger.info(f"✅ 消费者接收到扫描任务：task_id={task_id}，payload={payload}")
    store = get_state_store()

    try:
        # 直接 await 异步逻辑（无需事件循环）
        await store.update_status(task_id, TaskStatus.RUNNING)

        # 延迟导入异步扫描引擎
        from services.scan.unified_scan_engine import get_unified_scan_engine
        eng = await get_unified_scan_engine()

        # 异步进度回调
        async def _progress(scanned: int, media_found: int):
            try:
                await store.update_status(task_id, TaskStatus.RUNNING, updated_at=_now())
            except Exception as e:
                logger.error(f"任务 {task_id} 进度更新失败：{e}", exc_info=True)

        # 执行异步扫描（直接 await）
        storage_id = int(payload["storage_id"])
        scan_path = payload["scan_path"]
        res = await eng.scan_storage(
            storage_id=storage_id,
            scan_path=scan_path,
            progress_cb=_progress
        )
        logger.info(f"扫描任务 {task_id} 完成：新文件 {len(res.new_file_ids)} 个，已扫描文件 {res.total_files} 个")

        # 更新任务成功状态（带结果摘要）
        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({
                "new_file_count": len(res.new_file_ids),
                "total_files": res.total_files,
                "media_files": res.media_files
            })
        )

        # --------------------------
        # 任务链：创建后续任务（删除对齐 + 元数据提取）
        # --------------------------
        from .producer import create_delete_task, create_metadata_task

        # 1. 创建删除对齐任务（幂等性保障）
        try:
            idempotency_key = f"delete:{payload['user_id']}:{storage_id}:{scan_path}:{':'.join(res.encountered_media_paths[:2])}"
            await create_delete_task(
                user_id=payload["user_id"],
                storage_id=str(storage_id),
                scan_path=scan_path,
                encountered_media_paths=res.encountered_media_paths,
                priority=TaskPriority.NORMAL,
                idempotency_key=idempotency_key
            )
            logger.info(f"扫描任务 {task_id} 已创建删除任务：{idempotency_key}")
        except Exception as e:
            logger.error(f"扫描任务 {task_id} 创建删除任务失败：{e}", exc_info=True)

        # 2. 创建元数据提取任务（有新文件才创建）
        if res.new_file_ids:
            try:
                # 幂等键：取前10个文件ID拼接（避免过长）
                file_key = ":".join(res.new_file_ids[:10])
                idempotency_key = f"metadata:{payload['user_id']}:{file_key}"
                await create_metadata_task(
                    user_id=payload["user_id"],
                    file_ids=res.new_file_ids,
                    priority=TaskPriority.NORMAL,
                    idempotency_key=idempotency_key
                )
                logger.info(f"扫描任务 {task_id} 已创建元数据任务：{idempotency_key}（{len(res.new_file_ids)} 个文件）")
            except Exception as e:
                logger.error(f"扫描任务 {task_id} 创建元数据任务失败：{e}", exc_info=True)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 扫描任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        # 更新失败状态
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now()
        )

# --------------------------
# 2. 元数据提取任务（异步函数 + 原生同步 actor 装饰器）
# --------------------------
@actor(queue_name="metadata")
async def metadata_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到元数据任务：task_id={task_id}，file_ids={payload.get('file_ids', [])}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        # 导入异步元数据增强器
        from services.media.metadata_enricher import MetadataEnricher
        enricher = MetadataEnricher()

        # 批量处理文件元数据
        all_success = True
        file_ids = payload.get("file_ids", [])
        for fid in file_ids:
            try:
                success = await enricher.enrich_media_file(int(fid))
                all_success = all_success and success
                logger.debug(f"元数据任务 {task_id}：文件 {fid} 处理{'成功' if success else '失败'}")
            except Exception as e:
                all_success = False
                logger.error(f"元数据任务 {task_id}：处理文件 {fid} 失败：{e}", exc_info=True)

        # 任务链：创建本地化任务（所有文件处理成功才创建）
        if all_success and file_ids:
            try:
                from .producer import create_localize_task
                for fid in file_ids:
                    # 幂等键：文件ID唯一标识
                    idempotency_key = f"localize:{payload['user_id']}:{fid}"
                    await create_localize_task(
                        user_id=payload["user_id"],
                        file_id=fid,
                        storage_id=payload.get("storage_id", ""),
                        idempotency_key=idempotency_key
                    )
                logger.info(f"元数据任务 {task_id} 已创建本地化任务：{len(file_ids)} 个")
            except Exception as e:
                logger.error(f"元数据任务 {task_id} 创建本地化任务失败：{e}", exc_info=True)

        # 更新任务状态
        final_status = TaskStatus.SUCCESS if all_success else TaskStatus.FAILED
        await store.update_status(
            task_id,
            final_status,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"processed_file_count": len(file_ids), "all_success": all_success})
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 元数据任务 {task_id} 执行失败：{error_msg}", exc_info=True)
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now()
        )

# --------------------------
# 3. 持久化任务（异步函数 + 原生同步 actor 装饰器）
# --------------------------
@actor(queue_name="persist")
async def persist_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到持久化任务：task_id={task_id}，file_id={payload.get('file_id')}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        # 校验文件ID
        file_id = payload.get("file_id")
        if not file_id:
            raise ValueError("持久化任务缺少 file_id 参数")
        file_id_int = int(file_id)

        # 导入依赖（延迟导入）
        from services.media.metadata_persistence_service import MetadataPersistenceService
        from core.db import get_session as get_db_session
        from models.media_models import FileAsset

        # 数据库会话管理（同步代码兼容）
        svc = MetadataPersistenceService()
        with next(get_db_session()) as session:
            # 查询文件资产
            media_file = session.get(FileAsset, file_id_int)
            if not media_file:
                raise ValueError(f"文件 {file_id_int} 不存在")

            # 应用元数据并提交
            contract_payload = payload.get("contract_payload", {})
            svc.apply_metadata(session, media_file, contract_payload)
            session.commit()
            logger.info(f"持久化任务 {task_id}：文件 {file_id_int} 元数据已保存")

        # 更新成功状态
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

# --------------------------
# 4. 删除同步任务（异步函数 + 原生同步 actor 装饰器）
# --------------------------
@actor(queue_name="delete")
async def delete_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到删除任务：task_id={task_id}，storage_id={payload.get('storage_id')}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        # 导入删除服务
        from services.media.delete_sync_service import DeleteSyncService
        svc = DeleteSyncService()

        # 执行删除同步（同步代码直接调用，不影响异步 Actor）
        storage_id = int(payload["storage_id"])
        scan_path = payload["scan_path"]
        encountered_media_paths = payload.get("encountered_media_paths", [])
        
        res = svc.compute_missing(storage_id, scan_path, encountered_media_paths)
        missing_files = res.get("missing", [])
        if missing_files:
            svc.hard_delete_files(missing_files)
            logger.info(f"删除任务 {task_id}：已删除 {len(missing_files)} 个缺失文件")
        else:
            logger.info(f"删除任务 {task_id}：无缺失文件，无需删除")
        missing_file_ids = [str(file.id) for file in missing_files if hasattr(file, 'id')]
        # 更新成功状态
        await store.update_status(
            task_id,
            TaskStatus.SUCCESS,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"deleted_file_count": len(missing_files), "missing_file_ids": missing_file_ids})
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

# --------------------------
# 5. 本地化任务（异步函数 + 原生同步 actor 装饰器）
# --------------------------
@actor(queue_name="localize")
async def localize_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到本地化任务：task_id={task_id}，file_id={payload.get('file_id')}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        # 校验参数
        file_id = payload.get("file_id")
        storage_id = payload.get("storage_id")
        if not file_id or not storage_id:
            raise ValueError("本地化任务缺少 file_id 或 storage_id 参数")

        # 导入本地化处理器
        from services.media.sidecar_localize_processor import SidecarLocalizeProcessor
        proc = SidecarLocalizeProcessor()

        # 执行异步本地化处理
        await proc.process(int(file_id), storage_id=int(storage_id))
        logger.info(f"本地化任务 {task_id}：文件 {file_id} 处理完成")

        # 更新成功状态
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