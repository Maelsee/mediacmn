from __future__ import annotations
from .broker import broker  # 全局统一 Broker（已注册）

import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel
from .state_store import TaskRecord, TaskStatus, get_state_store, TaskPriority
from .custom_encoder import DramatiqCustomEncoder  # 导入自定义编码器
import json

import logging
logger = logging.getLogger(__name__)

# --------------------------
# 任务 Payload 模型（保持不变）
# --------------------------
class ScanPayload(BaseModel):
    user_id: int
    storage_id: int
    scan_path: str

class MetadataPayload(BaseModel):
    user_id: int
    file_ids: List[int]
    storage_id: Optional[int] = None
    scan_task_id: Optional[str] = None

class PersistPayload(BaseModel):
    user_id: int
    file_id: int
    contract_type: str
    contract_payload: Dict
    path_info: Dict


class PersistBatchItemPayload(BaseModel):
    file_id: int
    contract_type: str
    contract_payload: Dict
    path_info: Dict


class PersistBatchPayload(BaseModel):
    user_id: int
    items: List[PersistBatchItemPayload]
    scan_task_id: Optional[str] = None


class DeletePayload(BaseModel):
    user_id: int
    to_delete_ids: List[int]
class LocalizePayload(BaseModel):
    user_id: int
    file_id: int
    storage_id: int

# --------------------------
# 工具函数（保持不变）
# --------------------------
def _new_task_id() -> str:
    try:
        import ulid
        return str(ulid.new())
    except Exception:
        return uuid.uuid4().hex

def _now_iso() -> str:
    import datetime
    return datetime.datetime.now().isoformat()

# --------------------------
# 核心：精简后的 _enqueue 方法（统一任务创建逻辑）
# --------------------------
async def _enqueue(
    queue: str,
    task_type: str,
    payload: Dict,
    *,
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 3,
    time_limit_ms: Optional[int] = None
) -> str:
    store = get_state_store()
    idem_key = payload.get("idempotency_key")

    # 1. 幂等性检查：存在则直接返回已有任务 ID
    if idem_key:
        existing_task_id = await store.get_task_id_by_idempotency(idem_key)
        if existing_task_id:
            logger.info(f"幂等键 {idem_key} 已存在，返回已有任务 ID：{existing_task_id}")
            return existing_task_id

    # -------------------------- 关键修改：手动序列化 payload --------------------------
    # 使用自定义编码器将 payload 转换为 JSON 字符串（处理 ArtworkType 枚举）
    serialized_payload_str = json.dumps(payload, cls=DramatiqCustomEncoder)
    # 将 JSON 字符串转回 dict（确保传递给 Dramatiq 的是基础类型，无 Enum）
    serialized_payload = json.loads(serialized_payload_str)
    # ----------------------------------------------------------------------------------


    # 2. 生成任务 ID 并初始化状态
    task_id = _new_task_id()
    task_record = TaskRecord(
        task_id=task_id,
        task_type=task_type,
        queue=queue,
        status=TaskStatus.PENDING,
        payload=serialized_payload,
        max_retries=max_retries,
        time_limit_ms=time_limit_ms,
        created_at=_now_iso(),
    )
    await store.create_task(task_record)
    logger.debug(f"初始化任务状态：task_id={task_id}, queue={queue}, payload={payload}")

    try:
        # 3. 延迟导入 Actor（避免循环导入），映射队列与 Actor
        from .consumers import (
            scan_worker,
            metadata_worker,
            persist_worker,
            persist_batch_worker,
            delete_worker,
            localize_worker,
        )
        actor_mapping = {
            "scan": scan_worker,
            "metadata": metadata_worker,
            "persist": persist_worker,
            "persist_batch": persist_batch_worker,
            "delete": delete_worker,
            "localize": localize_worker,
        }
        target_actor = actor_mapping.get(queue)
        if not target_actor:
            raise ValueError(f"队列 {queue} 对应的 Actor 不存在")

        # 4. 发送任务（依赖全局统一 Broker，无需手动绑定）
        # logger.info(f"发送任务 {task_id} 到队列 {queue}，Actor：{target_actor.actor_name}")
        # target_actor.send(task_id, payload)

        
        # 4. 发送任务：使用手动序列化后的 payload（无 Enum 类型，可正常序列化）
        logger.info(f"发送任务 {task_id} 到队列 {queue}，Actor：{target_actor.actor_name}")
        target_actor.send(task_id, serialized_payload)  # 传递序列化后的 payload


        # 5. 幂等键持久化（若有）
        if idem_key:
            await store.set_idempotency(idem_key, task_id, ttl_seconds=60)
            logger.debug(f"任务 {task_id} 绑定幂等键：{idem_key}")

        return task_id

    except Exception as e:
        # 6. 异常处理：标记为死信队列，记录错误
        error_msg = str(e)
        logger.error(f"任务 {task_id} 入队失败：{error_msg}", exc_info=True)
        try:
            await store.update_status(
                task_id,
                TaskStatus.DEADLETTER,
                error_code="enqueue_failed",
                error_message=error_msg
            )
        except Exception:
            logger.error(f"任务 {task_id} 死信状态更新失败", exc_info=True)
        return task_id

# --------------------------
# 任务创建函数（统一调用 _enqueue，彻底精简）
# --------------------------
async def create_scan_task(
    user_id: int,
    storage_id: int,
    scan_path: str,
    *,
    priority: TaskPriority = TaskPriority.NORMAL,
    idempotency_key: Optional[str] = None
) -> str:
    payload = ScanPayload(
        user_id=user_id,
        storage_id=storage_id,
        scan_path=scan_path
    ).model_dump()
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    logger.info(f"创建扫描任务：user_id={user_id}, storage_id={storage_id}, scan_path={scan_path}")
    return await _enqueue("scan", "scan", payload, priority=priority)

async def create_metadata_task(
    user_id: int,
    file_ids: List[int],
    storage_id: Optional[int] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    idempotency_key: Optional[str] = None,
    scan_task_id: Optional[str] = None,
) -> str:
    payload = MetadataPayload(
        user_id=user_id,
        file_ids=file_ids,
        storage_id=storage_id,
        scan_task_id=scan_task_id,
    ).model_dump()
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    logger.info(f"创建元数据任务：user_id={user_id}, file_ids={file_ids}")
    return await _enqueue("metadata", "metadata", payload, priority=priority)

async def create_persist_task(
    user_id: int,
    file_id: int,
    contract_type: str,
    contract_payload: Dict,
    path_info: Dict,
    *,
    priority: TaskPriority = TaskPriority.NORMAL,
    idempotency_key: Optional[str] = None
) -> str:
    payload = PersistPayload(
        user_id=user_id,
        file_id=file_id,
        contract_type=contract_type,
        contract_payload=contract_payload,
        path_info=path_info
    ).model_dump()
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return await _enqueue("persist", "persist", payload, priority=priority)


async def create_persist_batch_task(
    user_id: int,
    items: List[Dict],
    *,
    priority: TaskPriority = TaskPriority.NORMAL,
    idempotency_key: Optional[str] = None,
    scan_task_id: Optional[str] = None,
) -> str:
    payload = PersistBatchPayload(
        user_id=user_id,
        items=items,
        scan_task_id=scan_task_id,
    ).model_dump()
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return await _enqueue("persist_batch", "persist_batch", payload, priority=priority)

async def create_delete_task(
    user_id: int,
    to_delete_ids: List[int],
    priority: TaskPriority = TaskPriority.NORMAL,
    idempotency_key: Optional[str] = None
) -> str:
    payload = DeletePayload(
        user_id=user_id,
        to_delete_ids=to_delete_ids
    ).model_dump()
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return await _enqueue("delete", "delete", payload, priority=priority)

async def create_localize_task(
    user_id: int,
    file_id: int,
    storage_id: int,
    *,
    priority: TaskPriority = TaskPriority.NORMAL,
    idempotency_key: Optional[str] = None
) -> str:
    payload = LocalizePayload(
        user_id=user_id,
        file_id=file_id,
        storage_id=storage_id
    ).model_dump()
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return await _enqueue("localize", "localize", payload, priority=priority)
