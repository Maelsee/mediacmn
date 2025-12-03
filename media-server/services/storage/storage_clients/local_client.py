"""
本地文件系统存储客户端实现

提供对本地文件系统的统一存储接口支持
"""

import os
import asyncio
import aiofiles
import logging
from typing import List, Optional, Dict, Any, Iterator
from datetime import datetime
from pathlib import Path

from ..storage_client import (
    StorageClient, StorageEntry, StorageInfo, 
    StorageNotFoundError, StoragePermissionError, StorageError
)

logger = logging.getLogger(__name__)


class LocalStorageClient(StorageClient):
    """本地文件系统存储客户端"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.base_path = config.get('base_path', '/')
        self.readonly = config.get('readonly', False)
        self._connected = False
        
        # 确保基础路径存在
        self.base_path = os.path.abspath(self.base_path)
        if not os.path.exists(self.base_path):
            raise StorageError(f"基础路径不存在: {self.base_path}")
    
    def _resolve_path(self, path: str) -> str:
        """解析相对路径为绝对路径"""
        if path.startswith('/'):
            # 绝对路径，相对于基础路径
            relative_path = path.lstrip('/')
            full_path = os.path.join(self.base_path, relative_path)
        else:
            # 相对路径
            full_path = os.path.join(self.base_path, path)
        
        # 确保路径在基础路径范围内（防止路径穿越）
        full_path = os.path.abspath(full_path)
        if not full_path.startswith(self.base_path):
            raise StorageError(f"路径超出允许范围: {path}")
        
        return full_path
    
    async def connect(self) -> bool:
        """建立本地存储连接"""
        try:
            # 检查基础路径是否存在且可访问
            if not os.path.exists(self.base_path):
                raise StorageError(f"基础路径不存在: {self.base_path}")
            
            if not os.access(self.base_path, os.R_OK):
                raise StoragePermissionError(f"无法读取基础路径: {self.base_path}", self.base_path)
            
            if not self.readonly and not os.access(self.base_path, os.W_OK):
                raise StoragePermissionError(f"无法写入基础路径: {self.base_path}", self.base_path)
            
            self._connected = True
            logger.info(f"本地存储客户端已连接: {self.name} -> {self.base_path}")
            return True
            
        except Exception as e:
            logger.error(f"本地存储连接失败: {e}")
            if isinstance(e, (StorageError, StoragePermissionError)):
                raise
            raise StorageError(f"本地存储连接失败: {e}")
    
    async def disconnect(self) -> None:
        """断开本地存储连接"""
        self._connected = False
        logger.info(f"本地存储客户端已断开: {self.name}")
    
    async def check_connection(self) -> tuple[bool, Optional[str]]:
        """测试本地存储连接"""
        try:
            if not os.path.exists(self.base_path):
                return False, f"基础路径不存在: {self.base_path}"
            
            if not os.access(self.base_path, os.R_OK):
                return False, f"无法读取基础路径: {self.base_path}"
            
            if not self.readonly and not os.access(self.base_path, os.W_OK):
                return False, f"无法写入基础路径: {self.base_path}"
            
            return True, None
            
        except Exception as e:
            error_msg = f"连接测试异常: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def info(self, path: str = "/") -> StorageInfo:
        """获取本地存储系统信息"""
        try:
            full_path = self._resolve_path(path)
            
            # 获取磁盘空间信息（如果可能）
            try:
                stat = os.statvfs(full_path)
                total_space = stat.f_blocks * stat.f_frsize
                free_space = stat.f_bavail * stat.f_frsize
                used_space = total_space - free_space
            except (OSError, AttributeError):
                # 某些系统不支持statvfs
                total_space = None
                free_space = None
                used_space = None
            
            return StorageInfo(
                total_space=total_space,
                used_space=used_space,
                free_space=free_space,
                readonly=self.readonly,
                supports_resume=True,
                supports_range=True,
                max_file_size=None
            )
            
        except Exception as e:
            logger.error(f"获取存储信息失败: {e}")
            raise StorageError(f"获取存储信息失败: {e}")
    
    async def list_dir(self, path: str = "/", depth: int = 1) -> List[StorageEntry]:
        """列出本地目录内容"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        try:
            full_path = self._resolve_path(path)
            
            if not os.path.exists(full_path):
                raise StorageNotFoundError(f"路径不存在: {path}", path)
            
            if not os.path.isdir(full_path):
                raise StorageError(f"路径不是目录: {path}")
            
            entries = []
            
            # 使用os.scandir获取目录内容（性能更好）
            with os.scandir(full_path) as scanner:
                for item in scanner:
                    try:
                        stat = item.stat()
                        
                        entry = StorageEntry(
                            name=item.name,
                            path=os.path.join(path, item.name).replace('\\', '/'),
                            is_dir=item.is_dir(),
                            size=stat.st_size if item.is_file() else None,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            content_type=None,  # 本地文件系统不提供内容类型
                            etag=str(stat.st_mtime)  # 使用修改时间作为简单的ETag
                        )
                        
                        entries.append(entry)
                        
                    except (OSError, PermissionError) as e:
                        # 跳过无法访问的条目
                        logger.warning(f"无法访问条目 {item.name}: {e}")
                        continue
            
            # 按名称排序
            entries.sort(key=lambda x: x.name)
            
            return entries
            
        except Exception as e:
            error_msg = f"列出目录失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"权限不足: {path}", path)
            else:
                raise StorageError(error_msg)
    
    async def get_file_info(self, path: str) -> StorageEntry:
        """获取本地文件/目录详细信息"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        try:
            full_path = self._resolve_path(path)
            
            if not os.path.exists(full_path):
                raise StorageNotFoundError(f"路径不存在: {path}", path)
            
            stat = os.stat(full_path)
            is_dir = os.path.isdir(full_path)
            name = os.path.basename(path.rstrip('/'))
            
            return StorageEntry(
                name=name,
                path=path,
                is_dir=is_dir,
                size=stat.st_size if not is_dir else None,
                modified=datetime.fromtimestamp(stat.st_mtime),
                content_type=None,
                etag=str(stat.st_mtime)
            )
        
        except Exception as e:
            error_msg = f"获取文件信息失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"权限不足: {path}", path)
            else:
                raise StorageError(error_msg)
    
    async def stat(self, path: str) -> StorageEntry:
        return await self.get_file_info(path)
    
    async def download_iter(self, path: str, chunk_size: int = 64 * 1024, offset: int = 0) -> Iterator[bytes]:
        """流式下载本地文件"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        try:
            full_path = self._resolve_path(path)
            
            if not os.path.exists(full_path):
                raise StorageNotFoundError(f"文件不存在: {path}", path)
            
            if os.path.isdir(full_path):
                raise StorageError(f"路径是目录，不是文件: {path}")
            
            if not os.access(full_path, os.R_OK):
                raise StoragePermissionError(f"读取权限不足: {path}", path)
            
            # 使用aiofiles进行异步文件读取
            async with aiofiles.open(full_path, 'rb') as file:
                if offset and offset > 0:
                    await file.seek(offset)
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
                    
        except Exception as e:
            error_msg = f"下载文件失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"读取权限不足: {path}", path)
            else:
                raise StorageError(error_msg)
    
    async def upload(self, path: str, data: bytes, 
                    content_type: Optional[str] = None) -> bool:
        """上传文件到本地文件系统"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        if self.readonly:
            raise StoragePermissionError("存储为只读模式", path)
        
        try:
            full_path = self._resolve_path(path)
            
            # 确保父目录存在
            parent_dir = os.path.dirname(full_path)
            os.makedirs(parent_dir, exist_ok=True)
            
            # 检查写入权限
            if os.path.exists(full_path):
                if not os.access(full_path, os.W_OK):
                    raise StoragePermissionError(f"写入权限不足: {path}", path)
            else:
                if not os.access(parent_dir, os.W_OK):
                    raise StoragePermissionError(f"目录写入权限不足: {parent_dir}", path)
            
            # 使用aiofiles进行异步文件写入
            async with aiofiles.open(full_path, 'wb') as file:
                await file.write(data)
            
            logger.info(f"文件上传成功: {path} ({len(data)} bytes)")
            return True
            
        except Exception as e:
            error_msg = f"上传文件失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StoragePermissionError, StorageError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"写入权限不足: {path}", path)
            elif "No space left" in str(e):
                raise StorageError("磁盘空间不足")
            else:
                raise StorageError(error_msg)
    
    async def create_dir(self, path: str) -> bool:
        """在本地文件系统中创建目录"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        if self.readonly:
            raise StoragePermissionError("存储为只读模式", path)
        
        try:
            full_path = self._resolve_path(path)
            
            if os.path.exists(full_path):
                if os.path.isdir(full_path):
                    return True  # 目录已存在，视为成功
                else:
                    raise StorageError(f"路径已存在且不是目录: {path}")
            
            # 检查父目录权限
            parent_dir = os.path.dirname(full_path)
            if not os.access(parent_dir, os.W_OK):
                raise StoragePermissionError(f"目录创建权限不足: {parent_dir}", path)
            
            os.makedirs(full_path, exist_ok=True)
            
            logger.info(f"目录创建成功: {path}")
            return True
            
        except Exception as e:
            error_msg = f"创建目录失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StoragePermissionError, StorageError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"创建权限不足: {path}", path)
            else:
                raise StorageError(error_msg)
    
    async def delete(self, path: str) -> bool:
        """删除本地文件或目录"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        if self.readonly:
            raise StoragePermissionError("存储为只读模式", path)
        
        try:
            full_path = self._resolve_path(path)
            
            if not os.path.exists(full_path):
                raise StorageNotFoundError(f"路径不存在: {path}", path)
            
            if not os.access(full_path, os.W_OK):
                raise StoragePermissionError(f"删除权限不足: {path}", path)
            
            if os.path.isdir(full_path):
                # 删除目录及其内容
                import shutil
                shutil.rmtree(full_path)
            else:
                # 删除文件
                os.remove(full_path)
            
            logger.info(f"删除成功: {path}")
            return True
            
        except Exception as e:
            error_msg = f"删除失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"删除权限不足: {path}", path)
            else:
                raise StorageError(error_msg)
    
    async def exists(self, path: str) -> bool:
        """检查本地路径是否存在"""
        if not self._connected:
            return False
        
        try:
            full_path = self._resolve_path(path)
            return os.path.exists(full_path)
        except Exception:
            return False
    
    async def move(self, source_path: str, dest_path: str) -> bool:
        """移动/重命名本地文件或目录"""
        if not self._connected:
            raise StorageError("客户端未连接")
        
        if self.readonly:
            raise StoragePermissionError("存储为只读模式", source_path)
        
        try:
            source_full_path = self._resolve_path(source_path)
            dest_full_path = self._resolve_path(dest_path)
            
            if not os.path.exists(source_full_path):
                raise StorageNotFoundError(f"源路径不存在: {source_path}", source_path)
            
            if not os.access(source_full_path, os.W_OK):
                raise StoragePermissionError(f"移动权限不足: {source_path}", source_path)
            
            # 确保目标父目录存在
            dest_parent = os.path.dirname(dest_full_path)
            os.makedirs(dest_parent, exist_ok=True)
            
            # 执行移动操作
            os.rename(source_full_path, dest_full_path)
            
            logger.info(f"移动成功: {source_path} -> {dest_path}")
            return True
            
        except Exception as e:
            error_msg = f"移动失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            elif "Permission denied" in str(e):
                raise StoragePermissionError(f"移动权限不足: {source_path}", source_path)
            elif "File exists" in str(e):
                raise StorageError("目标路径已存在")
            else:
                raise StorageError(error_msg)
