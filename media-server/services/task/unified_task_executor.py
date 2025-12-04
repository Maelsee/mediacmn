"""
统一任务执行器 - 处理队列中的扫描和元数据任务

功能特点：
- 统一的任务执行引擎
- 支持扫描任务、元数据任务、组合任务
- 集成统一扫描引擎和任务调度框架
- 实时进度更新和状态跟踪
- 错误处理和重试机制
- 资源使用监控

执行流程：
1. 从任务队列获取任务
2. 根据任务类型调用相应的执行器
3. 更新任务状态和进度
4. 处理执行结果和错误
5. 完成任务并更新统计信息
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any

from .task_queue_service import (
    TaskQueueService, Task, TaskType, TaskStatus, TaskResult
)
from .unified_task_scheduler import (
    UnifiedTaskScheduler, get_unified_task_scheduler
)

logger = logging.getLogger(__name__)


class UnifiedTaskExecutor:
    """统一任务执行器"""
    
    def __init__(self):
        self.task_queue_service: Optional[TaskQueueService] = None
        self.task_scheduler: Optional[UnifiedTaskScheduler] = None
        self.worker_id: str = f"unified_executor_{id(self)}"
        self.is_running = False
        self.current_task: Optional[Task] = None
        self._initialized = False
        self.stats = {
            "tasks_processed": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "start_time": None,
            "last_task_time": None,
            "batch_persist": {
                "batches": 0,
                "tasks": 0,
                "succeeded": 0,
                "failed": 0,
                "avg_batch_size": 0.0,
                "last_batch_duration": 0.0
            }
        }
    
    async def initialize(self):
        """初始化执行器"""
        if self._initialized:
            return
        
        try:
            # 获取任务队列服务并连接
            from .task_queue_service import get_task_queue_service
            self.task_queue_service = get_task_queue_service()
            await self.task_queue_service.connect()
            
            # 获取任务调度器
            self.task_scheduler = await get_unified_task_scheduler()
            
            self._initialized = True
            logger.debug(f"统一任务执行器初始化完成: {self.worker_id}")
            
        except Exception as e:
            logger.error(f"初始化统一任务执行器失败: {e}")
            raise
    
    async def start(self):
        """启动执行器"""
        if self.is_running:
            logger.warning("统一任务执行器已在运行")
            return
        
        await self.initialize()
        
        self.is_running = True
        self.stats["start_time"] = datetime.now()
        logger.debug(f"统一任务执行器启动: {self.worker_id}")
        
        try:
            while self.is_running:
                try:
                    # 从队列获取任务
                    task = await self.task_queue_service.dequeue_task(
                        [TaskType.SCAN, TaskType.METADATA_FETCH, TaskType.COMBINED_SCAN, TaskType.DELETE_SYNC, TaskType.SIDECAR_LOCALIZE, TaskType.PERSIST_METADATA],
                        self.worker_id,
                        timeout=10
                    )
                    
                    if task:
                        await self._execute_task(task)
                    else:
                        # 没有任务，短暂休眠
                        await asyncio.sleep(1)
                        
                except asyncio.CancelledError:
                    logger.debug("统一任务执行器被取消")
                    break
                except Exception as e:
                    logger.error(f"处理任务时出错: {e}")
                    await asyncio.sleep(5)  # 出错后等待一段时间
                    
        finally:
            self.is_running = False
            logger.debug(f"统一任务执行器停止: {self.worker_id}")
    
    async def stop(self):
        """停止执行器"""
        self.is_running = False
        logger.debug(f"统一任务执行器停止请求: {self.worker_id}")
    
    async def _execute_task(self, task: Task):
        """执行任务"""
        self.current_task = task
        start_time = datetime.now()
        
        logger.debug(f"开始执行任务: {task.id}, 类型: {task.task_type.value}")
        
        try:
            # 更新任务状态
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            
            if task.task_type == TaskType.PERSIST_METADATA:
                from core.config import get_settings
                settings = get_settings()
                max_size = int(getattr(settings, "PERSIST_BATCH_MAX_SIZE", 100))
                max_wait_ms = int(getattr(settings, "PERSIST_BATCH_MAX_WAIT_MS", 800))
                batch = [task]
                batch_start = time.time()
                while len(batch) < max_size and (time.time() - batch_start) < (max_wait_ms / 1000.0):
                    nxt = await self.task_queue_service.dequeue_task(
                        [TaskType.PERSIST_METADATA], self.worker_id, timeout=1
                    )
                    if not nxt:
                        break
                    batch.append(nxt)
                # 分桶优化（按 contract_type/provider/user_id）
                bucket_enabled = bool(getattr(settings, "PERSIST_BUCKET_ENABLED", True))
                if bucket_enabled and len(batch) > 1:
                    buckets = {}
                    for bt in batch:
                        p = bt.params or {}
                        key = (p.get("contract_type"), p.get("provider"), p.get("user_id"))
                        buckets.setdefault(key, []).append(bt)
                    results_all = {}
                    succeeded_all = 0
                    failed_all = 0
                    total_dur = 0.0
                    for key, group in buckets.items():
                        execution_result = await self.task_scheduler.execute_persist_batch(group)
                        dur = execution_result.duration or (datetime.now() - start_time).total_seconds()
                        total_dur += dur
                        results = (execution_result.data or {}).get("results", {})
                        succeeded = sum(1 for g in group if bool(results.get(g.id)))
                        failed = len(group) - succeeded
                        succeeded_all += succeeded
                        failed_all += failed
                        results_all.update(results)
                        for g in group:
                            ok = bool(results.get(g.id))
                            tr = TaskResult(success=ok, data=None, error=None, duration=dur)
                            await self.task_queue_service.complete_task(g.id, tr)
                            self.stats["tasks_processed"] += 1
                            self.stats["last_task_time"] = datetime.now()
                            if ok:
                                self.stats["tasks_succeeded"] += 1
                            else:
                                self.stats["tasks_failed"] += 1
                    prev_batches = self.stats["batch_persist"]["batches"]
                    prev_tasks = self.stats["batch_persist"]["tasks"]
                    new_tasks = prev_tasks + len(batch)
                    new_batches = prev_batches + len(buckets)
                    self.stats["batch_persist"]["batches"] = new_batches
                    self.stats["batch_persist"]["tasks"] = new_tasks
                    self.stats["batch_persist"]["succeeded"] += succeeded_all
                    self.stats["batch_persist"]["failed"] += failed_all
                    try:
                        self.stats["batch_persist"]["avg_batch_size"] = (new_tasks / new_batches) if new_batches > 0 else 0.0
                    except Exception:
                        pass
                    self.stats["batch_persist"]["last_batch_duration"] = total_dur
                    return
                execution_result = await self.task_scheduler.execute_persist_batch(batch)
                dur = execution_result.duration or (datetime.now() - start_time).total_seconds()
                results = (execution_result.data or {}).get("results", {})
                succeeded = sum(1 for bt in batch if bool(results.get(bt.id)))
                failed = len(batch) - succeeded
                prev_batches = self.stats["batch_persist"]["batches"]
                prev_tasks = self.stats["batch_persist"]["tasks"]
                new_tasks = prev_tasks + len(batch)
                new_batches = prev_batches + 1
                self.stats["batch_persist"]["batches"] = new_batches
                self.stats["batch_persist"]["tasks"] = new_tasks
                self.stats["batch_persist"]["succeeded"] += succeeded
                self.stats["batch_persist"]["failed"] += failed
                self.stats["batch_persist"]["last_batch_duration"] = dur
                try:
                    self.stats["batch_persist"]["avg_batch_size"] = (new_tasks / new_batches) if new_batches > 0 else 0.0
                except Exception:
                    pass
                for bt in batch:
                    ok = bool(results.get(bt.id))
                    tr = TaskResult(success=ok, data=None, error=None, duration=dur)
                    await self.task_queue_service.complete_task(bt.id, tr)
                    self.stats["tasks_processed"] += 1
                    self.stats["last_task_time"] = datetime.now()
                    if ok:
                        self.stats["tasks_succeeded"] += 1
                    else:
                        self.stats["tasks_failed"] += 1
            else:
                execution_result = await self.task_scheduler.execute_task(task)
                task_result = TaskResult(
                    success=execution_result.success,
                    data=execution_result.data,
                    error=execution_result.error,
                    duration=execution_result.duration or (datetime.now() - start_time).total_seconds()
                )
                await self.task_queue_service.complete_task(task.id, task_result)
                self.stats["tasks_processed"] += 1
                self.stats["last_task_time"] = datetime.now()
                if execution_result.success:
                    self.stats["tasks_succeeded"] += 1
                    logger.info(f"任务执行成功: {task.id}, 耗时: {task_result.duration:.2f}秒")
                else:
                    self.stats["tasks_failed"] += 1
                    logger.warning(f"任务执行失败: {task.id}, 错误: {execution_result.error}")
            
        except asyncio.CancelledError:
            logger.info(f"任务被取消: {task.id}")
            task_result = TaskResult(
                success=False,
                error="任务被取消"
            )
            await self.task_queue_service.complete_task(task.id, task_result)
            
        except Exception as e:
            logger.error(f"任务执行失败: {task.id}, 错误: {e}")
            
            # 检查是否需要重试
            if task.retry_count < task.max_retries:
                logger.info(f"任务将重试: {task.id} (第 {task.retry_count + 1} 次)")
                
                # 更新重试信息
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                
                # 延迟后重新加入队列
                await asyncio.sleep(task.retry_delay)
                await self.task_queue_service.enqueue_task(task)
            else:
                # 达到最大重试次数，标记为失败
                task_result = TaskResult(
                    success=False,
                    error=str(e)
                )
                await self.task_queue_service.complete_task(task.id, task_result)
                
                self.stats["tasks_failed"] += 1
                self.stats["last_task_time"] = datetime.now()
                
        finally:
            self.current_task = None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取执行器统计信息"""
        uptime = None
        if self.stats["start_time"]:
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        return {
            "worker_id": self.worker_id,
            "is_running": self.is_running,
            "current_task": self.current_task.id if self.current_task else None,
            "stats": {
                **self.stats,
                "uptime": uptime,
                "success_rate": (
                    self.stats["tasks_succeeded"] / self.stats["tasks_processed"] * 100
                    if self.stats["tasks_processed"] > 0 else 0
                )
            }
        }


# 创建全局执行器实例
unified_task_executor = UnifiedTaskExecutor()


async def get_unified_task_executor() -> UnifiedTaskExecutor:
    """获取统一任务执行器实例"""
    return unified_task_executor


class TaskExecutorManager:
    """任务执行器管理器 - 管理多个执行器实例"""
    
    def __init__(self):
        self.executors: list[UnifiedTaskExecutor] = []
        self.is_running = False
    
    async def start_executors(self, count: int = 1):
        """启动多个执行器"""
        if self.is_running:
            logger.warning("任务执行器管理器已在运行")
            return
        
        self.is_running = True
        logger.info(f"启动 {count} 个任务执行器")
        
        # 创建并启动执行器
        for i in range(count):
            executor = UnifiedTaskExecutor()
            self.executors.append(executor)
            
            # 启动执行器（不等待，后台运行）
            asyncio.create_task(executor.start())
            
            # 短暂延迟，避免同时启动
            await asyncio.sleep(0.1)
        
        logger.info(f"任务执行器管理器启动完成，共 {len(self.executors)} 个执行器")
    
    async def stop_executors(self):
        """停止所有执行器"""
        if not self.is_running:
            return
        
        logger.info("停止所有任务执行器")
        
        # 停止所有执行器
        for executor in self.executors:
            await executor.stop()
        
        self.executors.clear()
        self.is_running = False
        
        logger.info("任务执行器管理器已停止")
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有执行器的统计信息"""
        all_stats = {
            "total_executors": len(self.executors),
            "is_running": self.is_running,
            "executors": []
        }
        
        for executor in self.executors:
            all_stats["executors"].append(executor.get_stats())
        
        # 汇总统计
        total_processed = sum(stats["stats"]["tasks_processed"] for stats in all_stats["executors"])
        total_succeeded = sum(stats["stats"]["tasks_succeeded"] for stats in all_stats["executors"])
        total_failed = sum(stats["stats"]["tasks_failed"] for stats in all_stats["executors"])
        
        all_stats["summary"] = {
            "total_tasks_processed": total_processed,
            "total_tasks_succeeded": total_succeeded,
            "total_tasks_failed": total_failed,
            "overall_success_rate": (
                total_succeeded / total_processed * 100 if total_processed > 0 else 0
            )
        }
        
        return all_stats


# 创建全局管理器实例
task_executor_manager = TaskExecutorManager()


async def get_task_executor_manager() -> TaskExecutorManager:
    """获取任务执行器管理器"""
    return task_executor_manager
