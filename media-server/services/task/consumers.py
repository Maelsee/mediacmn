from __future__ import annotations
from .broker import broker  # 导入全局统一 Broker

import json
from typing import Any, Dict, List
from dramatiq import actor  # 保持导入同步 actor，但支持异步函数
from core.config import get_settings
from .state_store import get_state_store, TaskStatus, TaskPriority
from core.logging import init_logging

import logging
init_logging(get_settings())
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
        user_id=payload.get("user_id")
        storage_id=payload.get("storage_id")
        scan_path=payload.get("scan_path")
        logger.info(f"📂 开始扫描：用户 {user_id}，存储 {storage_id}，路径 '{scan_path}'")

        res = await eng.scan_storage(
            user_id=user_id,
            storage_id=storage_id,
            scan_path=scan_path,
            progress_cb=_progress
        )
        # logger.info(f"扫描结果：{res}")
        logger.info(f"扫描任务 {task_id} 完成：新文件 {len(res.new_file_ids)} 个，已扫描文件 {res.total_files} 个，需要删除文件 {len(res.to_delete_ids)} 个")

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
        if res.to_delete_ids:
            try:
                file_key = ":".join(map(str, res.to_delete_ids if len(res.to_delete_ids) <=5 else res.to_delete_ids[:5]))
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

        # 2. 创建元数据提取任务（有新文件才创建）
        logger.debug(f"扫描任务 {task_id} 准备创建元数据任务：新文件数 {len(res.new_file_ids)}")
        if res.new_file_ids:
            try:
                # 幂等键：取前10个文件ID拼接（避免过长）
                file_key = ":".join(map(str, res.new_file_ids[:] if len(res.new_file_ids) <=10 else res.new_file_ids[:10]))
                idempotency_key = f"metadata:{user_id}:{storage_id}:{file_key}"
                await create_metadata_task(
                    user_id=user_id,
                    file_ids=res.new_file_ids,
                    storage_id=storage_id,
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


@actor(queue_name="metadata")
async def metadata_worker(task_id: str, payload: Dict[str, Any]) -> None:
    logger.info(f"✅ 消费者接收到元数据任务：task_id={task_id}，file_ids={payload.get('file_ids', [])}")
    store = get_state_store()

    try:
        await store.update_status(task_id, TaskStatus.RUNNING)

        # 1. 导入全局元数据增强器实例（避免重复初始化）
        from services.media.metadata_enricher import metadata_enricher
        # 导入持久化任务创建函数
        from .producer import create_persist_task, create_localize_task

        from services.scraper.manager import scraper_manager  # 确保导入路径正确
        # 检查刮削插件系统是否运行
        if not scraper_manager.is_running:
            logger.warning("插件系统未在项目启动时初始化，尝试执行补救启动...")
            # 补救措施：如果确实没启动，这里才调用 startup
            await scraper_manager.startup()
            



        # 2. 解析任务参数
        user_id = payload.get("user_id")
        file_ids = payload.get("file_ids", [])
        storage_id = payload.get("storage_id")  # 透传给本地化任务
        if not user_id or not file_ids:
            raise ValueError(f"元数据任务缺少必要参数：user_id={user_id}, file_ids={file_ids}")

        # 3. 批量处理元数据（调用修改后的批量方法，返回 List[Dict]，消除数据类转换开销）
        logger.info(f"📦 开始批量处理元数据：共 {len(file_ids)} 个文件")
        metadata_results = await metadata_enricher.enrich_multiple_files(
            file_ids=file_ids,
            user_id=user_id,
            max_concurrency=20   # 控制并发量，避免过载,可作为环境调整 
        )
        logger.debug(f"📦 批量元数据处理完成：{len(metadata_results)} 个结果")

        # 4. 处理批量结果：为有效结果创建持久化任务
        persist_task_count = 0  # 统计成功创建的持久化任务数
        valid_result_count = 0  # 统计有效元数据结果数
        for result in metadata_results:
            # 跳过无效结果（无 contract_payload 或 file_id 不匹配）
            if not result.get("success") or not result.get("contract_payload") or result.get("file_id") not in file_ids:
                logger.warning(f"⚠️ 跳过无效元数据结果：file_id={result.get('file_id')}, contract_payload={bool(result.get('contract_payload'))}")
                continue

            valid_result_count += 1
            try:
                # 4.1 生成幂等键（确保同一文件+同一元数据类型不重复处理）
                idempotency_key = f"persist:{user_id}:{result.get('file_id')}:{result.get('contract_type')}"
                # logger.info(f"📄 文件 {result.get('file_id')} 的contract_payload={result.get('contract_payload')}")
                # 4.2 调用生产者创建持久化任务（参数格式对齐 PersistPayload）
                await create_persist_task(
                    user_id=user_id,
                    file_id=result.get("file_id"),
                    contract_type=result.get("contract_type"),
                    contract_payload=result.get("contract_payload"),
                    path_info=result.get("path_info"),
                    idempotency_key=idempotency_key  # 幂等性保障
                )
                persist_task_count += 1
                logger.debug(f"✅ 为文件 {result.get('file_id')} 创建持久化任务：幂等键={idempotency_key}")
            except Exception as e:
                logger.error(f"❌ 为文件 {result.get('file_id')} 创建持久化任务失败：{e}", exc_info=True)

        # 5. 任务链：创建本地化任务（有有效结果才创建，避免空任务）
        settings = get_settings()
        if valid_result_count > 0 and bool(getattr(settings, "SIDE_CAR_LOCALIZATION_ENABLED", True)) and storage_id is not None:
              
            localize_task_count = 0
            for result in metadata_results:
                if not result.get("contract_payload"):
                    continue
                try:
                    # 生成本地化任务幂等键（文件唯一）
                    idempotency_key = f"localize:{user_id}:{result.get('file_id')}"
                    await create_localize_task(
                        user_id=user_id,
                        file_id=result.get("file_id"),
                        storage_id=storage_id,
                        idempotency_key=idempotency_key
                    )
                    localize_task_count += 1
                except Exception as e:
                    logger.error(f"❌ 为文件 {result.get('file_id')} 创建本地化任务失败：{e}", exc_info=True)
            logger.info(f"📌 元数据任务 {task_id} 已创建本地化任务：{localize_task_count}/{valid_result_count} 个")

        # 6. 更新任务最终状态（基于有效结果数判断，而非全量成功）
        if valid_result_count > 0:
            final_status = TaskStatus.SUCCESS
            status_msg = f"部分成功（有效结果 {valid_result_count}/{len(file_ids)} 个，持久化任务 {persist_task_count} 个）"
        else:
            final_status = TaskStatus.FAILED
            status_msg = f"全部失败（无有效元数据结果）"

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
        # 更新失败状态（记录错误信息）
        await store.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg,
            finished_at=_now(),
            updated_at=_now(),
            result=json.dumps({"processed_file_count": len(payload.get("file_ids", [])), "error": error_msg})
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
        # file_id = int(file_id)

        # 导入依赖（延迟导入）
        from services.media.metadata_persistence_service import MetadataPersistenceService
        from core.db import get_session as get_db_session
        from models.media_models import FileAsset

        # 数据库会话管理（同步代码兼容）
        svc = MetadataPersistenceService()
        with next(get_db_session()) as session:
            # 查询文件资产
            media_file = session.get(FileAsset, file_id)
            if not media_file:
                raise ValueError(f"文件 {file_id} 不存在")

            # 应用元数据并提交
            contract_type = payload.get("contract_type", "unknown")
            # logger.info(f"📄 持久化文件 {file_id} 元数据：类型={contract_type}")
            contract_payload = payload.get("contract_payload", {})
            # logger.info(f"📄 持久化文件 {file_id} 元数据：{contract_payload}")
            path_info = payload.get("path_info", {})
            # logger.info(f"📄 持久化文件 {file_id} 元数据：{path_info}")
            
            success = svc.apply_metadata(session, media_file, metadata=contract_payload, metadata_type=contract_type,path_info=path_info)
            session.commit()
            logger.info(f"持久化任务 {task_id}：文件 {file_id} 元数据已保存")

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
        from services.scan.file_asset_repository import get_file_asset_repo
        repo = await get_file_asset_repo()
        
        to_delete_ids = payload.get("to_delete_ids", [])
        user_id = payload.get("user_id")
        cleanup_stats = await repo.delete_files_by_ids(to_delete_ids, user_id)
        logger.info(f"清理完成，删除文件数: {cleanup_stats.get('deleted_assets', 0)}，清理孤立核心数: {cleanup_stats.get('cleaned_cores', 0)}")

        # 更新成功状态
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
