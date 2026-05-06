"""任务消费者统一入口

此文件为 re-export facade，实际 Worker 实现分布在独立文件中：
- worker_scan.py      — scan 队列消费者
- worker_metadata.py  — metadata 队列消费者
- worker_persist.py   — persist / persist_batch 队列消费者
- worker_delete.py    — delete 队列消费者
- worker_localize.py  — localize 队列消费者

保持此文件以兼容 `dramatiq services.task.consumers` 启动命令和现有导入。
"""
from .worker_scan import scan_worker
from .worker_metadata import metadata_worker
from .worker_persist import persist_worker, persist_batch_worker
from .worker_delete import delete_worker
from .worker_localize import localize_worker

__all__ = [
    "scan_worker",
    "metadata_worker",
    "persist_worker",
    "persist_batch_worker",
    "delete_worker",
    "localize_worker",
]
