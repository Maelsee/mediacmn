from __future__ import annotations

from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries, TimeLimit
import redis  # 新增：用于操作 Redis 存储任务状态

# --------------------------
# 1. 基础配置（Redis 连接复用）
# --------------------------
REDIS_URL = "redis://:redis123@localhost:9001/0"

# 初始化 Redis Broker（任务队列）
redis_broker = RedisBroker(url=REDIS_URL)
dramatiq.set_broker(redis_broker)

# 初始化 Redis 客户端（存储任务状态，复用 Broker 连接池）
redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True  # 自动解码 bytes 为字符串，方便操作
)

# FastAPI 应用初始化
app = FastAPI(title="Dramatiq + FastAPI 任务队列")

# --------------------------
# 2. 任务状态管理（Redis 实现，跨进程共享）
# --------------------------
class TaskStatus(str, Enum):
    PENDING = "pending"  # 任务已提交
    RUNNING = "running"  # 任务执行中
    SUCCESS = "success"  # 任务成功
    FAILED = "failed"    # 任务失败

# Redis Key 前缀（避免和其他业务冲突）
TASK_REDIS_PREFIX = "task:"

def init_task_status(task_id: str, message: str) -> None:
    """初始化任务状态到 Redis"""
    created_at = datetime.utcnow().isoformat() + "Z"
    # 用 Redis Hash 存储任务状态（key: task:{task_id}）
    redis_client.hset(
        f"{TASK_REDIS_PREFIX}{task_id}",
        mapping={
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
            "message": message,  # 存储原始消息（可选）
            "created_at": created_at,
            "started_at": "",
            "finished_at": "",
            "result": "",
            "error": ""
        }
    )

def get_task_status(task_id: str) -> Optional[Dict[str, str]]:
    """从 Redis 获取任务状态"""
    task_key = f"{TASK_REDIS_PREFIX}{task_id}"
    # 检查任务是否存在
    if not redis_client.exists(task_key):
        return None
    # 获取 Hash 所有字段
    task_data = redis_client.hgetall(task_key)
    # 处理空字符串为 None（更符合 Pydantic 模型）
    return {
        k: v if v != "" else None
        for k, v in task_data.items()
    }

def update_task_status(task_id: str, **kwargs) -> None:
    """更新 Redis 中的任务状态（支持部分字段更新）"""
    task_key = f"{TASK_REDIS_PREFIX}{task_id}"
    if not redis_client.exists(task_key):
        raise KeyError(f"Task {task_id} not found")
    # 只更新传入的字段（如 status、started_at 等）
    redis_client.hset(task_key, mapping=kwargs)

def get_all_tasks() -> List[Dict[str, str]]:
    """获取所有任务状态（简化版）"""
    # 匹配所有任务 Key
    task_keys = redis_client.keys(f"{TASK_REDIS_PREFIX}*")
    tasks = []
    for key in task_keys:
        task_data = redis_client.hgetall(key)
        tasks.append({
            k: v if v != "" else None
            for k, v in task_data.items()
        })
    return tasks

# --------------------------
# 3. 任务模型（Pydantic 验证）
# --------------------------
class TaskRequest(BaseModel):
    """触发任务的请求参数"""
    message: str  # 示例参数：任务要处理的消息
    delay: Optional[int] = 0  # 延迟执行时间（秒）

class TaskResponse(BaseModel):
    """任务提交后的响应"""
    task_id: str
    status: TaskStatus
    created_at: str

class TaskStatusResponse(BaseModel):
    """查询任务状态的响应"""
    task_id: str
    status: TaskStatus
    message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None

# --------------------------
# 4. Dramatiq 任务定义（修改为 Redis 状态存储）
# --------------------------
@dramatiq.actor(
    queue_name="default",  # 队列名
    max_retries=2,         # 最大重试次数
    time_limit=30000,      # 任务超时时间（30秒，单位：毫秒）
)
def simple_task(task_id: str, message: str) -> Dict[str, str]:
    """
    同步任务示例：处理消息（使用 Redis 存储状态）
    :param task_id: 任务唯一ID
    :param message: 要处理的消息
    :return: 任务结果
    """
    try:
        # 更新任务状态为「运行中」
        update_task_status(
            task_id,
            status=TaskStatus.RUNNING.value,
            started_at=datetime.utcnow().isoformat() + "Z"
        )

        # 模拟任务执行（比如：数据处理、调用第三方接口等）
        import time
        time.sleep(5)  # 模拟耗时操作（5秒）
        
        # 任务结果（字典转字符串存储，Redis 不支持直接存字典）
        result = {
            "processed_message": f"✅ 处理完成：{message}",
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        result_str = str(result)  # 实际项目建议用 json.dumps()

        # 更新任务状态为「成功」
        update_task_status(
            task_id,
            status=TaskStatus.SUCCESS.value,
            finished_at=datetime.utcnow().isoformat() + "Z",
            result=result_str
        )
        return result
    except Exception as e:
        # 更新任务状态为「失败」
        error_msg = str(e)
        update_task_status(
            task_id,
            status=TaskStatus.FAILED.value,
            finished_at=datetime.utcnow().isoformat() + "Z",
            error=error_msg
        )
        raise  # 抛出异常，触发重试

# --------------------------
# 5. FastAPI 接口（修改为 Redis 状态查询）
# --------------------------
@app.post("/tasks", response_model=TaskResponse, summary="提交任务")
def create_task(request: TaskRequest):
    """提交一个简单任务到队列"""
    # 生成唯一任务ID（用 UUID）
    import uuid
    task_id = str(uuid.uuid4())
    
    # 初始化任务状态到 Redis（关键：跨进程共享）
    init_task_status(task_id, request.message)
    
    # 提交任务到队列（支持延迟执行）
    if request.delay > 0:
        simple_task.send_with_options(delay=request.delay * 1000, args=(task_id, request.message))
    else:
        simple_task.send(task_id, request.message)
    
    # 从 Redis 获取初始化后的状态（确保数据一致）
    task_data = get_task_status(task_id)
    return TaskResponse(
        task_id=task_id,
        status=TaskStatus(task_data["status"]),
        created_at=task_data["created_at"]
    )

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
def get_task(task_id: str):
    """根据任务ID查询状态和结果"""
    task_data = get_task_status(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    # 处理 result（字符串转字典）
    result = None
    if task_data["result"]:
        try:
            result = eval(task_data["result"])  # 实际项目建议用 json.loads()
        except Exception:
            result = {"error": "Failed to parse result"}
    
    return TaskStatusResponse(
        task_id=task_data["task_id"],
        status=TaskStatus(task_data["status"]),
        message=task_data["message"],
        created_at=task_data["created_at"],
        started_at=task_data["started_at"],
        finished_at=task_data["finished_at"],
        result=result,
        error=task_data["error"]
    )

@app.get("/tasks", response_model=List[TaskStatusResponse], summary="查询所有任务")
def list_tasks():
    """查询所有任务的状态"""
    tasks = get_all_tasks()
    # 处理每个任务的 result 字段
    for task in tasks:
        if task["result"]:
            try:
                task["result"] = eval(task["result"])
            except Exception:
                task["result"] = {"error": "Failed to parse result"}
    return [TaskStatusResponse(**task) for task in tasks]

# --------------------------
# 6. 运行入口
# --------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tests.main:app", host="0.0.0.0", port=8000, reload=True)