"""
增强异步扫描服务 - 基于统一扫描引擎和任务调度框架的高级服务

功能特点：
- 基于统一扫描引擎的高效文件扫描
- 集成任务调度框架的异步任务管理
- 支持扫描+元数据的组合任务
- 完整的任务状态跟踪和查询
- 插件健康状态监控
- 向后兼容现有API接口

架构优势：
- 解耦设计：扫描引擎与任务调度分离
- 插件化扩展：支持自定义扫描处理器
- 批量优化：支持大批量文件的高效处理
- 限流保护：内置第三方API限流机制
- 故障隔离：断路器防止级联故障
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from services.task import (
    UnifiedTaskScheduler, TaskPriority, TaskType, TaskStatus, Task
)
from services.scan.unified_scan_engine import ScanResult

logger = logging.getLogger(__name__)


class EnhancedAsyncScanService:
    """
    增强异步扫描服务
    
    基于统一扫描引擎和任务调度框架的高级服务，支持扫描+元数据的组合任务。
    """
    
    def __init__(self):
        self.task_scheduler: Optional[UnifiedTaskScheduler] = None
        self._initialized = False
    
    async def initialize(self):
        """初始化服务"""
        if self._initialized:
            return
        
        try:
            # 获取任务调度器
            from services.task import get_unified_task_scheduler
            self.task_scheduler = await get_unified_task_scheduler()
            
            self._initialized = True
            logger.info("增强异步扫描服务初始化完成")
            
        except Exception as e:
            logger.error(f"初始化增强异步扫描服务失败: {e}")
            raise
    
    async def start_async_scan(
        self,
        storage_id: int,
        scan_path: str = "/",
        recursive: bool = True,
        max_depth: int = 10,
        enable_metadata_enrichment: bool = False,
        enable_delete_sync: bool = True,
        user_id: int = 1,
        priority: str = "normal",
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        启动异步扫描任务
        
        Args:
            storage_id: 存储配置ID
            scan_path: 扫描路径
            recursive: 是否递归扫描
            max_depth: 最大递归深度
            enable_metadata_enrichment: 是否启用元数据丰富
            user_id: 用户ID
            priority: 任务优先级 (urgent, high, normal, low)
            batch_size: 批量处理大小
            enable_delete_sync: 是否启用删除同步
        Returns:
            任务信息
        """
        await self.initialize()
        
        try:
            # 转换优先级
            priority_map = {    
                "urgent": TaskPriority.URGENT,
                "high": TaskPriority.HIGH,
                "normal": TaskPriority.NORMAL,
                "low": TaskPriority.LOW
            }
            task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
            
            logger.info(f"启动异步扫描: storage_id={storage_id}, path={scan_path}, metadata={enable_metadata_enrichment}")
            
            # 创建扫描任务
            task_id = await self.task_scheduler.create_scan_task(
                storage_id=storage_id,
                scan_path=scan_path,
                recursive=recursive,
                max_depth=max_depth,
                enable_metadata_enrichment=enable_metadata_enrichment,
                enable_delete_sync=enable_delete_sync,
                user_id=user_id,
                priority=task_priority,
                batch_size=batch_size
            )
            
            # 返回任务信息
            return {
                "task_id": task_id,
                "status": "created",
                "message": "扫描任务已创建并加入队列",
                "created_at": datetime.now().isoformat(),
                "estimated_duration": self._estimate_scan_duration(storage_id, scan_path, recursive)
            }
            
        except Exception as e:
            logger.error(f"启动异步扫描失败: {e}")
            raise
    
    async def start_metadata_enrichment(
        self,
        storage_id: int,
        file_ids: List[int],
        user_id: int = 1,
        language: str = "zh-CN",
        priority: str = "normal",
        batch_size: int = 20
    ) -> Dict[str, Any]:
        """
        启动异步元数据丰富任务
        
        Args:
            storage_id: 存储配置ID
            file_ids: 文件ID列表
            user_id: 用户ID
            language: 语言
            priority: 任务优先级
            batch_size: 每批处理的文件数
            
        Returns:
            任务信息
        """
        await self.initialize()
        
        try:
            if not file_ids:
                return {
                    "task_ids": [],
                    "status": "skipped",
                    "message": "没有文件需要处理"
                }
            
            # 转换优先级
            priority_map = {
                "urgent": TaskPriority.URGENT,
                "high": TaskPriority.HIGH,
                "normal": TaskPriority.NORMAL,
                "low": TaskPriority.LOW
            }
            task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
            
            logger.info(f"启动异步元数据丰富: storage_id={storage_id}, files={len(file_ids)}")
            
            # 创建元数据任务
            task_ids = await self.task_scheduler.create_metadata_task(
                storage_id=storage_id,
                file_ids=file_ids,
                user_id=user_id,
                language=language,
                priority=task_priority,
                batch_size=batch_size
            )
            
            return {
                "task_ids": task_ids,
                "status": "created",
                "message": f"元数据丰富任务已创建，共{len(task_ids)}个批次",
                "created_at": datetime.now().isoformat(),
                "estimated_duration": self._estimate_metadata_duration(len(file_ids))
            }
            
        except Exception as e:
            logger.error(f"启动异步元数据丰富失败: {e}")
            raise
    
    async def get_task_status(self, task_id: str, user_id: int) -> Optional[Dict[str, Any]]:
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
            status_info = await self.task_scheduler.get_task_status(task_id, user_id)
            
            if not status_info:
                return None
            
            # 添加额外的状态信息
            status_info["service"] = "enhanced_async_scan"
            status_info["progress_percentage"] = self._calculate_progress_percentage(status_info)
            
            return status_info
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None
    
    async def get_user_tasks(
        self,
        user_id: int,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取用户任务列表
        
        Args:
            user_id: 用户ID
            task_type: 任务类型筛选 (scan, metadata, combined)
            status: 状态筛选 (pending, running, completed, failed, cancelled)
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            任务列表信息
        """
        await self.initialize()
        
        try:
            # 转换任务类型
            task_type_enum = None
            if task_type:
                type_map = {
                    "scan": TaskType.SCAN,
                    "metadata": TaskType.METADATA_FETCH,
                    "combined": TaskType.COMBINED_SCAN
                }
                task_type_enum = type_map.get(task_type.lower())
            
            # 转换状态
            status_enum = None
            if status:
                status_map = {
                    "pending": TaskStatus.PENDING,
                    "running": TaskStatus.RUNNING,
                    "completed": TaskStatus.COMPLETED,
                    "failed": TaskStatus.FAILED,
                    "cancelled": TaskStatus.CANCELLED
                }
                status_enum = status_map.get(status.lower())
            
            # 获取任务列表
            result = await self.task_scheduler.get_user_tasks(
                user_id=user_id,
                task_type=task_type_enum,
                status=status_enum,
                limit=limit,
                offset=offset
            )
            
            # 添加服务标识
            result["service"] = "enhanced_async_scan"
            
            return result
            
        except Exception as e:
            logger.error(f"获取用户任务列表失败: {e}")
            return {
                "tasks": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False,
                "error": str(e)
            }
    
    async def cancel_task(self, task_id: str, user_id: int) -> Dict[str, Any]:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            user_id: 用户ID
            
        Returns:
            取消结果
        """
        await self.initialize()
        
        try:
            success = await self.task_scheduler.cancel_task(task_id, user_id)
            
            if success:
                return {
                    "success": True,
                    "message": "任务取消成功",
                    "task_id": task_id
                }
            else:
                return {
                    "success": False,
                    "message": "任务取消失败或任务不存在",
                    "task_id": task_id
                }
                
        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return {
                "success": False,
                "message": f"取消任务失败: {str(e)}",
                "task_id": task_id
            }
    
    async def get_system_health(self) -> Dict[str, Any]:
        """
        获取系统健康状态
        
        Returns:
            系统健康状态信息
        """
        await self.initialize()
        
        try:
            # 获取插件健康状态
            plugin_health = self.task_scheduler.get_plugin_health_status()
            
            # 构建系统健康信息
            health_info = {
                "service": "enhanced_async_scan",
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "task_scheduler": {
                        "status": "operational" if self.task_scheduler else "error",
                        "initialized": self._initialized
                    },
                    "plugins": plugin_health
                }
            }
            
            return health_info
            
        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {
                "service": "enhanced_async_scan",
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def _estimate_scan_duration(self, storage_id: int, scan_path: str, recursive: bool) -> int:
        """估算扫描耗时（秒）"""
        # 基于存储类型和路径的简单估算
        # 实际应用中可以根据历史数据优化
        base_time = 30  # 基础30秒
        
        if recursive:
            base_time *= 3  # 递归扫描增加3倍时间
        
        # 根据路径深度调整
        path_depth = scan_path.count("/")
        if path_depth > 3:
            base_time += path_depth * 10
        
        return min(base_time, 3600)  # 最多1小时
    
    def _estimate_metadata_duration(self, file_count: int) -> int:
        """估算元数据丰富耗时（秒）"""
        # 基于文件数量的简单估算
        # 考虑API限流（10次/秒）和批量处理
        base_time_per_file = 2  # 每个文件2秒（包含API调用）
        batch_overhead = 10  # 每批次额外10秒
        
        batch_size = 20
        batch_count = (file_count + batch_size - 1) // batch_size
        
        total_time = (file_count * base_time_per_file) + (batch_count * batch_overhead)
        
        return min(total_time, 7200)  # 最多2小时
    
    def _calculate_progress_percentage(self, status_info: Dict) -> int:
        """计算进度百分比"""
        try:
            status = status_info.get("status", "unknown")
            
            if status == "completed":
                return 100
            elif status == "pending":
                return 0
            elif status == "running":
                # 基于任务类型的估算进度
                task_type = status_info.get("task_type", "")
                
                if task_type == "scan":
                    return 50  # 扫描任务估算50%
                elif task_type == "metadata_fetch":
                    return 75  # 元数据任务估算75%
                elif task_type == "combined_scan":
                    return 30  # 组合任务估算30%（扫描阶段）
                else:
                    return 25  # 默认25%
            else:
                return 0
                
        except Exception:
            return 0


# 创建全局服务实例
enhanced_async_scan_service = EnhancedAsyncScanService()


async def get_enhanced_async_scan_service() -> EnhancedAsyncScanService:
    """获取增强异步扫描服务实例"""
    await enhanced_async_scan_service.initialize()
    return enhanced_async_scan_service