from __future__ import annotations

import asyncio
import json
import uuid
import time
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries, TimeLimit
import redis

# --------------------------
# 1. 基础配置（Redis 连接 + 全局初始化）
# --------------------------
REDIS_URL = "redis://:redis123@localhost:9001/0"  # 你的 Redis 配置
app = FastAPI(title="Scan 任务队列 Demo")

# 初始化 Redis Broker（任务队列）
broker = RedisBroker(
    url=REDIS_URL,
    middleware=[Retries(max_retries=2), TimeLimit(time_limit=60000)]  # 1分钟超时
)
dramatiq.set_broker(broker)

# 初始化 Redis 客户端（存储任务状态）
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# --------------------------
# 2. 任务状态和模型定义
# --------------------------
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class TaskPriority(int, Enum):
    NORMAL = 50

class ScanPayload(BaseModel):
    user_id: str
    storage_id: str
    scan_path: str

class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    payload: Dict
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None

# --------------------------
# 3. 任务状态存储（Redis 实现）
# --------------------------
TASK_PREFIX = "scan_task:"

def _new_task_id() -> str:
    return str(uuid.uuid4())

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

async def init_task(task_id: str, payload: Dict) -> None:
    """初始化任务状态到 Redis"""
    mapping = {
        "task_id": task_id,
        "status": TaskStatus.PENDING.value,
        "payload": json.dumps(payload),
        "created_at": _now_iso(),
        "started_at": "",
        "finished_at": "",
        "error": ""
    }
    redis_client.hset(f"{TASK_PREFIX}{task_id}", mapping=mapping)

async def update_task_status(task_id: str, status: TaskStatus, **kwargs) -> None:
    """更新任务状态"""
    key = f"{TASK_PREFIX}{task_id}"
    mapping = {"status": status.value}
    mapping.update(kwargs)
    if "started_at" not in mapping and status == TaskStatus.RUNNING:
        mapping["started_at"] = _now_iso()
    if "finished_at" not in mapping and status in [TaskStatus.SUCCESS, TaskStatus.FAILED]:
        mapping["finished_at"] = _now_iso()
    redis_client.hset(key, mapping=mapping)

async def get_task(task_id: str) -> Optional[Dict]:
    """获取任务状态"""
    key = f"{TASK_PREFIX}{task_id}"
    data = redis_client.hgetall(key)
    if not data:
        return None
    # 解析 payload
    if data["payload"]:
        data["payload"] = json.loads(data["payload"])
    # 处理空字符串为 None
    for k, v in data.items():
        if v == "":
            data[k] = None
    return data

# --------------------------
# 4. Dramatiq 消费者（Scan 任务执行）
# --------------------------
@dramatiq.actor(queue_name="scan", broker=broker)
def scan_worker(task_id: str, payload: Dict) -> None:
    """Scan 任务执行逻辑（修复事件循环问题）"""
    print(f"\n✅ 接收到扫描任务：task_id={task_id}, payload={payload}")
    
    # 关键修复：强制创建并绑定事件循环到当前线程
    try:
        # 尝试获取当前线程的事件循环
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # 没有则创建新循环，并绑定到当前线程
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        # 更新状态为运行中（现在循环已存在，不会报错）
        loop.run_until_complete(update_task_status(task_id, TaskStatus.RUNNING))
        print(f"📌 任务 {task_id} 开始执行：扫描路径 {payload['scan_path']}")

        # 模拟扫描逻辑（5秒耗时）
        time.sleep(5)  # 替换为你的真实扫描逻辑（如 eng.scan_storage）
        print(f"✅ 任务 {task_id} 执行成功：模拟扫描完成")

        # 更新状态为成功
        loop.run_until_complete(update_task_status(task_id, TaskStatus.SUCCESS))

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 任务 {task_id} 执行失败：{error_msg}")
        # 更新状态为失败
        loop.run_until_complete(
            update_task_status(task_id, TaskStatus.FAILED, error=error_msg)
        )
        raise  # 触发重试（可选）
# --------------------------
# 5. FastAPI 生产者（创建 Scan 任务）
# --------------------------
@app.post("/tasks/scan", response_model=TaskResponse, summary="创建扫描任务")
async def create_scan_task(payload: ScanPayload):
    """创建并提交扫描任务"""
    task_id = _new_task_id()
    payload_dict = payload.model_dump()

    # 初始化任务状态
    await init_task(task_id, payload_dict)

    # 提交任务到队列
    scan_worker.send(task_id, payload_dict)
    print(f"📤 扫描任务已提交：task_id={task_id}, payload={payload_dict}")

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        created_at=_now_iso()
    )

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task_status(task_id: str):
    """查询指定任务的执行状态"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return TaskStatusResponse(
        task_id=task["task_id"],
        status=TaskStatus(task["status"]),
        payload=task["payload"],
        created_at=task["created_at"],
        started_at=task["started_at"],
        finished_at=task["finished_at"],
        error=task["error"]
    )

# --------------------------
# 6. 运行入口
# --------------------------
if __name__ == "__main__":
    import uvicorn
    # 启动 FastAPI 服务（生产者）
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)