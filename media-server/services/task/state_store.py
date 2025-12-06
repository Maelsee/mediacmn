from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional
from enum import Enum

import redis.asyncio as redis
from pydantic import BaseModel, Field

from core.config import get_settings

class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 10      # 低优先级
    NORMAL = 50   # 普通优先级
    HIGH = 90     # 高优先级
    URGENT = 100  # 紧急优先级

class TaskStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEADLETTER = "deadletter"


class TaskRecord(BaseModel):
    task_id: str
    task_type: str
    queue: str
    status: str = Field(default=TaskStatus.PENDING)
    payload: Dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    max_retries: int = 3
    time_limit_ms: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class StateStore:
    def __init__(self, redis_url: Optional[str] = None, db: Optional[int] = None):
        s = get_settings()
        self._redis = redis.from_url(redis_url or s.REDIS_URL, db=s.REDIS_DB if db is None else db, decode_responses=True)

    def _task_key(self, task_id: str) -> str:
        return f"task:{task_id}"

    def _status_set(self, status: str) -> str:
        return f"tasks:by_status:{status}"

    def _type_set(self, task_type: str) -> str:
        return f"tasks:by_type:{task_type}"

    def _timeline(self) -> str:
        return "tasks:timeline"

    def _idemp_key(self, k: str) -> str:
        return f"tasks:idemp:{k}"

    async def create_task(self, rec: TaskRecord, ttl_success_seconds: Optional[int] = None) -> None:
        key = self._task_key(rec.task_id)
        mapping = {
            "task_id": rec.task_id,
            "task_type": rec.task_type,
            "queue": rec.queue,
            "status": rec.status,
            "payload": json.dumps(rec.payload, ensure_ascii=False),
            "attempts": str(rec.attempts),
            "max_retries": str(rec.max_retries),
            "time_limit_ms": str(rec.time_limit_ms or ""),
            "created_at": rec.created_at,
            "updated_at": rec.updated_at or "",
            "started_at": rec.started_at or "",
            "finished_at": rec.finished_at or "",
            "error_code": rec.error_code or "",
            "error_message": rec.error_message or "",
        }
        _mem_store()[key] = mapping
        try:
            await self._redis.hset(key, mapping=mapping)
            await self._redis.sadd(self._status_set(rec.status), rec.task_id)
            await self._redis.sadd(self._type_set(rec.task_type), rec.task_id)
            await self._redis.zadd(self._timeline(), {rec.task_id: time.time()})
            if ttl_success_seconds:
                await self._redis.expire(key, ttl_success_seconds)
        except Exception:
            _mem_store()[key] = mapping

    async def update_status(self, task_id: str, status: str, **fields: Any) -> None:
        key = self._task_key(task_id)
        now = fields.get("updated_at") or fields.get("finished_at") or fields.get("started_at")
        mapping = {"status": status}
        for k, v in fields.items():
            mapping[k] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)
        if not now:
            mapping["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            prev = await self._redis.hget(key, "status")
            if prev:
                await self._redis.srem(self._status_set(prev), task_id)
            await self._redis.hset(key, mapping=mapping)
            await self._redis.sadd(self._status_set(status), task_id)
            await self._redis.zadd(self._timeline(), {task_id: time.time()})
        except Exception:
            data = _mem_store().get(key) or {"task_id": task_id}
            data.update(mapping)
            _mem_store()[key] = data

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        key = self._task_key(task_id)
        try:
            data = await self._redis.hgetall(key)
            if not data:
                data = _mem_store().get(key)
        except Exception:
            data = _mem_store().get(key)
        if not data:
            return None
        if data.get("payload"):
            try:
                data["payload"] = json.loads(data["payload"])
            except Exception:
                pass
        return data

    async def list_tasks(self, status: Optional[str] = None, task_type: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        ids: Optional[list] = None
        try:
            if status and task_type:
                ids = await self._redis.sinter(self._status_set(status), self._type_set(task_type))
            elif status:
                ids = await self._redis.smembers(self._status_set(status))
            elif task_type:
                ids = await self._redis.smembers(self._type_set(task_type))
            else:
                ids = await self._redis.zrevrange(self._timeline(), 0, max(0, limit - 1))
        except Exception:
            ids = None
        items: list = []
        if ids:
            try:
                pipe = self._redis.pipeline()
                for tid in list(ids)[:limit]:
                    pipe.hgetall(self._task_key(tid))
                rows = await pipe.execute()
            except Exception:
                rows = []
            for row in rows or []:
                if not row:
                    continue
                if row.get("payload"):
                    try:
                        row["payload"] = json.loads(row["payload"])
                    except Exception:
                        pass
                items.append(row)
        if not items:
            mem = _mem_store()
            for k, v in mem.items():
                if not k.startswith("task:"):
                    continue
                if status and v.get("status") != status:
                    continue
                if task_type and v.get("task_type") != task_type:
                    continue
                if v.get("payload") and isinstance(v.get("payload"), str):
                    try:
                        v["payload"] = json.loads(v["payload"])
                    except Exception:
                        pass
                items.append(v)
            items = items[:limit]
        return {"items": items, "count": len(items)}

    async def get_task_id_by_idempotency(self, idem_key: str) -> Optional[str]:
        try:
            v = await self._redis.get(self._idemp_key(idem_key))
        except Exception:
            v = _mem_idemp().get(idem_key)
        return v

    async def set_idempotency(self, idem_key: str, task_id: str, ttl_seconds: int = 43200) -> None:
        try:
            await self._redis.set(self._idemp_key(idem_key), task_id, ex=ttl_seconds, nx=True)
        except Exception:
            mem = _mem_idemp()
            if idem_key not in mem:
                mem[idem_key] = task_id


_store: Optional[StateStore] = None
_MEM: Dict[str, Dict[str, Any]] = {}
_MEM_IDEMP: Dict[str, str] = {}


def get_state_store() -> StateStore:
    global _store
    if _store is None:
        _store = StateStore()
    return _store


def _mem_store() -> Dict[str, Dict[str, Any]]:
    return _MEM


def _mem_idemp() -> Dict[str, str]:
    return _MEM_IDEMP
