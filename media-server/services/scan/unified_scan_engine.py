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
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_session as get_db_session
from models.media_models import MediaCore, FileAsset
from models.storage_models import StorageConfig
from services.storage.storage_service import StorageService
from services.storage.storage_client import StorageClient, StorageEntry
from services.utils.filename_parser import FilenameParser, ParserMode, ParseInput

logger = logging.getLogger(__name__)


class ScanStatus(Enum):
    """扫描状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScanResult:
    """扫描结果数据类"""
    total_files: int = 0
    media_files: int = 0
    new_files: int = 0
    updated_files: int = 0
    errors: int = 0
    duration: float = 0.0
    scanned_paths: List[str] = None
    error_details: List[Dict] = None
    new_file_ids: List[int] = None
    encountered_media_paths: List[str] = None
    new_file_snapshots: Dict[int, Dict] = None
    
    def __post_init__(self):
        if self.scanned_paths is None:
            self.scanned_paths = []
        if self.error_details is None:
            self.error_details = []
        if self.new_file_ids is None:
            self.new_file_ids = []
        if self.encountered_media_paths is None:
            self.encountered_media_paths = []
        if self.new_file_snapshots is None:
            self.new_file_snapshots = {}


class ScanProcessor:
    """扫描处理器基类"""
    
    async def process_file(self, file_entry: StorageEntry, context: Dict) -> Optional[Dict]:
        """处理单个文件"""
        raise NotImplementedError
    
    async def process_batch(self, file_entries: List[StorageEntry], context: Dict) -> List[Dict]:
        """批量处理文件"""
        results = []
        for entry in file_entries:
            result = await self.process_file(entry, context)
            if result:
                results.append(result)
        return results


class FileAssetProcessor(ScanProcessor):
    """文件资产处理器 - 核心处理器"""
    """处理文件资产，包括创建、更新和元数据提取"""
    def __init__(self):
        self.parser = FilenameParser()
        self.supported_media_extensions = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            # '.mp3', '.flac', '.wav', '.aac', '.ogg', '.wma', '.m4a',
            # '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg',
            # '.srt', '.ass', '.ssa', '.vtt', '.sub'
        }
    
    def _is_media_file(self, file_path: str) -> bool:
        """检查是否为媒体文件"""
        ext = Path(file_path).suffix.lower()
        return ext in self.supported_media_extensions
    
    def _parse_filename(self, filename: str) -> Dict:
        
        """
        从文件名中提取标题、年份、季集、分辨率等元数据
        
        Args:
            filename: 文件名
            
        Returns:
            Dict: 包含提取的元数据字段
        """
        
        # 基础文件名解析
        title = Path(filename).stem # 去掉扩展名，movie.2021.mp4"，那么 Path(filename).stem返回 "movie.2021"
        year = None
        season = None
        episode = None
        resolution = None
        
        # 简单的正则表达式匹配
        import re
        
        # 匹配年份
        year_match = re.search(r'\b(19|20)\d{2}\b', filename)
        if year_match:
            year = int(year_match.group())
        
        # 匹配季集信息 (S01E01, 第1季第1集, 1x01等格式)
        season_episode_patterns = [
            r'[Ss](\d+)[Ee](\d+)',
            r'(\d+)x(\d+)',
            r'第(\d+)[季集].*第(\d+)[集话]',
        ]
        
        for pattern in season_episode_patterns:
            match = re.search(pattern, filename)
            if match:
                season = int(match.group(1))
                episode = int(match.group(2))
                break
        
        # 匹配分辨率
        resolution_patterns = ['1080p', '720p', '4K', '2160p', '480p']
        for res in resolution_patterns:
            if res.lower() in filename.lower():
                resolution = res
                break
        
        return {
            "title": title,
            "year": year,
            "season": season,
            "episode": episode,
            "resolution": resolution,
            "source": self._detect_source(filename)
        }

    def _light_parse(self, entry: StorageEntry) -> Dict:
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
    
    def _detect_source(self, filename: str) -> Optional[str]:
        
        """
        从文件名中检测视频来源（如WEB-DL、Bluray、DVD等）
        
        Args:
            filename: 文件名
            
        Returns:
            Optional[str]: 检测到的视频来源类型，如'web', 'bluray', 'dvd', 'hdtv'，或None
        """
        sources = {
            'web': ['web', 'web-dl', 'webrip'],
            'bluray': ['bluray', 'bdrip', 'brrip'],
            'dvd': ['dvd', 'dvdrip'],
            'hdtv': ['hdtv', 'pdtv']
        }
        
        filename_lower = filename.lower()
        for source_type, keywords in sources.items():
            if any(keyword in filename_lower for keyword in keywords):
                return source_type
        return None
    
    async def _calculate_file_hash(self, storage_client: StorageClient, file_path: str) -> Optional[str]:
        """计算文件哈希"""
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
                    if stat.size > 20 * 1024 * 1024:
                        offset = max(0, stat.size - 10 * 1024 * 1024)
                        end_content = b""
                        async for chunk in storage_client.download_iter(file_path, chunk_size=64*1024, offset=offset):
                            end_content += chunk
                            if len(end_content) >= 10 * 1024 * 1024:
                                break
                        content += end_content
                except:
                    pass  # 如果无法seek，就只用前10MB
                
                return hashlib.md5(content).hexdigest()
                
        except Exception as e:
            logger.warning(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    async def process_file(self, file_entry: StorageEntry, context: Dict) -> Optional[Dict]:
        """
        处理单个文件，包括检查是否为媒体文件、解析元数据、计算哈希、检查数据库等
        
        Args:
            file_entry: 存储条目对象，包含文件路径、大小等信息
            context: 包含上下文信息的字典，如storage_id、user_id、storage_client等
            
        Returns:
            Optional[Dict]: 包含处理结果的字典，如文件ID、状态、元数据等，或None表示不处理
        """
        
        try:
            # 检查是否为媒体文件
            if not self._is_media_file(file_entry.path):
                return None
            
            storage_id = context.get("storage_id")
            user_id = context.get("user_id", 1)
            
            # 解析文件信息
            file_info = self._light_parse(file_entry)
            
            # 计算文件哈希（可选）
            storage_client = context.get("storage_client")
            file_hash = None
            if storage_client and file_entry.size and file_entry.size < 100 * 1024 * 1024:
                file_hash = await self._calculate_file_hash(storage_client, file_entry.path)
            
            # 检查数据库中是否已存在
            with next(get_db_session()) as session:
                existing_file = self._find_existing_file_sync(
                    session, storage_id, file_entry.path, file_hash
                )
                
                if existing_file:
                    # 更新现有文件信息
                    updated = self._update_file_info_sync(session, existing_file, file_entry)
                    if updated:
                        return {
                            "status": "updated",
                            "is_media": True,
                            "file_id": existing_file.id,
                            "file_info": file_info
                        }
                    return None
                else:
                    # 创建新文件记录
                    new_file = self._create_file_record_sync(
                        session, storage_id, file_entry, file_info, file_hash, user_id
                    )
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
    
    def _find_existing_file_sync(self, session, storage_id: int,
                                 file_path: str, file_hash: Optional[str]) -> Optional[FileAsset]:
        """同步查找现有文件记录"""
        from sqlalchemy.orm import Session
        
        if file_hash:
            # 优先使用哈希查找 - 注意：FileAsset模型没有file_hash字段，需要检查是否有这个字段
            # 先检查表结构是否支持file_hash
            try:
                file_record = session.query(FileAsset).filter(
                    FileAsset.file_hash == file_hash
                ).first()
                if file_record:
                    return file_record
            except:
                # 如果file_hash字段不存在，回退到路径查找
                pass
        
        # 使用路径查找
        return session.query(FileAsset).filter(
            FileAsset.full_path == file_path
        ).first()
    
    def _update_file_info_sync(self, session, file_record: FileAsset,
                               entry: StorageEntry) -> bool:
        """
        同步更新文件信息
        
        Args:
            session: SQLAlchemy会话对象
            file_record: 要更新的文件记录对象
            entry: 存储条目对象，包含最新的文件信息
            
        Returns:
            bool: 如果有更新则返回True，否则返回False
        """
        try:
            changed = False
            
            if entry.size is not None and file_record.size != entry.size:
                file_record.size = entry.size
                changed = True
            if entry.etag and file_record.etag != entry.etag:
                file_record.etag = entry.etag
                changed = True
            
            # 注意：FileAsset模型没有modified_time字段，跳过这个检查
            
            if changed:
                file_record.updated_at = datetime.now()
                session.commit()
                logger.info(f"更新文件信息: {entry.path}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"更新文件信息失败: {e}")
            session.rollback()
            return False
    
    def _create_file_record_sync(self, session, storage_id: int,
                                 entry: StorageEntry, file_info: Dict, 
                                 file_hash: Optional[str], user_id: int) -> Optional[FileAsset]:
        """
        同步创建文件记录
        
        Args:
            session: SQLAlchemy会话对象
            storage_id: 存储ID
            entry: 存储条目对象，包含文件路径、大小等信息
            file_info: 解析后的文件元数据字典
            file_hash: 文件哈希值（可选）
            user_id: 用户ID
            
        Returns:
            Optional[FileAsset]: 创建的文件记录对象，或None表示创建失败
        """
        try:
            import mimetypes
            from pathlib import Path
            
            # 提取相对路径 - 假设entry.path是绝对路径，我们需要相对路径
            path_parts = Path(entry.path).parts
            if len(path_parts) > 1:
                relative_path = str(Path(*path_parts[1:]))  # 去掉第一个路径组件
            else:
                relative_path = "."
            
            media_file = FileAsset(
                user_id=user_id,
                storage_id=storage_id,
                full_path=entry.path,
                filename=entry.name,
                relative_path=relative_path,
                size=entry.size or 0,
                mimetype=mimetypes.guess_type(entry.path)[0],
                resolution=file_info.get("resolution"),
                etag=entry.etag,
                # playurl=None,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            session.add(media_file)
            session.commit()
            
            logger.info(f"创建文件记录: {entry.path}")
            return media_file
            
        except Exception as e:
            logger.error(f"创建文件记录失败: {e}")
            session.rollback()
            return None
    
    def _get_file_type(self, file_path: str) -> str:
        """获取文件类型 - 返回mimetype"""
        import mimetypes
        mimetype = mimetypes.guess_type(file_path)[0]
        if not mimetype:
            return "application/octet-stream"
        return mimetype


class UnifiedScanEngine:
    """统一扫描引擎"""
    
    def __init__(self):
        self.storage_service = StorageService()
        self.processors: List[ScanProcessor] = []
        self._init_default_processors()
    
    def _init_default_processors(self):
        """初始化默认处理器"""
        # 核心文件资产处理器
        self.register_processor(FileAssetProcessor())
    
    def register_processor(self, processor: ScanProcessor):
        """注册扫描处理器"""
        self.processors.append(processor)
        logger.info(f"注册扫描处理器: {processor.__class__.__name__}")
    
    async def scan_storage(self, storage_id: int, scan_path: str = "/",
                          recursive: bool = True, max_depth: int = 10,
                          user_id: int = 1, batch_size: int = 100) -> ScanResult:
        """
        扫描存储，递归扫描指定路径下的所有文件，更新文件资产数据库
        
        Args:
            storage_id: 存储配置ID
            scan_path: 扫描路径
            recursive: 是否递归扫描
            max_depth: 最大递归深度
            user_id: 用户ID
            batch_size: 批量处理大小
            
        Returns:
            扫描结果
        """
        start_time = datetime.now()
        result = ScanResult()
        
        try:
            # 获取存储客户端
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
                        "user_id": user_id
                    })
                    
                    # 统计结果
                    for batch_result in batch_results:
                        result.total_files += len(batch)
                        
                        for file_result in batch_result:
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
                                result.error_details.append(file_result)
                    
                    # 记录扫描路径
                    for entry in batch:
                        if entry.path not in result.scanned_paths:
                            result.scanned_paths.append(entry.path)
                        # 记录媒体文件集合
                        if not entry.is_dir:
                            ext = Path(entry.path).suffix.lower()
                            if ext in FileAssetProcessor().supported_media_extensions:
                                result.encountered_media_paths.append(entry.path)
                
                # 计算耗时
                result.duration = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"扫描完成: {scan_path}, 统计: {result.__dict__}")
                
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
        将递归扫描结果按指定批次大小分批返回，避免一次性加载过多文件到内存
        
        Args:
            storage_client: 存储客户端实例，用于访问存储后端
            path: 起始扫描路径
            recursive: 是否递归扫描子目录
            max_depth: 最大递归深度，防止无限递归
            batch_size: 每批返回的文件数量，控制内存占用
            
        Yields:
            List[StorageEntry]: 每批文件条目列表
        """
        current_batch = []  # 当前批次缓存列表
        
        # 使用异步生成器逐个接收扫描到的文件条目
        async for entry in self._scan_directory_recursive(storage_client, path, recursive, max_depth, 0):
            current_batch.append(entry)  # 将文件加入当前批次
            
            # 当达到批次大小时，立即返回当前批次并清空缓存
            if len(current_batch) >= batch_size:
                yield current_batch
                current_batch = []
        
        # 处理剩余不足一批的文件
        if current_batch:
            yield current_batch
    
    async def _scan_directory_recursive(self, storage_client: StorageClient,
                                       path: str, recursive: bool, max_depth: int,
                                       current_depth: int) -> AsyncGenerator[StorageEntry, None]:
        """递归扫描目录
        深度优先遍历目录结构，返回所有文件和子目录
        
        Args:
            storage_client: 存储客户端实例，用于访问存储后端
            path: 当前扫描路径
            recursive: 是否递归扫描子目录
            max_depth: 最大递归深度，防止无限递归
            current_depth: 当前递归深度，用于控制递归终止
            
        Yields:
            StorageEntry: 每个文件和目录的元数据条目
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
    
    async def _process_batch(self, batch: List[StorageEntry], context: Dict) -> List[List[Dict]]:
        """批量处理文件
        为每个处理器批量处理文件条目，支持批量处理和逐个处理
        
        Args:
            batch: 当前批次的文件条目列表
            context: 扫描上下文，包含配置和状态信息
            
        Returns:
            List[List[Dict]]: 每个处理器的处理结果列表
        """
        all_results = []
        
        # 为每个处理器创建处理任务
        for processor in self.processors:
            try:
                # 批量处理
                if hasattr(processor, 'process_batch'):
                    results = await processor.process_batch(batch, context)
                else:
                    # 逐个处理
                    results = []
                    for entry in batch:
                        result = await processor.process_file(entry, context)
                        if result:
                            results.append(result)
                
                all_results.append(results)
                # 附带轻量快照到上下文，供后续任务使用
                # 仅收集媒体条目的轻量解析结果
                if processor.__class__.__name__ == 'FileAssetProcessor':
                    parse_snapshots = []
                    for rlist in [results]:
                        for r in rlist:
                            if r.get('is_media') and r.get('file_info'):
                                snap = r['file_info']
                                parse_snapshots.append(snap)
                    context['parse_snapshots'] = parse_snapshots
                
            except Exception as e:
                logger.error(f"处理器 {processor.__class__.__name__} 处理失败: {e}")
                all_results.append([])
        
        return all_results


# 创建全局引擎实例
unified_scan_engine = UnifiedScanEngine()


async def get_unified_scan_engine() -> UnifiedScanEngine:
    """获取统一扫描引擎实例"""
    return unified_scan_engine
