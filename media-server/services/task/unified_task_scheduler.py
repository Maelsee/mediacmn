"""
统一任务调度框架 - 高效异步扫描与刮削架构的任务管理层

功能特点：
- 统一的任务创建、调度和管理
- 支持扫描任务和元数据任务的协调执行
- 任务状态实时跟踪和查询
- 优先级队列支持
- 任务依赖和链式执行
- 批量任务优化处理

架构设计：
- 任务调度器：负责任务生命周期管理
- 任务协调器：协调扫描和元数据任务的执行顺序
- 状态管理器：实时跟踪任务状态和进度
- 批量优化器：优化批量任务的执行效率
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from .task_queue_service import (
    TaskQueueService, Task, TaskType, TaskStatus, TaskPriority, TaskResult
)
from services.scan.unified_scan_engine import UnifiedScanEngine, ScanResult, get_unified_scan_engine
from services.media.metadata_task_processor import (
    MetadataTaskProcessor, RateLimiter, CircuitBreaker
)
from services.media.metadata_enricher import metadata_enricher
from services.media.sidecar_localize_processor import SidecarLocalizeProcessor
from services.media.delete_sync_service import DeleteSyncService

logger = logging.getLogger(__name__)


class TaskCategory(Enum):
    """任务类别"""
    SCAN = "scan"
    METADATA = "metadata"
    COMBINED = "combined"  # 扫描+元数据组合任务


@dataclass
class TaskContext:
    """任务上下文"""
    task_id: str
    user_id: int
    storage_id: int
    task_category: TaskCategory
    created_at: datetime
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskExecutionResult:
    """任务执行结果"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration: float = 0.0
    sub_task_ids: List[str] = field(default_factory=list)


class UnifiedTaskScheduler:
    """统一任务调度器"""
    
    def __init__(self):
        self.task_queue_service: Optional[TaskQueueService] = None
        self.scan_processor: Optional[UnifiedScanEngine] = None
        self.metadata_processor: Optional[MetadataTaskProcessor] = None
        self.sidecar_processor: Optional[SidecarLocalizeProcessor] = None
        self._initialized = False
        self.delete_sync = DeleteSyncService()
    
    async def initialize(self):
        """初始化调度器"""
        if self._initialized:
            return
        
        try:
            # 获取任务队列服务
            from .task_queue_service import get_task_queue_service
            self.task_queue_service = get_task_queue_service()
            connected = await self.task_queue_service.connect()
            if not connected:
                logger.error("Redis未连接，任务队列不可用")
            
            # 获取扫描处理器
            self.scan_processor = await get_unified_scan_engine()
            
            # 获取元数据处理器
            self.metadata_processor = MetadataTaskProcessor(self.task_queue_service)
            # 获取侧车本地化处理器
            self.sidecar_processor = SidecarLocalizeProcessor()
            
            self._initialized = True
            logger.debug("统一任务调度器初始化完成")
            
        except Exception as e:
            logger.error(f"初始化统一任务调度器失败: {e}")
            raise
    
    async def create_scan_task(
        self,
        storage_id: int,
        scan_path: str = "/",
        recursive: bool = True,
        max_depth: int = 10,
        enable_metadata_enrichment: bool = False,
        enable_delete_sync: bool = True,
        user_id: int = 1,
        priority: TaskPriority = TaskPriority.NORMAL,
        batch_size: int = 100
    ) -> str:
        """
        创建扫描任务
        
        Args:
            storage_id: 存储配置ID
            scan_path: 扫描路径
            recursive: 是否递归扫描
            max_depth: 最大递归深度
            enable_metadata_enrichment: 是否启用元数据丰富
            user_id: 用户ID
            priority: 任务优先级
            batch_size: 批量处理大小
            enable_delete_sync: 是否启用删除同步
        Returns:
            任务ID
        """
        await self.initialize()
        
        try:
            logger.debug(f"创建扫描任务: storage_id={storage_id}, path={scan_path}, metadata={enable_metadata_enrichment}, delete_sync={enable_delete_sync}")
            
            # 根据是否启用元数据丰富，选择任务类型
            task_type = TaskType.COMBINED_SCAN if enable_metadata_enrichment else TaskType.SCAN
            
            # 创建任务
            task = Task(
                task_type=task_type,
                priority=priority,
                params={
                    "storage_id": storage_id,
                    "scan_path": scan_path,
                "recursive": recursive,
                "max_depth": max_depth,
                "enable_metadata_enrichment": enable_metadata_enrichment,
                "enable_delete_sync": enable_delete_sync,
                "user_id": user_id,
                "batch_size": batch_size,
                "create_metadata_tasks": enable_metadata_enrichment,
                "parse_snapshot": None
            },
            max_retries=3,
            retry_delay=300,  # 5分钟重试延迟
            timeout=3600  # 1小时超时
            )
            
            # 加入队列
            enqueue_ok = await self.task_queue_service.enqueue_task(task)
            if not enqueue_ok:
                logger.error("扫描任务加入队列失败: 队列不可用或Redis未连接")
                raise Exception("queue_unavailable")
            
            logger.debug(f"扫描任务创建成功: {task.id}")
            return task.id
            
        except Exception as e:
            logger.error(f"创建扫描任务失败: {e}")
            raise
    
    async def create_metadata_task(
        self,
        storage_id: int,
        file_ids: List[int],
        user_id: int = 1,
        language: str = "zh-CN",
        priority: TaskPriority = TaskPriority.NORMAL,
        batch_size: int = 20,
        parse_snapshot_map: Optional[Dict[int, Dict]] = None
    ) -> List[str]:
        """
        创建元数据任务（批量）
        
        Args:
            storage_id: 存储配置ID
            file_ids: 文件ID列表
            user_id: 用户ID
            language: 语言
            priority: 任务优先级
            batch_size: 每批处理的文件数
            
        Returns:
            任务ID列表
        """
        await self.initialize()
        
        try:
            logger.debug(f"创建元数据任务: storage_id={storage_id}, files={len(file_ids)}")
            
            task_ids = []
            
            # 分批创建任务
            for i in range(0, len(file_ids), batch_size):
                batch_file_ids = file_ids[i:i + batch_size]
                
                # 创建元数据获取任务
                metadata_task = Task(
                    task_type=TaskType.METADATA_FETCH,
                    priority=priority,
                    params={
                        "file_ids": batch_file_ids,
                        "storage_id": storage_id,
                        "language": language,
                        "batch_mode": True,
                        "user_id": user_id,
                        "parse_snapshot": {fid: (parse_snapshot_map.get(fid) if parse_snapshot_map else None) for fid in batch_file_ids}
                    },
                    max_retries=3,
                    retry_delay=300,  # 5分钟重试延迟
                    timeout=7200  # 2小时超时
                )
                
                # 加入队列
                await self.task_queue_service.enqueue_task(metadata_task)
                task_ids.append(metadata_task.id)
                
                logger.debug(f"创建元数据批次任务: {metadata_task.id}, 文件数: {len(batch_file_ids)}")
            
            logger.debug(f"元数据任务创建完成: 总计 {len(task_ids)} 个任务")
            return task_ids
            
        except Exception as e:
            logger.error(f"创建元数据任务失败: {e}")
            raise
    

    
    async def execute_task(self, task: Task) -> TaskExecutionResult:
        """
        执行任务
        
        Args:
            task: 任务对象
            
        Returns:
            执行结果
        """
        start_time = datetime.now()
        
        try:
            logger.debug(f"开始执行任务: {task.id}, 类型: {task.task_type.value}")
            
            if task.task_type == TaskType.SCAN:
                result = await self._execute_scan_task(task)
            elif task.task_type == TaskType.METADATA_FETCH:
                result = await self._execute_metadata_task(task)
            elif task.task_type == TaskType.COMBINED_SCAN:
                result = await self._execute_combined_task(task)
            elif task.task_type == TaskType.DELETE_SYNC:
                result = await self._execute_delete_sync_task(task)
            elif task.task_type == TaskType.SIDECAR_LOCALIZE:
                result = await self._execute_sidecar_localize_task(task)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")
            
            result.duration = (datetime.now() - start_time).total_seconds()
            
            logger.debug(f"任务{task.task_type.value}执行完成: {task.id}, 耗时: {result.duration:.2f}秒, 成功: {result.success}")
            
            return result
            
        except Exception as e:
            logger.error(f"任务执行失败: {task.id}, 错误: {e}")
            return TaskExecutionResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start_time).total_seconds()
            )
    
    async def _execute_scan_task(self, task: Task) -> TaskExecutionResult:
        """执行扫描任务"""
        try:
            params = task.params
            storage_id = params.get("storage_id")
            scan_path = params.get("scan_path", "/")
            recursive = params.get("recursive", True)
            max_depth = params.get("max_depth", 10)
            user_id = params.get("user_id", 1)
            batch_size = params.get("batch_size", 100)
            
            # 执行扫描
            scan_result = await self.scan_processor.scan_storage(
                storage_id=storage_id,
                scan_path=scan_path,
                recursive=recursive,
                max_depth=max_depth,
                user_id=user_id,
                batch_size=batch_size
            )
            
            return TaskExecutionResult(
                success=True,
                data={
                    "scan_result": scan_result.__dict__,
                    "new_file_ids": scan_result.new_file_ids,
                    "total_files": scan_result.total_files,
                    "new_files": scan_result.new_files,
                    "updated_files": scan_result.updated_files
                }
            )
            
        except Exception as e:
            logger.error(f"扫描任务执行失败: {task.id}, 错误: {e}")
            return TaskExecutionResult(success=False, error=str(e))
    
    async def _execute_metadata_task(self, task: Task) -> TaskExecutionResult:
        """执行元数据任务"""
        try:
            params = task.params
            file_ids = params.get("file_ids", [])
            storage_id = params.get("storage_id")
            language = params.get("language", "zh-CN")
            existing_snapshot_map = params.get("parse_snapshot") or {}
            
            if not file_ids:
                return TaskExecutionResult(success=True, data={"processed": 0, "succeeded": 0})
            
            # 使用元数据处理器执行任务
            success_count = 0
            results = {}
            
            for file_id in file_ids:
                try:
                    success = await metadata_enricher.enrich_media_file(file_id, language, storage_id=storage_id, existing_snapshot=existing_snapshot_map.get(file_id))
                    results[file_id] = success
                    if success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"元数据丰富失败 - 文件ID: {file_id}, 错误: {e}")
                    results[file_id] = False
            
            return TaskExecutionResult(
                success=True,
                data={
                    "processed": len(file_ids),
                    "succeeded": success_count,
                    "results": results
                }
            )
            
        except Exception as e:
            logger.error(f"元数据任务执行失败: {task.id}, 错误: {e}")
            return TaskExecutionResult(success=False, error=str(e))
    
    async def _execute_combined_task(self, task: Task) -> TaskExecutionResult:
        """执行组合任务（扫描+元数据）"""
        try:
            # 第一步：执行扫描
            scan_result = await self._execute_scan_task(task)
            
            if not scan_result.success:
                return scan_result
            
            # 获取新文件ID列表与轻量快照
            new_file_ids = scan_result.data.get("new_file_ids", [])
            new_file_snapshots = scan_result.data.get("scan_result", {}).get("new_file_snapshots", {})
            

            params = task.params
            storage_id = params.get("storage_id")
            user_id = params.get("user_id", 1)
            language = params.get("language", "zh-CN")
            metadata_task_ids: List[str] = []

            if new_file_ids:
                logger.debug(f"组合任务发现 {len(new_file_ids)} 个新文件，将创建元数据任务: {task.id}")
                
                # 第二步：创建元数据任务
               
                
                # 附带轻量快照到元数据任务参数
                # 将每个新文件的快照字典传递到元数据任务
                parse_snapshot = new_file_snapshots if isinstance(new_file_snapshots, dict) else None
               
                metadata_task_ids = await self.create_metadata_task(
                    storage_id=storage_id,
                    file_ids=new_file_ids,
                    user_id=user_id,
                    language=language,
                    priority=TaskPriority.NORMAL,  # 元数据任务使用普通优先级
                    parse_snapshot_map=parse_snapshot
                )

                # 更新扫描结果，添加元数据任务信息
                scan_result.data["metadata_task_ids"] = metadata_task_ids
                scan_result.sub_task_ids = metadata_task_ids
            
            else:
                # 没有新文件
                logger.debug(f"组合任务未发现新文件，跳过元数据丰富: {task.id}")
             
            # 第三步：删除对齐任务（如果开启），
            
            enable_delete_sync = params.get("enable_delete_sync", True)
            if enable_delete_sync:
                encountered = scan_result.data.get("scan_result", {}).get("encountered_media_paths", [])
                delete_task = Task(
                    task_type=TaskType.DELETE_SYNC,
                    priority=TaskPriority.NORMAL,
                    params={
                        "storage_id": storage_id,
                        "scan_path": params.get("scan_path", "/"),
                        "encountered_media_paths": encountered,
                        "user_id": user_id
                    },
                    max_retries=3,
                    retry_delay=300,
                    timeout=1800
                )
                logger.debug(
                    f"创建删除对齐任务: {delete_task.id}, storage_id={storage_id}, encountered_count={len(encountered)}"
                )
                await self.task_queue_service.enqueue_task(delete_task)
                scan_result.sub_task_ids.append(delete_task.id)
                scan_result.data.setdefault("delete_sync_task_id", delete_task.id)
      
            logger.debug(
                f"组合任务创建完成，扫描文件: {scan_result.data.get('total_files')}, 元数据任务: {len(metadata_task_ids)}, 删除任务: {scan_result.data.get('delete_sync_task_id')}"
            )
            
            return scan_result
        
        except Exception as e:
            logger.error(f"组合任务执行失败: {task.id}, 错误: {e}")
            return TaskExecutionResult(success=False, error=str(e))



    async def _execute_delete_sync_task(self, task: Task) -> TaskExecutionResult:
        """执行删除对齐任务"""

        try:
            params = task.params
            storage_id = params.get("storage_id")
            scan_path = params.get("scan_path", "/")
            encountered = params.get("encountered_media_paths", [])
            diff = self.delete_sync.compute_missing(storage_id, scan_path, encountered)
            moved_files = self.delete_sync.detect_moves_by_etag(storage_id, diff.get("missing"), encountered) if diff.get("missing") else 0
            removed_files = self.delete_sync.soft_delete_files(diff.get("missing")) if diff.get("missing") else 0
            affected_cores = set([fa.core_id for fa in (diff.get("missing") or []) if getattr(fa, "core_id", None)])
            cascade_summary = {"episodes": 0, "seasons": 0, "series": 0}
            for core_id in affected_cores:
                res = self.delete_sync.cascade_recursive_cleanup(core_id)
                if isinstance(res, dict):
                    cascade_summary["episodes"] += int(res.get("episodes", 0))
                    cascade_summary["seasons"] += int(res.get("seasons", 0))
                    cascade_summary["series"] += int(res.get("series", 0))
                else:
                    cascade_summary["series"] += int(res or 0)
            data = {
                "missing_count": len(diff.get("missing") or []),
                "moved_files": moved_files,
                "removed_files": removed_files,
                "cascade_removed": cascade_summary
            }
            logger.debug(
                f"删除对齐任务完成: {task.id}, missing={data['missing_count']}, moved={moved_files}, removed={removed_files}, cascade_removed={cascade_summary}"
            )
            return TaskExecutionResult(success=True, data=data)
        except Exception as e:
            logger.error(f"删除对齐任务失败: {e}")
            return TaskExecutionResult(success=False, error=str(e))

    async def _execute_sidecar_localize_task(self, task: Task) -> TaskExecutionResult:
        """执行侧车文件本地化任务"""
        try:
            params = task.params
            file_id = params.get("file_id")
            storage_id = params.get("storage_id")
            language = params.get("language", "zh-CN")
            ok = await self.sidecar_processor.process(file_id=file_id, storage_id=storage_id, language=language)
            return TaskExecutionResult(success=bool(ok), data={"file_id": file_id, "localized": bool(ok)})
        except Exception as e:
            logger.error(f"侧车本地化任务执行失败: {task.id}, 错误: {e}")
            return TaskExecutionResult(success=False, error=str(e))
    
    
   
    
    
    async def get_task_status(self, task_id: str, user_id: int) -> Optional[Dict]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            user_id: 用户ID
            
        Returns:
            任务状态信息
        """
        await self.initialize()
        
        try:
            # 从队列服务获取任务状态
            task = await self.task_queue_service.get_task_status(task_id)
            
            if not task:
                return None
            
            # 验证用户权限
            task_user_id = task.params.get("user_id")
            if task_user_id and task_user_id != user_id:
                logger.warning(f"用户 {user_id} 尝试访问任务 {task_id} 但权限不足")
                return None
            
            # 构建状态信息
            status_info = {
                "task_id": task.id,
                "task_type": task.task_type.value,
                "status": task.status.value,
                "priority": task.priority.value,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "params": {
                    k: v for k, v in task.params.items() 
                    if k not in ["user_id"]  # 移除敏感信息
                }
            }
            
            # 添加结果信息
            if task.result:
                status_info["result"] = {
                    "success": task.result.success,
                    "duration": task.result.duration,
                    "data": task.result.data,
                    "error": task.result.error
                }
            
            return status_info
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None
    
    async def get_user_tasks(
        self,
        user_id: int,
        task_type: Optional[TaskType] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        获取用户的任务列表
        
        Args:
            user_id: 用户ID
            task_type: 任务类型筛选
            status: 状态筛选
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            任务列表信息
        """
        await self.initialize()
        
        try:
            # 这里应该实现从数据库或缓存获取用户任务列表
            # 目前返回模拟数据，实际应该从数据库查询
            tasks = []
            
            # TODO: 实现完整的任务查询逻辑
            # 由于需要实现完整的任务查询逻辑，这里先返回空列表
            
            return {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset,
                "has_more": False
            }
            
        except Exception as e:
            logger.error(f"获取用户任务列表失败: {e}")
            return {"tasks": [], "total": 0, "limit": limit, "offset": offset, "has_more": False}
    
    async def cancel_task(self, task_id: str, user_id: int) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            user_id: 用户ID
            
        Returns:
            是否成功取消
        """
        await self.initialize()
        
        try:
            # 获取任务
            task = await self.task_queue_service.get_task(task_id)
            
            if not task:
                return False
            
            # 验证用户权限
            task_user_id = task.params.get("user_id")
            if task_user_id and task_user_id != user_id:
                logger.warning(f"用户 {user_id} 尝试取消任务 {task_id} 但权限不足")
                return False
            
            # 取消任务
            success = await self.task_queue_service.cancel_task(task_id)
            
            if success:
                logger.info(f"任务取消成功: {task_id}")
            else:
                logger.warning(f"任务取消失败: {task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False
    
    def get_plugin_health_status(self) -> Dict:
        """获取插件健康状态"""
        if not self.metadata_processor:
            return {}
        
        try:
            # 获取插件管理器
            plugin_manager = getattr(self.metadata_processor, 'plugin_manager', None)
            if not plugin_manager:
                return {}
            
            # 构建健康状态信息
            health_status = {}
            
            # 获取限流器状态
            rate_limiters = getattr(plugin_manager, 'rate_limiters', {})
            for plugin_name, limiter in rate_limiters.items():
                health_status[plugin_name] = {
                    "rate_limiter_tokens": getattr(limiter, 'tokens', 0),
                    "last_update": getattr(limiter, 'last_update', datetime.now()).isoformat()
                }
            
            # 获取断路器状态
            circuit_breakers = getattr(plugin_manager, 'circuit_breakers', {})
            for plugin_name, breaker in circuit_breakers.items():
                if plugin_name not in health_status:
                    health_status[plugin_name] = {}
                health_status[plugin_name].update({
                    "circuit_breaker_state": getattr(breaker, 'state', 'unknown'),
                    "failure_count": getattr(breaker, 'failure_count', 0)
                })
            
            return {"plugin_stats": health_status}
            
        except Exception as e:
            logger.error(f"获取插件健康状态失败: {e}")
            return {}


# 创建全局调度器实例
unified_task_scheduler = UnifiedTaskScheduler()


async def get_unified_task_scheduler() -> UnifiedTaskScheduler:
    """获取统一任务调度器实例"""
    await unified_task_scheduler.initialize()
    return unified_task_scheduler
    async def _execute_delete_sync_task(self, task: Task) -> TaskExecutionResult:
        """执行删除对齐任务"""
        try:
            params = task.params
            storage_id = params.get("storage_id")
            scan_path = params.get("scan_path", "/")
            encountered = params.get("encountered_media_paths", [])
            # 计算缺失集合（按 storage 过滤，不再严格前缀）
            diff = self.delete_sync.compute_missing(storage_id, scan_path, encountered)
            moved_files = self.delete_sync.detect_moves_by_etag(storage_id, diff["missing"], encountered) if diff["missing"] else 0
            removed_files = self.delete_sync.soft_delete_files(diff["missing"]) if diff["missing"] else 0
            affected_cores = set([fa.core_id for fa in diff["missing"] if fa.core_id])
            cascade_removed = 0
            for core_id in affected_cores:
                cascade_removed += self.delete_sync.cascade_recursive_cleanup(core_id)
            data = {
                "missing_count": len(diff["missing"]) if diff else 0,
                "moved_files": moved_files,
                "removed_files": removed_files,
                "cascade_removed": cascade_removed
            }
            logger.info(
                f"删除对齐任务完成: {task.id}, missing={data['missing_count']}, moved={moved_files}, removed={removed_files}, cascade_removed={cascade_removed}"
            )
            return TaskExecutionResult(success=True, data=data)
        except Exception as e:
            logger.error(f"删除对齐任务失败: {e}")
            return TaskExecutionResult(success=False, error=str(e))