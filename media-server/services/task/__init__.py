"""
任务系统模块 - 统一的任务队列、调度和执行框架

该模块提供完整的任务生命周期管理：
- 任务队列服务 (task_queue_service): Redis-based分布式任务队列
- 任务调度器 (unified_task_scheduler): 任务调度和协调管理
- 任务执行器 (unified_task_executor): 任务执行引擎

主要功能：
- 支持多种任务类型：扫描、元数据获取、转码等
- 任务优先级管理和状态跟踪
- 失败任务重试机制
- 分布式任务处理
- 实时进度更新
"""

# 任务队列服务
from .task_queue_service import (
    TaskQueueService,
    Task,
    TaskType,
    TaskStatus,
    TaskPriority,
    TaskResult,
    get_task_queue_service
)

# 任务调度器
from .unified_task_scheduler import (
    UnifiedTaskScheduler,
    TaskCategory,
    get_unified_task_scheduler
)

# 任务执行器
from .unified_task_executor import (
    UnifiedTaskExecutor,
    get_task_executor_manager
)

__all__ = [
    # 任务队列
    'TaskQueueService',
    'Task',
    'TaskType',
    'TaskStatus',
    'TaskPriority',
    'TaskResult',
    'get_task_queue_service',
    
    # 任务调度
    'UnifiedTaskScheduler',
    'TaskCategory',
    'get_unified_task_scheduler',
    
    # 任务执行
    'UnifiedTaskExecutor',
    'get_task_executor_manager'
]