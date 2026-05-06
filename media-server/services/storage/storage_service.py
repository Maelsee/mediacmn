

"""
统一存储服务

提供统一的存储服务接口，支持多种存储后端（WebDAV、SMB、Local、Cloud）
实现完全异步化、单例模式、按需加锁及连接复用。
"""

import threading
import logging
from typing import Dict, Any, Optional, List, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession  # ✅ 导入SQLModel的AsyncSession
from core.db import AsyncSessionLocal
from .storage_client import (
    StorageClient, StorageClientFactory, StorageEntry, StorageInfo
)
from .client_pool import get_client_pool
from models.storage_models import (
    StorageConfig, WebdavStorageConfig, SmbStorageConfig,
    LocalStorageConfig, CloudStorageConfig
)
logger = logging.getLogger(__name__)

class StorageService:
    """统一存储服务 (完全异步版)"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 确保单例初始化逻辑只运行一次
        if not hasattr(self, "_initialized"):
            self._initialized = True
    

    async def _get_detailed_config(self, session: AsyncSession, storage_config: StorageConfig) -> Dict[str, Any]:
        """
        获取详细的存储配置 (异步查询)
        """
        storage_type = storage_config.storage_type
        config_id = storage_config.id
        
        if storage_type == "webdav":
            result = await session.exec(select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == config_id))
            webdav_config = result.first()
            if not webdav_config:
                raise ValueError(f"WebDAV配置不存在: {config_id}")
            
            return {
                "url": webdav_config.hostname,
                "username": webdav_config.login,
                "password": webdav_config.password,
                "timeout": webdav_config.timeout_seconds or 30,
                "verify_ssl": webdav_config.verify_ssl if webdav_config.verify_ssl is not None else True,
                "root_path": webdav_config.root_path or "/"
            }
        
        elif storage_type == "smb":
            result = await session.exec(select(SmbStorageConfig).where(SmbStorageConfig.storage_config_id == config_id))
            smb_config = result.first()
            if not smb_config:
                raise ValueError(f"SMB配置不存在: {config_id}")
            
            return {
                "server": smb_config.server_host,
                "share": smb_config.share_name,
                "username": smb_config.username,
                "password": smb_config.password,
                "domain": getattr(smb_config, "domain", None),
                "port": smb_config.server_port or 445,
                "timeout": 30,
                "client_name": getattr(smb_config, "client_name", "MEDIACMN"),
                "is_direct_tcp": getattr(smb_config, "is_direct_tcp", True)
            }
        
        elif storage_type == "local":
            result = await session.exec(select(LocalStorageConfig).where(LocalStorageConfig.storage_config_id == config_id))
            local_config = result.first()
            if not local_config:
                raise ValueError(f"本地存储配置不存在: {config_id}")
            
            return {
                "base_path": local_config.base_path,
                "readonly": False,
                "auto_create_dirs": getattr(local_config, "auto_create_dirs", True)
            }
        
        elif storage_type == "cloud":
            result = await session.exec(select(CloudStorageConfig).where(CloudStorageConfig.storage_config_id == config_id))
            cloud_config = result.first()
            if not cloud_config:
                raise ValueError(f"云存储配置不存在: {config_id}")
            
            return {
                "provider": cloud_config.cloud_provider,
                "remote_root_path": cloud_config.remote_root_path,
                "access_token": getattr(cloud_config, "access_token", None),
                "refresh_token": getattr(cloud_config, "refresh_token", None),
                "chunk_size_mb": getattr(cloud_config, "chunk_size_mb", 100)
            }
        
        raise ValueError(f"不支持的存储类型: {storage_type}")

    async def get_client(self, storage_id: int) -> StorageClient:
        """
        获取一个新的存储客户端实例（未连接）。
        调用方需自行使用 `async with client:` 管理连接生命周期。
        业务方法（list_directory 等）已改用连接池，无需手动管理。
        """
        return await self.create_client(storage_id)

    async def create_client(self, storage_id: int) -> StorageClient:
        """
        创建一个新的存储客户端实例（未连接）。
        供连接池工厂函数调用，内部完成 DB 查询和客户端实例化。
        """
        async with AsyncSessionLocal() as session:
            result = await session.exec(select(StorageConfig).where(StorageConfig.id == storage_id))
            storage_config = result.first()

            if not storage_config:
                raise ValueError(f"存储配置 ID={storage_id} 不存在")

            detailed_config = await self._get_detailed_config(session, storage_config)

            client = StorageClientFactory.create(
                storage_config.storage_type,
                storage_config.name,
                detailed_config
            )
            return client

    async def _acquire_client(self, storage_id: int, user_id: int = 0):
        """
        从连接池获取已连接的客户端上下文管理器。
        内部负责创建、连接和池化复用。
        """
        pool = get_client_pool()
        return pool.acquire(
            storage_id,
            user_id=user_id,
            client_factory=lambda: self._create_and_connect(storage_id)
        )

    async def _create_and_connect(self, storage_id: int) -> StorageClient:
        """创建客户端并建立连接"""
        client = await self.create_client(storage_id)
        await client.connect()
        return client

    async def test_connection(self, storage_id: int) -> Tuple[bool, Optional[str]]:
        """
        测试存储连接（不使用连接池，创建临时客户端）

        Returns:
            (连接状态, 错误信息)
        """
        try:
            client = await self.create_client(storage_id)
            async with client:
                return await client.check_connection()
        except Exception as e:
            error_msg = str(e)
            logger.error(f"存储连接测试失败: {error_msg}")
            return False, error_msg

    async def list_directory(self, storage_id: int, path: str = "/", depth: int = 1) -> List[StorageEntry]:
        """
        列出目录内容

        Args:
            storage_id: 存储配置 ID
            path: 目录路径
            depth: 递归深度, 可选值: 1, infinity

        Returns:
            存储条目列表
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.list_dir(path, depth)
    
    async def get_file_info(self, storage_id: int, path: str) -> StorageEntry:
        """
        获取文件/目录信息

        Args:
            storage_id: 存储配置 ID
            path: 文件或目录路径

        Returns:
            存储条目信息
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.get_file_info(path)
    
    async def download_file(self, storage_id: int, path: str, chunk_size: int = 64 * 1024) -> bytes:
        """
        下载文件

        Args:
            storage_id: 存储配置 ID
            path: 文件路径
            chunk_size: 块大小

        Returns:
            文件数据
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            chunks = []
            async for chunk in client.download_iter(path, chunk_size):
                chunks.append(chunk)
            return b''.join(chunks)
    
    async def upload_file(self, storage_id: int, path: str, data: bytes, content_type: Optional[str] = None) -> bool:
        """
        上传文件

        Args:
            storage_id: 存储配置 ID
            path: 目标路径
            data: 文件数据
            content_type: 内容类型

        Returns:
            上传成功返回True
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.upload(path, data, content_type)

    async def create_directory(self, storage_id: int, path: str) -> bool:
        """
        创建目录

        Args:
            storage_id: 存储配置 ID
            path: 目录路径

        Returns:
            创建成功返回True
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.create_dir(path)
    
    async def delete_path(self, storage_id: int, path: str) -> bool:
        """
        删除文件或目录

        Args:
            storage_id: 存储配置 ID
            path: 要删除的路径

        Returns:
            删除成功返回True
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.delete(path)
    
    async def get_storage_info(self, storage_id: int, path: str = "/") -> StorageInfo:
        """
        获取存储系统信息

        Args:
            storage_id: 存储配置 ID
            path: 路径（用于获取特定路径的信息）

        Returns:
            存储系统信息
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.info(path)
    
    async def path_exists(self, storage_id: int, path: str) -> bool:
        """
        检查路径是否存在

        Args:
            storage_id: 存储配置 ID
            path: 要检查的路径

        Returns:
            存在返回True
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.exists(path)

    async def move_path(self, storage_id: int, source_path: str, dest_path: str) -> bool:
        """
        移动/重命名文件或目录

        Args:
            storage_id: 存储配置 ID
            source_path: 源路径
            dest_path: 目标路径

        Returns:
            移动成功返回True
        """
        pool = get_client_pool()
        async with pool.acquire(storage_id, user_id=0, client_factory=lambda: self._create_and_connect(storage_id)) as client:
            return await client.move(source_path, dest_path)
    

# 全局存储服务实例
storage_service = StorageService()
