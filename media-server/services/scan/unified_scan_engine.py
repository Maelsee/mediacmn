"""
统一扫描引擎 - 高效异步扫描与刮削架构的核心组件

功能特点：
- 统一的基础扫描逻辑，支持多种存储后端
- 插件化扩展能力，支持扫描处理器链
- 异步执行，支持批量处理
- 与任务队列解耦，可独立使用
- 统一的错误处理和重试机制

架构设计：
- 引擎核心：负责文件发现、分类、存储
- 处理器链：插件化的扫描后处理
- 存储抽象：支持本地、WebDAV、S3等多种存储
- 配置中心：统一的扫描配置管理
"""


import asyncio
import traceback
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, AsyncGenerator, Any, Union, Awaitable
from pydantic import BaseModel, Field 
from dataclasses import dataclass, field

from services.storage.storage_service import storage_service
from services.storage.storage_client import StorageClient, StorageEntry
from services.scan.file_asset_repository import file_asset_repo

logger = logging.getLogger(__name__)

class ScanResult(BaseModel):
    """扫描结果模型"""
    total_files: int = 0
    media_files: int = 0
    new_files: int = 0
    updated_files: int = 0
    errors: int = 0
    duration: float = 0.0
    # 路径记录
    scanned_paths: List[str] = Field(default_factory=list)
    encountered_media_paths: List[str] = Field(default_factory=list)
    # ID 与 详情记录
    new_file_ids: List[int] = Field(default_factory=list)
    to_delete_ids: List[int] = Field(default_factory=list)
    error_details: List[Dict[str, Any]] = Field(default_factory=list)

class FileAssetProcessor():
    """文件资产处理器 - 核心处理器"""

    def __init__(self) -> None:
        # 直接获取单例引用
        self.repo = file_asset_repo
        self.supported_media_extensions = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            # '.srt', '.ass', '.ssa', '.vtt', '.sub'
        }
    
    def _is_media_file(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.supported_media_extensions

    async def process_batch(self, file_entries: List[StorageEntry], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """优化后的批量入库逻辑 (UPSERT 模式)"""
        results: List[Dict[str, Any]] = []
        storage_id: int = context.get("storage_id", 0)
        user_id: int = context.get("user_id", 1)
        repo =self.repo


        # 1. 预过滤媒体文件
        media_entries = [e for e in file_entries if not e.is_dir and self._is_media_file(e.path)]
        if not media_entries:
            return results

        try:
            paths: List[str] = [e.path for e in media_entries]
            # 2. 获取快照
            existing_map = await self.repo.find_existing_files_bulk(user_id, storage_id, paths)
            
            to_upsert: List[StorageEntry] = []
            
            for entry in media_entries:
                existing = existing_map.get(entry.path)
                if not existing:
                    to_upsert.append(entry)
                    results.append({"status": "new", "is_media": True, "path": entry.path})
                else:
                    changed = (entry.size is not None and existing.size != entry.size) or \
                              (entry.etag is not None and existing.etag != entry.etag)
                    
                    if changed:
                        to_upsert.append(entry)
                        results.append({"status": "updated", "is_media": True, "file_id": existing.id, "path": entry.path})
                    else:
                        results.append({"status": "unchanged", "is_media": True, "file_id": existing.id})

            # 3. 执行 UPSERT 并回填 ID
            if to_upsert:
                path_to_id: Dict[str, int] = await self.repo.bulk_upsert_file_records(storage_id, to_upsert, user_id)
                for res in results:
                    if "file_id" not in res and res.get("path") in path_to_id:
                        res["file_id"] = path_to_id[res["path"]]

        except Exception as e:
            logger.error(f"Batch processing error: {e}\n{traceback.format_exc()}")
            for entry in media_entries:
                results.append({"status": "error", "path": entry.path, "error": str(e), "is_media": True})
        return results

# class UnifiedScanEngine:
#     """统一扫描引擎 - 负责调度扫描与处理器"""

#     def __init__(self) -> None:
#         self.storage_service = storage_service
#         self.processor = FileAssetProcessor()
#         self.repo = file_asset_repo

#     async def scan_storage(self, storage_id: int, scan_path: str = "/", **kwargs: Any) -> ScanResult:
#         """核心扫描入口"""
#         recursive: bool = kwargs.get('recursive', True)
#         max_depth: int = kwargs.get('max_depth', 10)
#         user_id: int = kwargs.get('user_id', 1)
#         batch_size: int = kwargs.get('batch_size', 100)
#         progress_cb: Optional[Callable[[int, int], Union[None, Awaitable[None]]]] = kwargs.get('progress_cb')   
#         start_time = datetime.now()
#         result = ScanResult()
#         seen_paths: Set[str] = set()
#         media_paths: Set[str] = set()
#         # 获取数据库现有快照用于后续差集计算
#         db_files_snapshot: Dict[str, int] = await self.repo.get_all_paths_in_directory(user_id, storage_id, scan_path)
#         storage_client = None  # 在此处先初始化为 None
#         try:
#             storage_client = await self.storage_service.get_client(storage_id)
#             if not storage_client or not await storage_client.connect():
#                 logger.error(f"Storage client connection failed: {storage_id}")
#                 raise ConnectionError(f"存储客户端连接失败：{storage_id}")

            # async for batch in self._scan_in_batches(storage_client, scan_path, recursive, max_depth, batch_size):
                
            #     batch_results = await self.processor.process_batch(batch, {
            #         "storage_id": storage_id,
            #         "user_id": user_id
            #     })

#                 # 汇总统计
#                 result.total_files += len(batch)
#                 for entry in batch:
#                     seen_paths.add(entry.path)
#                     if not entry.is_dir and self.processor._is_media_file(entry.path):
#                         media_paths.add(entry.path)

                
#                 for r in batch_results:
#                     status = r.get("status")
#                     if status == "new":
#                         result.new_files += 1
#                         if "file_id" in r: result.new_file_ids.append(r["file_id"])
#                     elif status == "updated":
#                         result.updated_files += 1
#                     elif status == "error":
#                         result.errors += 1
#                         result.error_details.append(r)
                
#                 result.media_files = len(media_paths)
#                 # 回调
#                 if progress_cb:
#                     try:
#                         res = progress_cb(result.total_files, result.media_files)
#                         if asyncio.iscoroutine(res): await res
#                     except Exception as e:
#                         logger.warning(f"Progress callback failed: {e}")

#             # 计算并记录待删除 ID
#             for path, file_id in db_files_snapshot.items():
#                 if path not in seen_paths:
#                     result.to_delete_ids.append(file_id)

#             result.scanned_paths = list(seen_paths)
#             result.encountered_media_paths = list(media_paths)
            
#         except Exception as e:
#             logger.error(f"Scan interrupted: {e}")
#             result.error_details.append({"path": scan_path, "error": str(e), "trace": traceback.format_exc()})
#             result.errors += 1
#         finally:
#             # if storage_client:
#             #     await storage_client.disconnect()
#             result.duration = (datetime.now() - start_time).total_seconds()

#         logger.info(f"文件扫描完成，耗时 {result.duration}s")
#         return result

#     async def _scan_in_batches(self, client: StorageClient, path: str, recursive: bool, max_depth: int, size: int) -> AsyncGenerator[List[StorageEntry], None]:
#         """分批产生文件列表"""
#         current_batch: List[StorageEntry] = []
#         async for entry in self._recursive_walk(client, path, recursive, max_depth, 0):
#             current_batch.append(entry)
#             if len(current_batch) >= size:
#                 yield current_batch
#                 current_batch = []
#         if current_batch:
#             yield current_batch

#     async def _recursive_walk(self, client: StorageClient, path: str, recursive: bool, max_depth: int, depth: int) -> AsyncGenerator[StorageEntry, None]:
#         """递归遍历存储"""
#         if depth >= max_depth:
#             return

#         try:
#             entries: List[StorageEntry] = await client.list_dir(path)
#             for entry in entries:
#                 if not entry.is_dir:
#                     yield entry
#                 elif recursive:
#                     async for sub in self._recursive_walk(client, entry.path, recursive, max_depth, depth + 1):
#                         yield sub
#         except Exception as e:
#             logger.error(f"List dir failed {path}: {e}")

class UnifiedScanEngine:
    """统一扫描引擎 - 采用并发小分队模式"""

    def __init__(self) -> None:
        self.storage_service = storage_service
        self.processor = FileAssetProcessor()
        self.repo = file_asset_repo
        # 每个扫描任务分配的工作协程数量
        self.max_workers = 10 

    async def scan_storage(self, storage_id: int, scan_path: str = "/", **kwargs: Any) -> ScanResult:
        """核心扫描入口 - 并发增强版"""
        recursive: bool = kwargs.get('recursive', True)
        max_depth: int = kwargs.get('max_depth', 10)
        user_id: int = kwargs.get('user_id', 1)
        batch_size: int = kwargs.get('batch_size', 100)
        progress_cb: Optional[Callable[[int, int], Union[None, Awaitable[None]]]] = kwargs.get('progress_cb')
        
        start_time = datetime.now()
        result = ScanResult()
        seen_paths: Set[str] = set()
        media_paths: Set[str] = set()
        
        # 1. 获取数据库快照
        db_files_snapshot: Dict[str, int] = await self.repo.get_all_paths_in_directory(user_id, storage_id, scan_path)
        
        storage_client = None
        # 2. 获取客户端实例 (此时只是创建了 Python 对象，还没发起网络连接)
        raw_client = await self.storage_service.get_client(storage_id)
        try:
            # 3. 使用异步上下文管理器
            # 这会自动触发 raw_client.connect()
            async with raw_client as storage_client:
                if not storage_client or not storage_client.is_alive():
                    raise ConnectionError(f"存储客户端连接失败：{storage_id}")
                
                # --- 核心扫描逻辑开始 ---
                # 2. 初始化队列
                # dir_queue 存放待扫描的目录路径和当前深度: (path, current_depth)
                dir_queue = asyncio.Queue()
                # file_buffer 存放扫描到的文件实体，供处理器消费
                file_buffer = asyncio.Queue(maxsize=batch_size * 2)
                
                # 初始路径入队
                await dir_queue.put((scan_path, 0))

                # 3. 启动小分队 (Scanner Workers)
                # 动态调整 worker 数量，确保不浪费 client 的并发能力
                client_concurrency = storage_client.get_max_concurrency() 
                worker_count = client_concurrency if client_concurrency else self.max_workers
                logger.info(f"启动 {worker_count} 个扫描协程，存储客户端最大并发数: {client_concurrency}")
                
                scanner_tasks = [
                    asyncio.create_task(self._scanner_worker(storage_client, dir_queue, file_buffer, recursive, max_depth))
                    for _ in range(worker_count)
                ]

                # 4. 启动处理器 (Processor Worker)
                processor_task = asyncio.create_task(
                    self._processor_worker(file_buffer, result, seen_paths, media_paths, 
                                        storage_id, user_id, batch_size, progress_cb)
                )

                # 5. 等待扫描完成 (生产者全部结束)
                await dir_queue.join()
                
                # 停止 Scanner 协程
                for t in scanner_tasks:
                    t.cancel()
                
                # 给处理器发送结束信号
                await file_buffer.put(None)
                await processor_task
                # --- 核心扫描逻辑结束 ---
            # 当代码运行到这里（离开 async with），会自动触发 storage_client.disconnect()

            # 6. 计算待删除记录
            for path, file_id in db_files_snapshot.items():
                if path not in seen_paths:
                    result.to_delete_ids.append(file_id)

            result.scanned_paths = list(seen_paths)
            result.encountered_media_paths = list(media_paths)

            # # 7. 执行智能清理
            # if result.to_delete_ids:
            #     cleanup_stats = await self.repo.delete_files_by_ids(result.to_delete_ids, user_id)
            #     logger.info(f"清理完成，删除文件数: {cleanup_stats.get('deleted_assets', 0)}，清理孤立核心数: {cleanup_stats.get('cleaned_cores', 0)}")
            #     # result.deleted_files = cleanup_stats.get("deleted_assets", 0)
            #     # result.cleaned_cores = cleanup_stats.get("cleaned_cores", 0)

        except Exception as e:
            logger.error(f"Scan interrupted: {e}\n{traceback.format_exc()}")
            result.error_details.append({"path": scan_path, "error": str(e)})
            result.errors += 1
        finally:
            
            result.duration = (datetime.now() - start_time).total_seconds()

        logger.info(f"并发扫描完成，总计 {result.total_files} 文件，耗时 {result.duration}s")
        return result

    async def _scanner_worker(self, client: StorageClient, 
                              in_q: asyncio.Queue, 
                              out_q: asyncio.Queue, 
                              recursive: bool, 
                              max_depth: int):
        """扫描协程：负责 IO 密集型操作"""
        while True:
            try:
                current_path, depth = await in_q.get()
                
                if depth >= max_depth:
                    in_q.task_done()
                    continue

                entries: List[StorageEntry] = await client.list_dir(current_path)
                
                for entry in entries:
                    if entry.is_dir:
                        if recursive:
                            # 发现目录，丢回目录队列实现齐头并进
                            await in_q.put((entry.path, depth + 1))
                    else:
                        # 发现文件，塞入缓存给处理器
                        await out_q.put(entry)
                
                in_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scanner worker error at {current_path}: {e}")
                in_q.task_done()

    async def _processor_worker(self, 
                                in_q: asyncio.Queue, 
                                result: ScanResult, 
                                seen_paths: Set[str], 
                                media_paths: Set[str],
                                storage_id: int, 
                                user_id: int, 
                                batch_size: int,
                                progress_cb: Optional[Callable]):
        """处理协程：负责逻辑汇总、攒批入库、进度回调"""
        batch: List[StorageEntry] = []

        async def flush():
            nonlocal batch
            if not batch: return
            
            # 批量处理
            batch_results = await self.processor.process_batch(batch, {
                "storage_id": storage_id,
                "user_id": user_id
            })

            # 统计与记录
            result.total_files += len(batch)
            for entry in batch:
                seen_paths.add(entry.path)
                if not entry.is_dir and self.processor._is_media_file(entry.path):
                    media_paths.add(entry.path)

            for r in batch_results:
                status = r.get("status")
                if status == "new":
                    result.new_files += 1
                    if "file_id" in r: result.new_file_ids.append(r["file_id"])
                elif status == "updated":
                    result.updated_files += 1
                elif status == "error":
                    result.errors += 1
                    result.error_details.append(r)
            
            result.media_files = len(media_paths)
            if progress_cb:
                try:
                    res = progress_cb(result.total_files, result.media_files)
                    if asyncio.iscoroutine(res): await res
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")
            
            batch.clear()

        while True:
            entry = await in_q.get()
            
            # 收到退出信号
            if entry is None:
                await flush()
                in_q.task_done()
                break
            
            batch.append(entry)
            if len(batch) >= batch_size:
                await flush()
            
            in_q.task_done()

# 单例模式
unified_scan_engine = UnifiedScanEngine()

async def get_unified_scan_engine() -> UnifiedScanEngine:
    return unified_scan_engine