# """
# 统一存储服务

# 提供统一的存储服务接口，支持多种存储后端（WebDAV、SMB、Local、Cloud）
# """

# import asyncio
# import threading
# from typing import Dict, Any, Optional, List, Tuple
# from sqlmodel import Session, select

# from .storage_client import (
#     StorageClient, StorageClientFactory, StorageEntry, StorageInfo,
#     StorageError, StorageConnectionError
# )
# from models.storage_models import StorageConfig, WebdavStorageConfig, SmbStorageConfig, LocalStorageConfig, CloudStorageConfig

# # 导入存储客户端实现，确保它们被注册到工厂
# from .storage_clients import WebDAVStorageClient, SMBStorageClient, LocalStorageClient
# from core.db import AsyncSessionLocal  # 建议切换到异步Session

# import logging
# logger = logging.getLogger(__name__)


# class StorageService:
#     """统一存储服务"""
#     _instance = None
#     _lock = threading.Lock()

#     def __new__(cls):
#         if not cls._instance:
#             with cls._lock:
#                 if not cls._instance:
#                     cls._instance = super().__new__(cls)
#         return cls._instance
    
#     # def __init__(self):
#     #     self._clients: Dict[str, StorageClient] = {}

#     def __init__(self):
#         # 确保只初始化一次
#         if not hasattr(self, "_initialized"):
#             self._clients: Dict[str, StorageClient] = {}
#             self._connection_locks: Dict[str, asyncio.Lock] = {}
#             self._initialized = True
    
#     def _build_client_key(self, user_id: int, storage_name: str) -> str:
#         """构建客户端缓存键"""
#         return f"{user_id}:{storage_name}"
    
#     def _get_storage_type(self, storage_config: StorageConfig) -> str:
#         """获取存储类型"""
#         return storage_config.storage_type
    
#     def _get_detailed_config(self, session: Session, storage_config: StorageConfig) -> Dict[str, Any]:
#         """获取详细的存储配置"""
#         storage_type = self._get_storage_type(storage_config)
        
#         if storage_type == "webdav":
#             webdav_config = session.exec(
#                 select(WebdavStorageConfig).where(WebdavStorageConfig.storage_config_id == storage_config.id)
#             ).first()
#             if not webdav_config:
#                 raise ValueError(f"WebDAV配置不存在: {storage_config.id}")
            
           
#             return {
#                 "url": webdav_config.hostname,
#                 "username": webdav_config.login,
#                 "password": webdav_config.password,
#                 "timeout": webdav_config.timeout_seconds or 30,
#                 "verify_ssl": webdav_config.verify_ssl if webdav_config.verify_ssl is not None else True,
#                 "root_path": webdav_config.root_path or "/"
#             }
        
#         elif storage_type == "smb":
#             smb_config = session.exec(
#                 select(SmbStorageConfig).where(SmbStorageConfig.storage_config_id == storage_config.id)
#             ).first()
#             if not smb_config:
#                 raise ValueError(f"SMB配置不存在: {storage_config.id}")
            
#             # 直接使用明文配置，不再加密解密
#             return {
#                 "server": smb_config.server_host,
#                 "share": smb_config.share_name,
#                 "username": smb_config.username,
#                 "password": smb_config.password,
#                 "domain": getattr(smb_config, "domain", None),
#                 "port": smb_config.server_port or 445,
#                 "timeout": 30,
#                 "client_name": getattr(smb_config, "client_name", "MEDIACMN"),
#                 "is_direct_tcp": getattr(smb_config, "is_direct_tcp", True)
#             }
        
#         elif storage_type == "local":
#             local_config = session.exec(
#                 select(LocalStorageConfig).where(LocalStorageConfig.storage_config_id == storage_config.id)
#             ).first()
#             if not local_config:
#                 raise ValueError(f"本地存储配置不存在: {storage_config.id}")
            
#             # 直接使用明文配置，不再加密解密
#             return {
#                 "base_path": local_config.base_path,
#                 "readonly": False,
#                 "auto_create_dirs": getattr(local_config, "auto_create_dirs", True)
#             }
        
#         elif storage_type == "cloud":
#             cloud_config = session.exec(
#                 select(CloudStorageConfig).where(CloudStorageConfig.storage_config_id == storage_config.id)
#             ).first()
#             if not cloud_config:
#                 raise ValueError(f"云存储配置不存在: {storage_config.id}")
            
#             # 直接使用明文配置，不再加密解密
#             return {
#                 "provider": cloud_config.cloud_provider,
#                 "remote_root_path": cloud_config.remote_root_path,
#                 "access_token": getattr(cloud_config, "access_token", None),
#                 "refresh_token": getattr(cloud_config, "refresh_token", None),
#                 "chunk_size_mb": getattr(cloud_config, "chunk_size_mb", 100)
#             }
        
#         else:
#             raise ValueError(f"不支持的存储类型: {storage_type}")
    
#     async def ensure_client(self, session: Session, user_id: int, storage_name: str) -> StorageClient:
#         """
#         确保获取存储客户端
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
            
#         Returns:
#             存储客户端实例
            
#         Raises:
#             ValueError: 配置不存在或类型不支持
#             StorageConnectionError: 连接失败
#         """
#         client_key = self._build_client_key(user_id, storage_name)
        
#         # 检查缓存
#         if client_key in self._clients:
#             return self._clients[client_key]
        
#         # 获取存储配置
#         storage_config = session.exec(
#             select(StorageConfig).where(
#                 (StorageConfig.user_id == user_id) &
#                 (StorageConfig.name == storage_name) &
#                 (StorageConfig.is_active == True)
#             )
#         ).first()
        
#         if not storage_config:
#             raise ValueError(f"存储配置不存在: {storage_name}")
        
#         # 获取存储类型和详细配置
#         storage_type = self._get_storage_type(storage_config)
#         detailed_config = self._get_detailed_config(session, storage_config)
        
#         # 创建客户端
#         client = StorageClientFactory.create(storage_type, storage_name, detailed_config)
        
#         # 连接客户端
#         try:
#             await client.connect()
#         except Exception as e:
#             logger.error(f"存储客户端连接失败: {e}")
#             raise StorageConnectionError(f"存储客户端连接失败: {e}")
        
#         # 缓存客户端
#         self._clients[client_key] = client
#         logger.debug(f"存储客户端已创建并连接: {client_key}")
        
#         return client
    
#     async def test_connection(self, session: Session, user_id: int, storage_name: str) -> Tuple[bool, Optional[str]]:
#         """
#         测试存储连接
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
            
#         Returns:
#             (连接状态, 错误信息)
#         """
#         try:
#             client = await self.ensure_client(session, user_id, storage_name)
#             return await client.check_connection()
#         except Exception as e:
#             error_msg = str(e)
#             logger.error(f"存储连接测试失败: {error_msg}")
#             return False, error_msg
    
#     async def list_directory(self, session: Session, user_id: int, storage_name: str, 
#                            path: str = "/", depth: int = 1) -> List[StorageEntry]:
#         """
#         列出目录内容
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 目录路径
#             depth: 递归深度, 可选值: 1, infinity
            
#         Returns:
#             存储条目列表
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.list_dir(path, depth)
    
#     async def get_file_info(self, session: Session, user_id: int, storage_name: str, 
#                            path: str) -> StorageEntry:
#         """
#         获取文件/目录信息
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 文件或目录路径
            
#         Returns:
#             存储条目信息
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.get_file_info(path)
    
#     async def download_file(self, session: Session, user_id: int, storage_name: str, 
#                            path: str, chunk_size: int = 64 * 1024) -> bytes:
#         """
#         下载文件
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 文件路径
#             chunk_size: 块大小
            
#         Returns:
#             文件数据
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
        
#         chunks = []
#         async for chunk in client.download_iter(path, chunk_size):
#             chunks.append(chunk)
        
#         return b''.join(chunks)
    
#     async def upload_file(self, session: Session, user_id: int, storage_name: str, 
#                          path: str, data: bytes, content_type: Optional[str] = None) -> bool:
#         """
#         上传文件
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 目标路径
#             data: 文件数据
#             content_type: 内容类型
            
#         Returns:
#             上传成功返回True
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.upload(path, data, content_type)
    
#     async def create_directory(self, session: Session, user_id: int, storage_name: str, 
#                               path: str) -> bool:
#         """
#         创建目录
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 目录路径
            
#         Returns:
#             创建成功返回True
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.create_dir(path)
    
#     async def delete_path(self, session: Session, user_id: int, storage_name: str, 
#                          path: str) -> bool:
#         """
#         删除文件或目录
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 要删除的路径
            
#         Returns:
#             删除成功返回True
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.delete(path)
    
#     async def get_storage_info(self, session: Session, user_id: int, storage_name: str, 
#                                path: str = "/") -> StorageInfo:
#         """
#         获取存储系统信息
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 路径（用于获取特定路径的信息）
            
#         Returns:
#             存储系统信息
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.info(path)
    
#     async def path_exists(self, session: Session, user_id: int, storage_name: str, 
#                          path: str) -> bool:
#         """
#         检查路径是否存在
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             path: 要检查的路径
            
#         Returns:
#             存在返回True
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.exists(path)
    
#     async def move_path(self, session: Session, user_id: int, storage_name: str, 
#                        source_path: str, dest_path: str) -> bool:
#         """
#         移动/重命名文件或目录
        
#         Args:
#             session: 数据库会话
#             user_id: 用户ID
#             storage_name: 存储配置名称
#             source_path: 源路径
#             dest_path: 目标路径
            
#         Returns:
#             移动成功返回True
#         """
#         client = await self.ensure_client(session, user_id, storage_name)
#         return await client.move(source_path, dest_path)
    
#     def remove_client(self, user_id: int, storage_name: str) -> None:
#         """
#         移除客户端缓存
        
#         Args:
#             user_id: 用户ID
#             storage_name: 存储配置名称
#         """
#         client_key = self._build_client_key(user_id, storage_name)
#         if client_key in self._clients:
#             client = self._clients.pop(client_key)
#             # 异步关闭客户端连接
#             asyncio.create_task(client.disconnect())
#             logger.info(f"存储客户端已移除: {client_key}")
    
#     def clear_all_clients(self) -> None:
#         """清除所有客户端缓存"""
#         client_keys = list(self._clients.keys())
#         for client_key in client_keys:
#             client = self._clients.pop(client_key)
#             asyncio.create_task(client.disconnect())
        
#         logger.info(f"已清除所有存储客户端缓存，数量: {len(client_keys)}")
    
#     async def get_client(self, storage_id: int) -> Optional[StorageClient]:
#         """
#         根据存储ID获取存储客户端（简化接口）
        
#         Args:
#             storage_id: 存储配置ID
            
#         Returns:
#             存储客户端实例，如果找不到则返回None
#         """
#         try:
#             # 获取存储配置
#             from core.db import get_session
#             from models.storage_models import StorageConfig
            
#             with next(get_session()) as session:
#                 storage_config = session.exec(select(StorageConfig).where(StorageConfig.id == storage_id)).first()
#                 if not storage_config:
#                     logger.error(f"存储配置不存在: {storage_id}")
#                     return None
            
                
#                 # 使用ensure_client获取客户端
#                 return await self.ensure_client(
#                     session=session,
#                     user_id=storage_config.user_id,
#                     storage_name=storage_config.name
#                 )
                
#         except Exception as e:
#             logger.error(f"获取存储客户端失败 {storage_id}: {e}")
#             return None

# # 全局存储服务实例
# storage_service = StorageService()

"""
统一存储服务

提供统一的存储服务接口，支持多种存储后端（WebDAV、SMB、Local、Cloud）
实现完全异步化、单例模式、按需加锁及连接复用。
"""

import asyncio
import threading
import logging
from typing import Dict, Any, Optional, List, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession  # ✅ 导入SQLModel的AsyncSession

from .storage_client import (
    StorageClient, StorageClientFactory, StorageEntry, StorageInfo,
    StorageError, StorageConnectionError
)
from models.storage_models import (
    StorageConfig, WebdavStorageConfig, SmbStorageConfig, 
    LocalStorageConfig, CloudStorageConfig
)

# 确保注册
# from .storage_clients import WebDAVStorageClient, SMBStorageClient, LocalStorageClient
from core.db import AsyncSessionLocal

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
            self._clients: Dict[str, StorageClient] = {}
            self._connection_locks: Dict[str, asyncio.Lock] = {}
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
        核心接口：通过 ID 获取已连接的客户端 (完全异步)
        """
        client_key = str(storage_id)

        # 1. 快速检查缓存
        if client_key in self._clients:
            client = self._clients[client_key]
            # 修正：判断 client 是否依然存活
            if client.is_alive():
                return client
            else:
                logger.warning(f"存储客户端 ID={storage_id} 连接已失效，尝试重连...")
                
        # 2. 获取针对该 ID 的异步锁，防止并发连接
        if client_key not in self._connection_locks:
            self._connection_locks[client_key] = asyncio.Lock()

        async with self._connection_locks[client_key]:
            # 双重检查
            if client_key in self._clients:
                return self._clients[client_key]

            async with AsyncSessionLocal() as session:
                # 异步查询主配置
                result = await session.exec(select(StorageConfig).where(StorageConfig.id == storage_id))
                storage_config = result.first()
                
                if not storage_config:
                    raise ValueError(f"存储配置 ID={storage_id} 不存在")

                # 异步获取详细配置
                detailed_config = await self._get_detailed_config(session, storage_config)
                
                # 创建客户端
                client = StorageClientFactory.create(
                    storage_config.storage_type, 
                    storage_config.name, 
                    detailed_config
                )
                
                try:
                    await client.connect()
                    self._clients[client_key] = client
                    logger.info(f"存储客户端已连接并缓存: ID={storage_id} ({storage_config.storage_type})")
                    return client
                except Exception as e:
                    logger.error(f"存储客户端 ID={storage_id} 连接失败: {e}")
                    raise StorageConnectionError(f"连接失败: {str(e)}")
    
    def remove_client(self, storage_id: int) -> None:
        """显式移除并断开客户端"""
        client_key = str(storage_id)
        if client_key in self._clients:
            client = self._clients.pop(client_key)
            asyncio.create_task(client.disconnect())
            logger.info(f"存储客户端 ID={storage_id} 已移除")

    async def clear_all_clients(self) -> None:
        """清除所有客户端"""
        tasks = [client.disconnect() for client in self._clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()
        logger.info("所有存储连接已关闭")

    

    # --- 以下为业务操作接口，全部调用 get_client ---
    async def ensure_client(self, session: AsyncSession, user_id: int, storage_name: str) -> StorageClient:
        """
        兼容旧接口：确保获取存储客户端 (已改为异步)
        """
        # 为了复用逻辑，先通过同步传入的信息查询 ID，再调用 get_client
        stmt = select(StorageConfig.id).where(
            (StorageConfig.user_id == user_id) &
            (StorageConfig.name == storage_name) &
            (StorageConfig.is_active == True)
        )
        result = await session.exec(stmt)
        storage_id = result.first()
        
        if not storage_id:
            raise ValueError(f"存储配置不存在: {storage_name}")
            
        return await self.get_client(storage_id)

    async def test_connection(self, session: AsyncSession, user_id: int, storage_name: str) -> Tuple[bool, Optional[str]]:
        """
        测试存储连接
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            
        Returns:
            (连接状态, 错误信息)
        """
        try:
            client = await self.ensure_client(session, user_id, storage_name)
            return await client.check_connection()
        except Exception as e:
            error_msg = str(e)
            logger.error(f"存储连接测试失败: {error_msg}")
            return False, error_msg
    
    async def list_directory(self, session: AsyncSession, user_id: int, storage_name: str, 
                           path: str = "/", depth: int = 1) -> List[StorageEntry]:
        """
        列出目录内容
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 目录路径
            depth: 递归深度, 可选值: 1, infinity
            
        Returns:
            存储条目列表
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.list_dir(path, depth)
    
    async def get_file_info(self, session: AsyncSession, user_id: int, storage_name: str, 
                           path: str) -> StorageEntry:
        """
        获取文件/目录信息
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 文件或目录路径
            
        Returns:
            存储条目信息
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.get_file_info(path)
    
    async def download_file(self, session: AsyncSession, user_id: int, storage_name: str, 
                           path: str, chunk_size: int = 64 * 1024) -> bytes:
        """
        下载文件
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 文件路径
            chunk_size: 块大小
            
        Returns:
            文件数据
        """
        client = await self.ensure_client(session, user_id, storage_name)
        
        chunks = []
        async for chunk in client.download_iter(path, chunk_size):
            chunks.append(chunk)
        
        return b''.join(chunks)
    
    async def upload_file(self, session: AsyncSession, user_id: int, storage_name: str, 
                         path: str, data: bytes, content_type: Optional[str] = None) -> bool:
        """
        上传文件
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 目标路径
            data: 文件数据
            content_type: 内容类型
            
        Returns:
            上传成功返回True
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.upload(path, data, content_type)
    
    async def create_directory(self, session: AsyncSession, user_id: int, storage_name: str, 
                              path: str) -> bool:
        """
        创建目录
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 目录路径
            
        Returns:
            创建成功返回True
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.create_dir(path)
    
    async def delete_path(self, session: AsyncSession, user_id: int, storage_name: str, 
                         path: str) -> bool:
        """
        删除文件或目录
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 要删除的路径
            
        Returns:
            删除成功返回True
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.delete(path)
    
    async def get_storage_info(self, session: AsyncSession, user_id: int, storage_name: str, 
                               path: str = "/") -> StorageInfo:
        """
        获取存储系统信息
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 路径（用于获取特定路径的信息）
            
        Returns:
            存储系统信息
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.info(path)
    
    async def path_exists(self, session: AsyncSession, user_id: int, storage_name: str, 
                         path: str) -> bool:
        """
        检查路径是否存在
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            path: 要检查的路径
            
        Returns:
            存在返回True
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.exists(path)
    
    async def move_path(self, session: AsyncSession, user_id: int, storage_name: str, 
                       source_path: str, dest_path: str) -> bool:
        """
        移动/重命名文件或目录
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            source_path: 源路径
            dest_path: 目标路径
            
        Returns:
            移动成功返回True
        """
        client = await self.ensure_client(session, user_id, storage_name)
        return await client.move(source_path, dest_path)
    

# 全局存储服务实例
storage_service = StorageService()
