"""
任务队列服务 - 基于Redis的分布式任务队列系统

功能特点：
- 支持多种任务类型（扫描、转码、元数据获取等）
- 任务优先级管理
- 任务状态实时跟踪
- 失败任务重试机制
- 分布式任务处理
- 任务结果缓存
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, asdict

import redis.asyncio as redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"          # 待处理
    RUNNING = "running"          # 运行中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消
    RETRYING = "retrying"        # 重试中


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 10      # 低优先级
    NORMAL = 50   # 普通优先级
    HIGH = 90     # 高优先级
    URGENT = 100  # 紧急优先级


class TaskType(str, Enum):
    """任务类型"""
    SCAN = "scan"                    # 存储扫描
    METADATA_FETCH = "metadata_fetch" # 元数据获取
    COMBINED_SCAN = "combined_scan"   # 扫描+元数据组合任务
    TRANSCODE = "transcode"         # 转码处理
    THUMBNAIL = "thumbnail"         # 缩略图生成
    INDEX = "index"                 # 索引重建
    CLEANUP = "cleanup"             # 清理任务
    DELETE_SYNC = "delete_sync"     # 删除对齐任务
    SIDECAR_LOCALIZE = "sidecar_localize"     # 侧车文件本地化
    PERSIST_METADATA = "persist_metadata"     # 持久化元数据


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    duration: Optional[float] = None


class Task(BaseModel):
    """任务模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    
    # 任务参数
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # 执行信息
    worker_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 重试信息
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: int = 60  # 重试延迟（秒）
    
    # 结果信息
    result: Optional[TaskResult] = None
    
    # 超时设置
    timeout: int = 3600  # 任务超时时间（秒）
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TaskQueueService:
    """任务队列服务"""
    
    def __init__(self, redis_url: Optional[str] = None, db: Optional[int] = None):
        # 允许为空，自动从项目配置填充
        if redis_url is None or db is None:
            from core.config import get_settings
            settings = get_settings()
            redis_url = redis_url or settings.REDIS_URL
            db = settings.REDIS_DB if db is None else db
        self.redis_url = redis_url
        self.db = db
        self.redis_client: Optional[redis.Redis] = None
        self.is_connected = False
        
        # 队列键名前缀
        self.queue_prefix = "task_queue"
        self.task_prefix = "task"
        self.result_prefix = "task_result"
        self.worker_prefix = "worker"
        
    async def connect(self) -> bool:
        """连接Redis"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # 测试连接
            await self.redis_client.ping()
            self.is_connected = True
            logger.debug("任务队列服务连接到Redis")
            return True
            
        except Exception as e:
            logger.error(f"连接Redis失败: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """断开Redis连接"""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False
            logger.debug("任务队列服务断开Redis连接")
    
    def _get_queue_key(self, task_type: TaskType, priority: TaskPriority) -> str:
        """获取队列键名"""
        return f"{self.queue_prefix}:{task_type.value}:{priority.value}"
    
    def _get_task_key(self, task_id: str) -> str:
        """获取任务键名"""
        return f"{self.task_prefix}:{task_id}"
    
    def _get_result_key(self, task_id: str) -> str:
        """获取结果键名"""
        return f"{self.result_prefix}:{task_id}"
    
    def _get_worker_key(self, worker_id: str) -> str:
        """获取工作者键名"""
        return f"{self.worker_prefix}:{worker_id}"
    
    async def enqueue_task(self, task: Task) -> bool:
        """将任务加入队列"""
        try:
            if not self.is_connected:
                logger.error("Redis未连接")
                # 尝试立即连接一次
                await self.connect()
                if not self.is_connected:
                    return False
            
            # 保存任务信息
            task_key = self._get_task_key(task.id)
            task_data = task.model_dump_json()
            await self.redis_client.setex(task_key, 86400, task_data)  # 保存24小时
            
            # 将任务加入优先级队列
            queue_key = self._get_queue_key(task.task_type, task.priority)
            score = task.priority.value
            
            # 使用有序集合实现优先级队列
            await self.redis_client.zadd(queue_key, {task.id: score})
            
            logger.debug(f"任务加入队列: {task.id} (类型: {task.task_type.value}, 优先级: {task.priority.value})")
            return True
            
        except Exception as e:
            logger.error(f"任务入队失败: {e}")
            return False
    
    async def dequeue_task(self, task_types: List[TaskType], 
                          worker_id: str,
                          timeout: int = 30) -> Optional[Task]:
        """从队列中获取任务"""
        try:
            if not self.is_connected:
                logger.error("Redis未连接")
                await self.connect()
                if not self.is_connected:
                    return None
            
            start_time = datetime.now()
            
            while (datetime.now() - start_time).total_seconds() < timeout:
                # 按优先级顺序检查各个队列
                for task_type in task_types:
                    for priority in [TaskPriority.URGENT, TaskPriority.HIGH, 
                                   TaskPriority.NORMAL, TaskPriority.LOW]:
                        
                        queue_key = self._get_queue_key(task_type, priority)
                        
                        # 从有序集合中获取最高优先级的任务
                        task_ids = await self.redis_client.zrevrange(queue_key, 0, 0)
                        
                        if task_ids:
                            task_id = task_ids[0].decode() if isinstance(task_ids[0], bytes) else task_ids[0]
                            
                            # 获取任务信息
                            task_key = self._get_task_key(task_id)
                            task_data = await self.redis_client.get(task_key)
                            
                            if task_data:
                                # 从队列中移除任务
                                await self.redis_client.zrem(queue_key, task_id)
                                
                                # 更新任务状态
                                task = Task.model_validate_json(task_data)
                                task.status = TaskStatus.RUNNING
                                task.worker_id = worker_id
                                task.started_at = datetime.now()
                                
                                # 保存更新后的任务信息
                                await self.redis_client.setex(task_key, 86400, task.model_dump_json())
                                
                                logger.debug(f"工作者 {worker_id} 获取任务: {task_id}")
                                return task
                            else:
                                # 任务信息不存在，从队列中移除
                                await self.redis_client.zrem(queue_key, task_id)
                
                # 短暂等待后重试
                await asyncio.sleep(1)
            
            return None
            
        except Exception as e:
            logger.error(f"任务出队失败: {e}")
            return None
    
    async def complete_task(self, task_id: str, result: TaskResult) -> bool:
        """完成任务"""
        '''
        完成任务，更新任务状态和结果
        Args:
            task_id: 任务ID
            result: 任务结果
        Returns:
            是否成功
        '''
        try:
            if not self.is_connected:
                logger.error("Redis未连接")
                return False
            
            task_key = self._get_task_key(task_id)
            task_data = await self.redis_client.get(task_key)
            
            if not task_data:
                logger.error(f"任务不存在: {task_id}")
                return False
            
            task = Task.model_validate_json(task_data)
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.result = result
            
            # 保存更新后的任务信息
            await self.redis_client.setex(task_key, 86400, task.model_dump_json())
            
            # 保存任务结果（单独存储，可设置更短的过期时间）
            result_key = self._get_result_key(task_id)
            import json as _json
            from dataclasses import asdict as _asdict
            await self.redis_client.setex(result_key, 3600, _json.dumps(_asdict(result)))  # 结果保存1小时
            
            logger.info(f"任务完成: {task_id} (成功: {result.success})")
            return True
            
        except Exception as e:
            logger.error(f"完成任务失败: {e}")
            return False
    
    async def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        try:
            if not self.is_connected:
                return None
            
            task_key = self._get_task_key(task_id)
            task_data = await self.redis_client.get(task_key)
            
            if task_data:
                return Task.model_validate_json(task_data)
            else:
                return None
                
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None
    
    async def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        try:
            if not self.is_connected:
                return None
            
            result_key = self._get_result_key(task_id)
            result_data = await self.redis_client.get(result_key)
            
            if result_data:
                import json as _json
                try:
                    payload = _json.loads(result_data)
                    return TaskResult(**payload)
                except Exception:
                    return None
            else:
                # 尝试从任务信息中获取结果
                task = await self.get_task_status(task_id)
                if task and task.result:
                    return task.result
                return None
                
        except Exception as e:
            logger.error(f"获取任务结果失败: {e}")
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            if not self.is_connected:
                return False
            
            task = await self.get_task_status(task_id)
            if not task:
                return False
            
            # 只能从待处理状态取消
            if task.status != TaskStatus.PENDING:
                logger.warning(f"任务无法取消，当前状态: {task.status}")
                return False
            
            # 从队列中移除
            queue_key = self._get_queue_key(task.task_type, task.priority)
            await self.redis_client.zrem(queue_key, task_id)
            
            # 更新任务状态
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            
            task_key = self._get_task_key(task_id)
            await self.redis_client.setex(task_key, 86400, task.model_dump_json())
            
            logger.debug(f"任务已取消: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False
    
    async def get_queue_stats(self, task_type: Optional[TaskType] = None) -> Dict[str, int]:
        """获取队列统计信息"""
        try:
            if not self.is_connected:
                return {}
            
            stats = {}
            
            if task_type:
                # 获取特定类型的队列统计
                for priority in TaskPriority:
                    queue_key = self._get_queue_key(task_type, priority)
                    count = await self.redis_client.zcard(queue_key)
                    stats[f"{task_type.value}_{priority.name}"] = count
            else:
                # 获取所有类型的队列统计
                for task_type in TaskType:
                    for priority in TaskPriority:
                        queue_key = self._get_queue_key(task_type, priority)
                        count = await self.redis_client.zcard(queue_key)
                        stats[f"{task_type.value}_{priority.name}"] = count
            
            return stats
            
        except Exception as e:
            logger.error(f"获取队列统计失败: {e}")
            return {}
    
    async def cleanup_expired_tasks(self) -> int:
        """清理过期任务"""
        try:
            if not self.is_connected:
                return 0
            
            # 扫描所有任务键
            task_pattern = f"{self.task_prefix}:*"
            task_keys = await self.redis_client.keys(task_pattern)
            
            cleaned_count = 0
            current_time = datetime.now()
            
            for task_key in task_keys:
                task_data = await self.redis_client.get(task_key)
                if task_data:
                    try:
                        task = Task.model_validate_json(task_data)
                        
                        # 检查是否超时
                        if task.started_at and task.timeout:
                            elapsed = (current_time - task.started_at).total_seconds()
                            if elapsed > task.timeout and task.status == TaskStatus.RUNNING:
                                # 标记为失败
                                task.status = TaskStatus.FAILED
                                task.result = TaskResult(
                                    success=False,
                                    error="任务超时"
                                )
                                task.completed_at = current_time
                                
                                await self.redis_client.setex(task_key, 86400, task.model_dump_json())
                                cleaned_count += 1
                                
                    except Exception as e:
                        logger.error(f"处理任务清理失败 {task_key}: {e}")
            
            logger.debug(f"清理过期任务完成: {cleaned_count} 个")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")
            return 0


# 全局任务队列服务实例（延迟初始化以使用配置）
task_queue_service = None

def get_task_queue_service():
    """获取任务队列服务实例，使用配置中的Redis设置"""
    global task_queue_service
    if task_queue_service is None:
        from core.config import get_settings
        settings = get_settings()
        task_queue_service = TaskQueueService(
            redis_url=settings.REDIS_URL,
            db=settings.REDIS_DB
        )
    return task_queue_service
