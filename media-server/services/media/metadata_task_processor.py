"""
元数据任务处理器 - 处理元数据获取队列任务

功能特点：
- 处理元数据获取任务队列
- 支持插件限流和断路器机制
- 批量处理优化
- 错误处理和重试机制
- 支持取消操作
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict, deque

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_session as get_db_session
from services.task import (
    TaskQueueService, Task, TaskType, TaskStatus, TaskResult, TaskPriority
)
from services.media.metadata_enricher import metadata_enricher
from services.scraper import scraper_manager
from services.scraper.tmdb import TmdbScraper
from services.scraper.douban import DoubanScraper

logger = logging.getLogger(__name__)


class RateLimiter:
    """令牌桶限流器"""
    
    def __init__(self, rate: float, burst: int = 1):
        """
        初始化限流器
        
        Args:
            rate: 每秒生成令牌数
            burst: 最大突发令牌数
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = datetime.now()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        获取令牌（非阻塞），令牌不足时返回 False
        """
        async with self._lock:
            now = datetime.now()
            elapsed = (now - self.last_update).total_seconds()
            self.last_update = now
            
            # 生成新令牌
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            
            # 检查是否有足够令牌
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                return False
    
    async def wait_for_tokens(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """
        等待直到获取足够令牌或超时
        """
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(0.1)
        
        return False


class CircuitBreaker:
    """断路器"""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        """
        初始化断路器
        
        Args:
            failure_threshold: 失败阈值
            timeout: 断路器打开后的超时时间
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
        self._lock = asyncio.Lock()
    
    async def can_execute(self) -> bool:
        """
        检查断路器状态，决定是否允许执行
        """
        async with self._lock:
            if self.state == "closed":
                return True
            elif self.state == "open":
                if self.last_failure_time and (datetime.now() - self.last_failure_time).total_seconds() > self.timeout:
                    self.state = "half_open"
                    self.failure_count = 0
                    return True
                return False
            else:  # half_open
                return True
    
    async def record_success(self):
        """
        记录成功并关闭断路器
        """
        async with self._lock:
            self.failure_count = 0
            self.state = "closed"
    
    async def record_failure(self):
        """
        记录失败并在达到阈值时打开断路器
        """
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.warning(f"断路器打开，失败次数: {self.failure_count}")


class PluginManager:
    """插件管理器 - 管理刮削器插件的限流和断路器"""
    
    def __init__(self):
        # 插件限流器配置
        self.rate_limiters = {
            "tmdb": RateLimiter(rate=10.0, burst=5),      # TMDB: 10次/秒
            "douban": RateLimiter(rate=5.0, burst=3),    # 豆瓣: 5次/秒
        }
        
        # 插件断路器
        self.circuit_breakers = {
            "tmdb": CircuitBreaker(failure_threshold=5, timeout=60.0),
            "douban": CircuitBreaker(failure_threshold=3, timeout=120.0),
        }
        
        # 插件状态缓存
        self.plugin_status = {}
        self._lock = asyncio.Lock()
    
    async def can_use_plugin(self, plugin_name: str) -> bool:
        """
        检查插件是否满足断路器与限流要求
        """
        if plugin_name not in self.rate_limiters or plugin_name not in self.circuit_breakers:
            return False
        
        # 检查断路器状态
        circuit_breaker = self.circuit_breakers[plugin_name]
        if not await circuit_breaker.can_execute():
            logger.warning(f"插件 {plugin_name} 断路器打开，跳过使用")
            return False
        
        # 检查限流器
        rate_limiter = self.rate_limiters[plugin_name]
        if not await rate_limiter.acquire():
            logger.warning(f"插件 {plugin_name} 限流，等待令牌")
            # 等待令牌，但不阻塞太久
            if not await rate_limiter.wait_for_tokens(timeout=5.0):
                logger.error(f"插件 {plugin_name} 获取令牌超时")
                return False
        
        return True
    
    async def record_plugin_success(self, plugin_name: str):
        """
        记录插件调用成功，重置失败计数
        """
        if plugin_name in self.circuit_breakers:
            await self.circuit_breakers[plugin_name].record_success()
        
        async with self._lock:
            self.plugin_status[plugin_name] = {
                "last_success": datetime.now(),
                "consecutive_failures": 0
            }
    
    async def record_plugin_failure(self, plugin_name: str, error: str):
        """
        记录插件调用失败，更新断路器与状态
        """
        if plugin_name in self.circuit_breakers:
            await self.circuit_breakers[plugin_name].record_failure()
        
        async with self._lock:
            if plugin_name not in self.plugin_status:
                self.plugin_status[plugin_name] = {}
            
            status = self.plugin_status[plugin_name]
            status["last_failure"] = datetime.now()
            status["consecutive_failures"] = status.get("consecutive_failures", 0) + 1
            status["last_error"] = error
    
    def get_plugin_stats(self) -> Dict[str, Dict]:
        """
        获取插件断路器状态、限流令牌与最近成功/失败信息
        """
        return {
            plugin: {
                "circuit_breaker_state": self.circuit_breakers[plugin].state,
                "failure_count": self.circuit_breakers[plugin].failure_count,
                "rate_limiter_tokens": self.rate_limiters[plugin].tokens,
                **self.plugin_status.get(plugin, {})
            }
            for plugin in ["tmdb", "douban"]
        }


class MetadataTaskProcessor:
    """元数据任务处理器"""
    
    def __init__(self, task_queue_service: TaskQueueService):
        self.task_queue_service = task_queue_service
        self.plugin_manager = PluginManager()
        self.worker_id = f"metadata_worker_{id(self)}"
        self.is_running = False
        self.current_task: Optional[Task] = None
        self._cancel_requested = False
        
        # 批次处理配置
        self.batch_size = 50
        self.batch_timeout = 30.0  # 批次等待超时
        self.max_batch_wait = 100  # 最大批次等待文件数
        
        # 批次缓存
        self.pending_files: Dict[str, List[Dict]] = defaultdict(list)
        self.batch_timers: Dict[str, asyncio.Task] = {}
        self._batch_lock = asyncio.Lock()
    
    async def start(self):
        """
        启动主循环，持续从队列拉取并处理元数据任务
        """
        if self.is_running:
            logger.warning("元数据任务处理器已在运行")
            return
        
        self.is_running = True
        logger.info(f"元数据任务处理器启动: {self.worker_id}")
        
        try:
            while self.is_running:
                try:
                    # 从队列获取元数据获取任务
                    task = await self.task_queue_service.dequeue_task(
                        [TaskType.METADATA_FETCH], 
                        self.worker_id,
                        timeout=10
                    )
                    
                    if task:
                        await self._process_task(task)
                    else:
                        # 没有任务，短暂休眠
                        await asyncio.sleep(1)
                        
                except asyncio.CancelledError:
                    logger.info("元数据任务处理器被取消")
                    break
                except Exception as e:
                    logger.error(f"处理任务时出错: {e}")
                    await asyncio.sleep(5)  # 出错后等待一段时间
                    
        finally:
            self.is_running = False
            logger.info(f"元数据任务处理器停止: {self.worker_id}")
            
            # 清理批次定时器
            for timer in self.batch_timers.values():
                if not timer.done():
                    timer.cancel()
    
    async def stop(self):
        """
        请求停止处理器，清理定时器与状态
        """
        self.is_running = False
        self._cancel_requested = True
        logger.info(f"元数据任务处理器停止请求: {self.worker_id}")
        
        # 清理批次定时器
        for timer in self.batch_timers.values():
            if not timer.done():
                timer.cancel()
    
    async def _process_task(self, task: Task):
        """
        处理单个任务：解析参数、分支批量/单个、重试与完成回写
        """
        self.current_task = task
        self._cancel_requested = False
        
        logger.info(f"开始处理元数据任务: {task.id}")
        start_time = datetime.now()
        
        try:
            # 获取任务参数
            file_ids = task.params.get("file_ids", [])
            storage_id = task.params.get("storage_id")
            language = task.params.get("language", "zh-CN")
            batch_mode = task.params.get("batch_mode", True)
            
            if not file_ids:
                raise ValueError("缺少文件ID参数")
            
            if not storage_id:
                raise ValueError("缺少存储ID参数")
            
            # 批量处理优化
            if batch_mode and len(file_ids) > 1:
                result = await self._process_batch_files(
                    file_ids=file_ids,
                    storage_id=storage_id,
                    language=language,
                    task=task
                )
            else:
                result = await self._process_single_file(
                    file_id=file_ids[0] if file_ids else None,
                    storage_id=storage_id,
                    language=language,
                    task=task
                )
            
            # 计算耗时
            duration = (datetime.now() - start_time).total_seconds()
            
            # 创建任务结果
            task_result = TaskResult(
                success=True,
                data=result,
                duration=duration
            )
            
            # 完成任务
            await self.task_queue_service.complete_task(task.id, task_result)
            
            logger.info(f"元数据任务完成: {task.id}, 耗时: {duration:.2f}秒")
            
        except asyncio.CancelledError:
            logger.info(f"元数据任务被取消: {task.id}")
            task_result = TaskResult(
                success=False,
                error="任务被取消"
            )
            await self.task_queue_service.complete_task(task.id, task_result)
            
        except Exception as e:
            logger.error(f"元数据任务失败: {task.id}, 错误: {e}")
            
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
                
        finally:
            self.current_task = None
            self._cancel_requested = False
    
    async def _process_batch_files(self, file_ids: List[int], storage_id: int, 
                                 language: str, task: Task) -> Dict:
        """
        批量处理文件：分批并发丰富、统计结果与更新进度
        """
        logger.info(f"批量处理 {len(file_ids)} 个文件的元数据")
        
        result = {
            "total_files": len(file_ids),
            "processed_files": 0,
            "successful_enrichments": 0,
            "failed_enrichments": 0,
            "plugin_stats": {},
            "errors": []
        }
        
        # 分批处理
        batch_size = 20  # 每批处理20个文件
        for i in range(0, len(file_ids), batch_size):
            if self._cancel_requested:
                raise asyncio.CancelledError()
            
            batch_ids = file_ids[i:i + batch_size]
            logger.info(f"处理批次 {i//batch_size + 1}/{(len(file_ids) + batch_size - 1)//batch_size}")
            
            try:
                # 使用元数据丰富服务批量处理
                enrichment_results = await metadata_enricher.enrich_multiple_files(
                    file_ids=batch_ids,
                    preferred_language=language,
                    storage_id=storage_id
                )
                
                # 统计结果
                batch_success = sum(1 for success in enrichment_results.values() if success)
                batch_failed = len(enrichment_results) - batch_success
                
                result["successful_enrichments"] += batch_success
                result["failed_enrichments"] += batch_failed
                result["processed_files"] += len(batch_ids)
                
                # 记录插件使用情况
                for file_id, success in enrichment_results.items():
                    if success:
                        # 这里可以记录使用的插件信息
                        pass
                
                # 更新任务进度
                await self._update_task_progress(task, result)
                
                logger.info(f"批次完成: 成功 {batch_success} 个, 失败 {batch_failed} 个")
                
            except Exception as e:
                logger.error(f"批次处理失败: {e}")
                result["errors"].append({
                    "batch_index": i // batch_size,
                    "error": str(e)
                })
                result["failed_enrichments"] += len(batch_ids)
            
            # 批次间短暂休眠，避免过载
            if i + batch_size < len(file_ids):
                await asyncio.sleep(0.5)
        
        # 获取插件统计
        result["plugin_stats"] = self.plugin_manager.get_plugin_stats()
        
        return result
    
    async def _process_single_file(self, file_id: int, storage_id: int, 
                                 language: str, task: Task) -> Dict:
        """
        处理单个文件：调用丰富器批量接口处理一个文件并回填状态
        """
        logger.info(f"处理单个文件元数据: {file_id}")
        
        result = {
            "file_id": file_id,
            "processed": False,
            "successful": False,
            "plugin_used": None,
            "error": None
        }
        
        try:
            # 使用元数据丰富服务处理单个文件
            enrichment_results = await metadata_enricher.enrich_multiple_files(
                file_ids=[file_id],
                preferred_language=language,
                storage_id=storage_id
            )
            
            if file_id in enrichment_results:
                success = enrichment_results[file_id]
                result["processed"] = True
                result["successful"] = success
                
                if success:
                    logger.info(f"文件 {file_id} 元数据丰富成功")
                else:
                    logger.warning(f"文件 {file_id} 元数据丰富失败")
            
        except Exception as e:
            logger.error(f"处理文件 {file_id} 失败: {e}")
            result["error"] = str(e)
        
        return result
    
    async def _update_task_progress(self, task: Task, stats: Dict):
        """
        根据已处理/总数更新任务进度日志
        """
        try:
            total_files = stats.get("total_files", 0)
            processed_files = stats.get("processed_files", 0)
            successful_enrichments = stats.get("successful_enrichments", 0)
            
            if total_files > 0:
                progress = min(100, int((processed_files / total_files) * 100))
                logger.info(f"元数据任务进度: {task.id}, 进度: {progress}%, "
                          f"已处理: {processed_files}/{total_files}, "
                          f"成功: {successful_enrichments}")
                
        except Exception as e:
            logger.error(f"更新任务进度失败: {e}")
    
    async def create_batch_task(self, file_ids: List[int], storage_id: int, 
                              user_id: int, priority: TaskPriority = TaskPriority.NORMAL) -> str:
        """创建批量元数据获取任务"""
        try:
            # 创建任务
            task = Task(
                task_type=TaskType.METADATA_FETCH,
                priority=priority,
                params={
                    "file_ids": file_ids,
                    "storage_id": storage_id,
                    "language": "zh-CN",
                    "batch_mode": True,
                    "user_id": user_id
                },
                max_retries=3,
                retry_delay=300,  # 5分钟重试延迟
                timeout=7200  # 2小时超时
            )
            
            # 加入队列
            await self.task_queue_service.enqueue_task(task)
            
            logger.info(f"创建批量元数据任务: {task.id}, 文件数: {len(file_ids)}")
            
            return task.id
            
        except Exception as e:
            logger.error(f"创建批量元数据任务失败: {e}")
            raise


# 全局元数据任务处理器实例
metadata_task_processor: Optional[MetadataTaskProcessor] = None


async def get_metadata_task_processor() -> MetadataTaskProcessor:
    """
    获取元数据任务处理器全局实例（懒加载）
    """
    global metadata_task_processor
    if metadata_task_processor is None:
        from services.task_queue_service import task_queue_service
        metadata_task_processor = MetadataTaskProcessor(task_queue_service)
    return metadata_task_processor