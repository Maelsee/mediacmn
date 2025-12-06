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
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum

from sqlmodel import select

from core.db import get_session as get_db_session
from models.media_models import MediaCore, FileAsset
from services.storage.storage_service import StorageService
from services.storage.storage_client import StorageClient, StorageEntry
from services.utils.filename_parser import FilenameParser, ParserMode, ParseInput
from services.scan.file_asset_repository import SqlFileAssetRepository

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """扫描结果数据类"""
    total_files: int = 0
    media_files: int = 0
    new_files: int = 0
    updated_files: int = 0
    errors: int = 0
    duration: float = 0.0
    scanned_paths: List[str] = field(default_factory=list)
    error_details: List[Dict] = field(default_factory=list)
    new_file_ids: List[int] = field(default_factory=list)
    encountered_media_paths: List[str] = field(default_factory=list)
    new_file_snapshots: Dict[int, Dict] = field(default_factory=dict)

"""
示例 ScanResult 实例
ScanResult(
    total_files=17,
    media_files=0,
    new_files=0,
    updated_files=0,
    errors=0,
    duration=0.406041,
    scanned_paths=[
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/西游记之大圣归来.Monkey.King.Hero.Is.Back.2015.2160p.WEB-DL.HEVC.60fps.AAC.fanart.jpg',
        '/dav/302/133quark302/test/fanart.jpg',
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/西游记之大圣归来.Monkey.King.Hero.Is.Back.2015.2160p.WEB-DL.HEVC.60fps.AAC.mp4',
        '/dav/302/133quark302/test/七月与安生/七月与安生 (2016) - 1080p.nfo',
        '/dav/302/133quark302/test/毕正明的证明.The.Return.of.The.Lame.Hero.2025.2160p.WEB-DL.H265.HDR.DDP5.1-PandaQT.nfo',
        '/dav/302/133quark302/test/七月与安生/七月与安生 (2016) - 1080p.poster.jpg',
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/fanart.jpg',
        '/dav/302/133quark302/test/毕正明的证明.The.Return.of.The.Lame.Hero.2025.2160p.WEB-DL.H265.HDR.DDP5.1-PandaQT.poster.jpg',
        '/dav/302/133quark302/test/毕正明的证明.The.Return.of.The.Lame.Hero.2025.2160p.WEB-DL.H265.HDR.DDP5.1-PandaQT.mkv',
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/西游记之大圣归来.Monkey.King.Hero.Is.Back.2015.2160p.WEB-DL.HEVC.60fps.AAC.nfo',
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/poster.jpg',
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/西游记之大圣归来.Monkey.King.Hero.Is.Back.2015.2160p.WEB-DL.HEVC.60fps.AAC.poster.jpg',
        '/dav/302/133quark302/test/长安的荔枝.The.Litchi.Road.S01.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV/The.Litchi.Road.S01E02.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV.mkv',
        '/dav/302/133quark302/test/七月与安生/七月与安生 (2016) - 1080p.mkv',
        '/dav/302/133quark302/test/poster.jpg',
        '/dav/302/133quark302/test/长安的荔枝.The.Litchi.Road.S01.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV/The.Litchi.Road.S01E01.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV.mkv',
        '/dav/302/133quark302/test/毕正明的证明.The.Return.of.The.Lame.Hero.2025.2160p.WEB-DL.H265.HDR.DDP5.1-PandaQT.fanart.jpg'
    ],
    error_details=None,
    new_file_ids=None,
    encountered_media_paths=[
        '/dav/302/133quark302/test/西游记之大圣归来 (2015) 4K 60帧/西游记之大圣归来.Monkey.King.Hero.Is.Back.2015.2160p.WEB-DL.HEVC.60fps.AAC.mp4',
        '/dav/302/133quark302/test/毕正明的证明.The.Return.of.The.Lame.Hero.2025.2160p.WEB-DL.H265.HDR.DDP5.1-PandaQT.mkv',
        '/dav/302/133quark302/test/长安的荔枝.The.Litchi.Road.S01.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV/The.Litchi.Road.S01E02.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV.mkv',
        '/dav/302/133quark302/test/七月与安生/七月与安生 (2016) - 1080p.mkv',
        '/dav/302/133quark302/test/长安的荔枝.The.Litchi.Road.S01.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV/The.Litchi.Road.S01E01.2025.2160p.IQ.WEB-DL.H265.AAC-BlackTV.mkv'
    ],
    new_file_snapshots=None
)

"""


class ScanProcessor:
    """扫描处理器基类"""
    
    async def process_file(self, file_entry: StorageEntry, context: Dict) -> Optional[Dict]:
        """处理单个文件
        
        Args:
            file_entry: 存储条目，包含 `path/name/size/etag/is_dir` 等基本属性。
            context: 扫描上下文字典，通常包含 `storage_id/user_id/storage_client/file_asset_repo` 等。
        
        Returns:
            可选的处理结果字典。约定字段：
            - `status`: 处理状态，例如 `new/updated/error`。
            - `is_media`: 是否为媒体文件。
            - `file_id`: 数据库中的文件记录ID（如适用）。
            - `file_info`: 解析到的轻量元信息快照（如标题/年/季/集/分辨率）。
        
        Raises:
            NotImplementedError: 基类不提供实现，子类必须重写。
        """
        raise NotImplementedError
    
    async def process_batch(self, file_entries: List[StorageEntry], context: Dict) -> List[Dict]:
        """批量处理文件
        
        默认兜底实现：顺序逐条调用 `process_file` 并聚合结果，保证只实现了单文件处理的处理器也能工作。
        若子类具备真正的批量能力（如数据库批量查询/批量提交、跨文件聚合），应重写本方法以提升性能。
        
        Args:
            file_entries: 同一批次的存储条目列表。
            context: 扫描上下文，参见 `process_file`。
        
        Returns:
            每个文件对应的处理结果列表。无结果的文件不会出现在返回值中。
        """
        results = []
        for entry in file_entries:
            result = await self.process_file(entry, context)
            if result:
                results.append(result)
        return results


class FileAssetProcessor(ScanProcessor):
    """
    文件资产处理器 - 核心处理器
    
    在处理文件资产时，主要负责：
    - 识别媒体文件（根据扩展名）
    - 解析文件名提取元数据
    - 创建或更新文件资产记录
    
    """

    def __init__(self):
        """初始化处理器

        - 创建文件名解析器 `FilenameParser`，用于快速提取标题/年/季/集/分辨率等轻量信息。
        - 维护受支持的媒体扩展名集合，以便快速过滤非媒体文件。
        """
        self.parser = FilenameParser()
        self.supported_media_extensions = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            # '.mp3', '.flac', '.wav', '.aac', '.ogg', '.wma', '.m4a',
            # '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg',
            # '.srt', '.ass', '.ssa', '.vtt', '.sub'
        }
    
    def _is_media_file(self, file_path: str) -> bool:
        """检查是否为媒体文件

        通过后缀名匹配受支持的扩展名集合，判断给定路径是否为媒体文件。

        Args:
            file_path: 文件完整路径或名称。

        Returns:
            True 表示为受支持的媒体文件，False 表示非媒体或未知类型。
        """
        ext = Path(file_path).suffix.lower()
        return ext in self.supported_media_extensions
    
    def _light_parse(self, entry: StorageEntry) -> Dict:
        """轻量级文件名解析

        使用 `FilenameParser` 的轻量模式，优先提取常见元信息（标题/年/季/集/分辨率）。
        当轻量模式无法提取到季集或分辨率等关键点时，回退到更保守的解析策略（例如依据文件名 stem）。

        Args:
            entry: 存储条目，至少包含 `name` 与 `path`。

        Returns:
            结构化的轻量信息字典：`{"title","year","season","episode","resolution","source"}`。
        """
        out = self.parser.parse(ParseInput(filename_raw=entry.name, parent_hint=str(Path(entry.path).parent.name)), ParserMode.LIGHT)
        title = out.title or Path(entry.name).stem
        year = out.year or None
        season = out.season_number or None
        episode = out.episode_number or None
        resolution = None
        if out.resolution_tags and len(out.resolution_tags) > 0:
            resolution = out.resolution_tags[0]
        if not any([year, season, episode, resolution]):
            return self._parse_filename(entry.name)
        return {
            "title": title,
            "year": year,
            "season": season,
            "episode": episode,
            "resolution": resolution,
            "source": None
        }
    
    async def _calculate_file_hash(self, storage_client: StorageClient, file_path: str) -> Optional[str]:
        """计算文件哈希

        - 小文件（<100MB）：下载全量内容并计算 MD5。
        - 大文件（>=100MB）：优先使用分段策略（前10MB + 后10MB），在存储支持 Range 时并行拉取末段数据以提升准确性与性能。

        Args:
            storage_client: 存储客户端，用于 `stat/info/download_iter`。
            file_path: 文件路径。

        Returns:
            十六进制 MD5 字符串；若无法计算则返回 None。

        Notes:
            - 网络与存储特性不同，可能导致 Range 不可用；此时退化为仅前10MB。
            - 该方法为可选优化，实际流程中可能关闭以避免带宽与时间消耗。
        """
        try:
            # 对于小文件计算完整哈希，大文件计算部分哈希
            import hashlib
            
            # 先获取文件大小
            stat = await storage_client.stat(file_path)
            if not stat or not stat.size:
                return None
            
            # 小于100MB的文件计算完整哈希
            if stat.size < 100 * 1024 * 1024:
                content = b""
                async for chunk in storage_client.download_iter(file_path, chunk_size=64*1024):
                    content += chunk
                return hashlib.md5(content).hexdigest()
            else:
                # 大文件计算前10MB + 后10MB的哈希
                content = b""
                # 前10MB
                async for chunk in storage_client.download_iter(file_path, chunk_size=64*1024):
                    content += chunk
                    if len(content) >= 10 * 1024 * 1024:
                        break
                
                # 后10MB（如果可能）
                try:
                    info = await storage_client.info("/")
                    if info.supports_range and stat.size > 20 * 1024 * 1024:
                        offset = max(0, stat.size - 10 * 1024 * 1024)
                        end_content = b""
                        async for chunk in storage_client.download_iter(file_path, chunk_size=64*1024, offset=offset):
                            end_content += chunk
                            if len(end_content) >= 10 * 1024 * 1024:
                                break
                        content += end_content
                except Exception:
                    # 无法获取info或不支持range时，降级为仅前10MB
                    pass
                
                return hashlib.md5(content).hexdigest()
                
        except Exception as e:
            logger.warning(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    async def process_file(self, file_entry: StorageEntry, context: Dict) -> Optional[Dict]:
        """处理单个文件（非批量路径）

        步骤：
        1) 过滤非媒体文件。
        2) 轻量解析文件名，产出 `file_info`。
        3) 通过仓储接口查询是否存在记录；存在则按 `size/etag` 判变更并更新；不存在则创建新记录。

        Args:
            file_entry: 存储条目对象，包含路径、大小、etag 等。
            context: 上下文（`storage_id/user_id/storage_client/file_asset_repo`）。

        Returns:
            `{"status","is_media","file_id","file_info"}` 或错误条目；非媒体返回 None。
        """
        
        try:
            # 检查是否为媒体文件
            if not self._is_media_file(file_entry.path):
                return None
            
            storage_id = context.get("storage_id")
            user_id = context.get("user_id", 1)
            
            # 解析文件信息
            file_info = self._light_parse(file_entry)
            
            # 暂不使用文件哈希以提升性能
            
            # 通过仓储接口检查与持久化
            repo = context.get("file_asset_repo")
            existing_file = None
            if repo:
                existing_file = repo.find_existing_file(user_id, storage_id, file_entry.path)
            if existing_file:
                updated = repo.update_file_info(existing_file, file_entry)
                if updated:
                    return {
                        "status": "updated",
                        "is_media": True,
                        "file_id": existing_file.id,
                        "file_info": file_info
                    }
                return None
            else:
                new_file = None
                if repo:
                    new_file = repo.create_file_record(storage_id, file_entry, file_info, user_id)
                if new_file:
                    return {
                        "status": "new",
                        "is_media": True,
                        "file_id": new_file.id,
                        "file_info": file_info
                    }
                else:
                    logger.error(f"创建文件记录失败: {file_entry.path}")
                    return {
                        "status": "error",
                        "is_media": True,
                        "path": file_entry.path,
                        "error": "create_file_record_failed",
                        "file_info": file_info
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"处理文件失败 {file_entry.path}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "path": file_entry.path
            }

    async def process_batch(self, file_entries: List[StorageEntry], context: Dict) -> List[Dict]:
        """批量处理文件（真正的数据库批量路径）

        - 过滤媒体文件，轻量解析并构建 `file_info_map`。
        - 一次查询拿到既有记录映射 `existing_map`。
        - 计算需更新集合（比较 `size/etag`），统一提交 `bulk_update_file_info`。
        - 对新增集合统一提交 `bulk_create_file_records`。
        - 统一返回与单文件处理一致的结果结构，便于引擎统计与链路复用。

        Args:
            file_entries: 同批次条目。
            context: 上下文（含仓储）。

        Returns:
            聚合后的处理结果列表。
        """
        results: List[Dict] = []
        try:
            storage_id = context.get("storage_id")
            user_id = context.get("user_id", 1)
            repo: SqlFileAssetRepository = context.get("file_asset_repo") or SqlFileAssetRepository()

            media_entries: List[StorageEntry] = [e for e in file_entries if (not e.is_dir and self._is_media_file(e.path))]
            if not media_entries:
                return results
            
            # # 批量解析文件信息
            file_info_map: Dict[str, Dict] = {}
            for e in media_entries:
                file_info_map[e.path] = self._light_parse(e)
            
            # 构建路径到存储条目的映射  
            entry_by_path: Dict[str, StorageEntry] = {e.path: e for e in media_entries}

            paths: List[str] = list(entry_by_path.keys())
            # 批量查询既有记录,返回的都是存在的记录
            existing_map: Dict[str, FileAsset] = repo.find_existing_files_bulk(user_id, storage_id, paths)
            to_create: list[StorageEntry] = []
            to_update_records: list[FileAsset] = []

            # to_update_paths: set[str] = set(existing_map.keys())  # 存在的记录路径集合
            # to_create_paths: set[str] = set(paths) - set(existing_map.keys())  # 不存在的记录路径集合
            # to_update_records: list[FileAsset] = list(existing_map.values())  # 真正存储 FileAsset 对象的集合
            # to_create: list[StorageEntry] = list(entry_by_path[path] for path in to_create_paths)   # 从映射中提取 StorageEntry 对象
          
            for p, entry in entry_by_path.items():
                existing = existing_map.get(p)
                if existing is None:
                    to_create.append(entry)
                else:
                    changed = ((entry.size is not None and existing.size != entry.size) or
                               (entry.etag and existing.etag != entry.etag))
                    if changed:
                        if entry.size is not None and existing.size != entry.size:
                            existing.size = entry.size
                        if entry.etag and existing.etag != entry.etag:
                            existing.etag = entry.etag
                        to_update_records.append(existing)

            if to_update_records:
                updated_count = repo.bulk_update_file_info(to_update_records)
                if updated_count > 0:
                    for fr in to_update_records:
                        fi = file_info_map.get(fr.full_path)
                        results.append({
                            "status": "updated",
                            "is_media": True,
                            "file_id": fr.id,
                            "file_info": fi
                        })

            if to_create:
                created = repo.bulk_create_file_records(storage_id, to_create, file_info_map, user_id)
                for mf in created:
                    fi = file_info_map.get(mf.full_path)
                    results.append({
                        "status": "new",
                        "is_media": True,
                        "file_id": mf.id,
                        "file_info": fi
                    })

            return results
        except Exception as err:
            logger.error(f"批量处理文件失败: {err}")
            # 失败时为每个媒体条目记录错误，避免丢失上下文
            for entry in file_entries:
                if entry.is_dir or not self._is_media_file(entry.path):
                    continue
                results.append({
                    "status": "error",
                    "is_media": True,
                    "path": entry.path,
                    "error": str(err),
                    "file_info": None
                })
            return results


class UnifiedScanEngine:
    """统一扫描引擎"""
    
    def __init__(self, storage_service: Optional[StorageService] = None):
        """初始化引擎

        Args:
            storage_service: 可注入的存储服务实现；默认使用内置 `StorageService`。

        Notes:
            - 处理器列表在构造时通过 `_init_default_processors` 初始化。
        """
        self.storage_service = storage_service or StorageService()
        self.processors: List[ScanProcessor] = []
        self._init_default_processors()
    
    def _init_default_processors(self):
        """初始化默认处理器

        当前注册核心的 `FileAssetProcessor`，用于将扫描到的媒体文件入库或更新。
        可扩展：未来可在此注册更多处理器（如元数据抓取、封面下载、预转码等）。
        """
        # 核心文件资产处理器
        self.register_processor(FileAssetProcessor())
    
    def register_processor(self, processor: ScanProcessor):
        """注册扫描处理器

        Args:
            processor: 实现了 `ScanProcessor` 契约的处理器实例。

        Notes:
            - 处理器的调用由 `_process_batch` 统一调度，支持真实批处理与并发兜底。
        """
        self.processors.append(processor)
        logger.info(f"注册扫描处理器: {processor.__class__.__name__}")
    
    async def scan_storage(self, storage_id: int, scan_path: str = "/",
                          recursive: bool = True, max_depth: int = 10,
                          user_id: int = 1, batch_size: int = 100,
                          storage_client: Optional[StorageClient] = None,
                          file_asset_repo: Optional[SqlFileAssetRepository] = None,
                          progress_cb: Optional[Callable[[int, int], None]] = None) -> ScanResult:
        """扫描存储并批量入库

        流程：
        1) 获取/连接存储客户端。
        2) 递归/分层扫描，按 `batch_size` 产出批次（预取 `size/etag`）。
        3) 对每批调用 `_process_batch` 并收集结果，统一统计新增/更新/错误。
        4) 断开存储连接，返回整体扫描统计。

        Args:
            storage_id: 存储配置ID。
            scan_path: 起始扫描路径。
            recursive: 是否递归子目录。
            max_depth: 最大递归深度。
            user_id: 用户ID（多租户隔离）。
            batch_size: 每批大小，控制内存与并发。
            storage_client: 可注入的客户端（便于测试/复用）。
            file_asset_repo: 可注入的仓储实现。

        Returns:
            `ScanResult`，包含总耗时、总文件数、媒体文件数、新增/更新/错误计数与快照。

        Raises:
            Exception: 存储不可连接或扫描过程中发生不可恢复错误时。
        """
        start_time = datetime.now()
        result = ScanResult()
        seen_paths_set: Set[str] = set()
        encountered_media_set: Set[str] = set()
        supported_exts = FileAssetProcessor().supported_media_extensions
        
        try:
            # 获取或使用注入的存储客户端
            if not storage_client:
                storage_client = await self.storage_service.get_client(storage_id)
                if not storage_client:
                    raise Exception(f"存储配置 {storage_id} 不存在或无法连接")
            
            # 连接存储
            if not await storage_client.connect():
                raise Exception(f"无法连接到存储 {storage_id}")
            
            logger.info(f"开始扫描存储 {storage_id} 路径: {scan_path}")
            
            try:
                # 执行扫描
                async for batch in self._scan_directory_in_batches(
                    storage_client, scan_path, recursive, max_depth, batch_size
                ):
                    # 批量处理文件
                    batch_results = await self._process_batch(batch, {
                        "storage_id": storage_id,
                        "storage_client": storage_client,
                        "user_id": user_id,
                        "file_asset_repo": file_asset_repo or SqlFileAssetRepository()
                    })
                    
                    result.total_files += len(batch)
                    for br in batch_results:
                        for file_result in br:
                            if file_result.get("is_media"):
                                result.media_files += 1
                            status = file_result.get("status")
                            if status == "new":
                                result.new_files += 1
                                if "file_id" in file_result:
                                    result.new_file_ids.append(file_result["file_id"])
                                    fi = file_result.get("file_info")
                                    if fi:
                                        result.new_file_snapshots[file_result["file_id"]] = fi
                            elif status == "updated":
                                result.updated_files += 1
                            elif status == "error":
                                result.errors += 1
                                err_path = file_result.get("path")
                                err_msg = file_result.get("error")
                                if err_path or err_msg:
                                    result.error_details.append({
                                        "status": "error",
                                        "path": err_path,
                                        "error": err_msg
                                    })
                    
                    # 记录扫描路径
                    for entry in batch:
                        seen_paths_set.add(entry.path)
                        if not entry.is_dir:
                            ext = Path(entry.path).suffix.lower()
                            if ext in supported_exts:
                                encountered_media_set.add(entry.path)
                    try:
                        if progress_cb:
                            # 回调当前进度：已扫描条目数与遇到的媒体文件数
                            maybe = progress_cb(result.total_files, len(encountered_media_set))
                            import inspect
                            if inspect.iscoroutine(maybe):
                                await maybe
                    except Exception:
                        pass
                
                # 写入去重后的路径集合并计算耗时
                result.scanned_paths = list(seen_paths_set)
                result.encountered_media_paths = list(encountered_media_set)
                result.duration = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"扫描完成: {scan_path}, 统计: {result}")
                
            finally:
                # 断开存储连接
                try:
                    await storage_client.disconnect()
                except:
                    pass
            
            return result
            
        except Exception as e:
            logger.error(f"扫描失败: {scan_path}, 错误: {e}")
            result.errors += 1
            result.error_details.append({
                "path": scan_path,
                "error": str(e)
            })
            return result
    
    async def _scan_directory_in_batches(self, storage_client: StorageClient, 
                                      path: str, recursive: bool, max_depth: int,
                                      batch_size: int) -> AsyncGenerator[List[StorageEntry], None]:
        """批量扫描目录
        
        将递归扫描结果按 `batch_size` 分批返回，避免一次性加载过多文件到内存；在 `yield` 之前预取缺失的 `size/etag`，降低处理器阶段的 I/O 开销。
        
        Args:
            storage_client: 存储客户端。
            path: 起始扫描路径。
            recursive: 是否递归子目录。
            max_depth: 最大递归深度。
            batch_size: 每批返回的条目数量。
        
        Yields:
            每批 `List[StorageEntry]`。
        """
        current_batch: List[StorageEntry] = []
        async for entry in self._scan_directory_recursive(storage_client, path, recursive, max_depth, 0):
            current_batch.append(entry)
            if len(current_batch) >= batch_size:
                # 在yield前预取文件基本信息以优化后续处理器
                try:
                    await self._prefetch_basic_stats(storage_client, current_batch)
                except Exception:
                    pass
                yield current_batch
                current_batch = []
        if current_batch:
            try:
                await self._prefetch_basic_stats(storage_client, current_batch)
            except Exception:
                pass
            yield current_batch
    
    async def _scan_directory_recursive(self, storage_client: StorageClient,
                                       path: str, recursive: bool, max_depth: int,
                                       current_depth: int) -> AsyncGenerator[StorageEntry, None]:
        """递归扫描目录（深度优先）
        
        按深度优先策略遍历目录结构，在 `current_depth >= max_depth` 时终止递归。目录条目在递归时继续展开，文件条目直接产出。
        
        Args:
            storage_client: 存储客户端。
            path: 当前扫描路径。
            recursive: 是否递归子目录。
            max_depth: 最大递归深度。
            current_depth: 当前深度计数。
        
        Yields:
            每个文件或目录的 `StorageEntry`（目录仅在递归展开时产出其子条目）。
        """
        if current_depth >= max_depth:
            return
        
        try:
            logger.info(f"---目录 {path}，深度 {current_depth}---")
            entries = await storage_client.list_dir(path, depth=1)
            
            for entry in entries:
                if not entry.is_dir:
                    yield entry
                elif entry.is_dir and recursive:
                    async for sub_entry in self._scan_directory_recursive(
                        storage_client, entry.path, recursive, max_depth, current_depth + 1
                    ):
                        yield sub_entry
                        
        except Exception as e:
            logger.error(f"扫描目录失败 {path}: {e}")
            # 不中断扫描，只记录错误 - 不创建错误条目，只记录日志

    async def _prefetch_basic_stats(self, storage_client: StorageClient, entries: List[StorageEntry]) -> None:
        """预取基础文件属性

        并发拉取批次内条目的 `stat`，仅在缺失 `size/etag` 时执行，避免过度拉取。将获取到的属性填充回原始 `StorageEntry`，以便处理器阶段直接使用，减少重复 I/O。

        Args:
            storage_client: 存储客户端。
            entries: 批次条目列表。
        """
        tasks = []
        for e in entries:
            if e.is_dir:
                continue
            # 仅当必要时才stat，避免过度拉取
            need_stat = (e.size is None) or (e.etag is None)
            if need_stat:
                tasks.append(storage_client.stat(e.path))
        if not tasks:
            return
        stats = await asyncio.gather(*tasks, return_exceptions=True)
        i = 0
        for e in entries:
            if e.is_dir:
                continue
            need_stat = (e.size is None) or (e.etag is None)
            if not need_stat:
                continue
            s = stats[i] if i < len(stats) else None
            i += 1
            if isinstance(s, Exception) or s is None:
                continue
            try:
                if e.size is None:
                    e.size = getattr(s, 'size', e.size)
                if e.etag is None:
                    e.etag = getattr(s, 'etag', e.etag)
            except Exception:
                pass
    
    async def _process_batch(self, batch: List[StorageEntry], context: Dict) -> List[List[Dict]]:
        """批量处理文件（处理器并发 + 结果聚合）
        
        - 并发执行处理器：若处理器重写了 `process_batch`，走其批处理路径；否则并发逐条调用 `process_file` 并聚合。
        - 收集 `FileAssetProcessor` 的轻量解析快照，提供给后续链路。
        - 返回每个处理器的结果列表集合，以便上层统计。
        
        Args:
            batch: 批次条目列表。
            context: 扫描上下文。
        
        Returns:
            `List[List[Dict]]`：外层为处理器维度，内层为各处理器的处理结果列表。
        """
        async def _run_processor(processor: ScanProcessor) -> List[Dict]:
            try:
                if processor.__class__.process_batch is not ScanProcessor.process_batch:
                    return await processor.process_batch(batch, context)
                # 不支持批处理：并发逐条处理
                tasks = [processor.process_file(entry, context) for entry in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                out: List[Dict] = []
                for r in results:
                    if isinstance(r, Exception) or r is None:
                        continue
                    out.append(r)
                return out
            except Exception as e:
                logger.error(f"处理器 {processor.__class__.__name__} 处理失败: {e}")
                return []

        # 并发跑所有处理器
        proc_tasks = [_run_processor(p) for p in self.processors]
        all_results: List[List[Dict]] = await asyncio.gather(*proc_tasks)

        # 仅收集媒体条目的轻量解析快照（来自 FileAssetProcessor 的结果）
        # try:
        #     for idx, processor in enumerate(self.processors):
        #         if processor.__class__.__name__ == 'FileAssetProcessor':
        #             parse_snaps: List[Dict] = []
        #             for r in all_results[idx]:
        #                 if r.get('is_media') and r.get('file_info'):
        #                     parse_snaps.append(r['file_info'])
        #             context['parse_snapshots'] = parse_snaps
        #             break
        # except Exception:
        #     context['parse_snapshots'] = []

        return all_results


# 创建全局引擎实例
unified_scan_engine = UnifiedScanEngine()


async def get_unified_scan_engine() -> UnifiedScanEngine:
    """获取统一扫描引擎实例

    Returns:
        单例的 `UnifiedScanEngine`，便于在服务层或路由中复用。
    """
    return unified_scan_engine
