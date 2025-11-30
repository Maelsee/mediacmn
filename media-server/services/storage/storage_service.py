"""
统一存储服务

提供统一的存储服务接口，支持多种存储后端（WebDAV、SMB、Local、Cloud）
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session

from .storage_client import (
    StorageClient, StorageClientFactory, StorageEntry, StorageInfo,
    StorageError, StorageConnectionError
)
from models.storage_models import StorageConfig, WebdavStorageConfig, SmbStorageConfig, LocalStorageConfig, CloudStorageConfig
from .storage_config_service import StorageConfigService

# 导入存储客户端实现，确保它们被注册到工厂
from .storage_clients import WebDAVStorageClient, SMBStorageClient, LocalStorageClient

logger = logging.getLogger(__name__)


class StorageService:
    """统一存储服务"""
    
    def __init__(self):
        self._clients: Dict[str, StorageClient] = {}
    
    def _build_client_key(self, user_id: int, storage_name: str) -> str:
        """构建客户端缓存键"""
        return f"{user_id}:{storage_name}"
    
    def _get_storage_type(self, storage_config: StorageConfig) -> str:
        """获取存储类型"""
        return storage_config.storage_type
    
    def _get_detailed_config(self, session: Session, storage_config: StorageConfig) -> Dict[str, Any]:
        """获取详细的存储配置"""
        storage_type = self._get_storage_type(storage_config)
        
        if storage_type == "webdav":
            webdav_config = session.query(WebdavStorageConfig).filter_by(
                storage_config_id=storage_config.id
            ).first()
            if not webdav_config:
                raise ValueError(f"WebDAV配置不存在: {storage_config.id}")
            
            # 直接使用明文配置，不再加密解密
            return {
                "url": webdav_config.hostname,
                "username": webdav_config.login,
                "password": webdav_config.password,
                "timeout": webdav_config.timeout_seconds or 30,
                "verify_ssl": webdav_config.verify_ssl if webdav_config.verify_ssl is not None else True,
                "root_path": webdav_config.root_path or "/"
            }
        
        elif storage_type == "smb":
            smb_config = session.query(SmbStorageConfig).filter_by(
                storage_config_id=storage_config.id
            ).first()
            if not smb_config:
                raise ValueError(f"SMB配置不存在: {storage_config.id}")
            
            # 直接使用明文配置，不再加密解密
            return {
                "server": smb_config.server,
                "share": smb_config.share,
                "username": smb_config.username,
                "password": smb_config.password,
                "port": smb_config.port or 445,
                "timeout": smb_config.timeout_seconds or 30
            }
        
        elif storage_type == "local":
            local_config = session.query(LocalStorageConfig).filter_by(
                storage_config_id=storage_config.id
            ).first()
            if not local_config:
                raise ValueError(f"本地存储配置不存在: {storage_config.id}")
            
            # 直接使用明文配置，不再加密解密
            return {
                "base_path": local_config.base_path,
                "readonly": local_config.readonly if local_config.readonly is not None else False
            }
        
        elif storage_type == "cloud":
            cloud_config = session.query(CloudStorageConfig).filter_by(
                storage_config_id=storage_config.id
            ).first()
            if not cloud_config:
                raise ValueError(f"云存储配置不存在: {storage_config.id}")
            
            # 直接使用明文配置，不再加密解密
            return {
                "provider": cloud_config.provider,
                "bucket": cloud_config.bucket,
                "access_key": cloud_config.access_key,
                "secret_key": cloud_config.secret_key,
                "region": cloud_config.region,
                "endpoint": cloud_config.endpoint
            }
        
        else:
            raise ValueError(f"不支持的存储类型: {storage_type}")
    
    async def ensure_client(self, session: Session, user_id: int, storage_name: str) -> StorageClient:
        """
        确保获取存储客户端
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            storage_name: 存储配置名称
            
        Returns:
            存储客户端实例
            
        Raises:
            ValueError: 配置不存在或类型不支持
            StorageConnectionError: 连接失败
        """
        client_key = self._build_client_key(user_id, storage_name)
        
        # 检查缓存
        if client_key in self._clients:
            return self._clients[client_key]
        
        # 获取存储配置
        storage_config = session.query(StorageConfig).filter_by(
            user_id=user_id,
            name=storage_name,
            is_active=True
        ).first()
        
        if not storage_config:
            raise ValueError(f"存储配置不存在: {storage_name}")
        
        # 获取存储类型和详细配置
        storage_type = self._get_storage_type(storage_config)
        detailed_config = self._get_detailed_config(session, storage_config)
        
        # 创建客户端
        client = StorageClientFactory.create(storage_type, storage_name, detailed_config)
        
        # 连接客户端
        try:
            await client.connect()
        except Exception as e:
            logger.error(f"存储客户端连接失败: {e}")
            raise StorageConnectionError(f"存储客户端连接失败: {e}")
        
        # 缓存客户端
        self._clients[client_key] = client
        logger.info(f"存储客户端已创建并连接: {client_key}")
        
        return client
    
    async def test_connection(self, session: Session, user_id: int, storage_name: str) -> Tuple[bool, Optional[str]]:
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
    
    async def list_directory(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def get_file_info(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def download_file(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def upload_file(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def create_directory(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def delete_path(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def get_storage_info(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def path_exists(self, session: Session, user_id: int, storage_name: str, 
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
    
    async def move_path(self, session: Session, user_id: int, storage_name: str, 
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
    
    def remove_client(self, user_id: int, storage_name: str) -> None:
        """
        移除客户端缓存
        
        Args:
            user_id: 用户ID
            storage_name: 存储配置名称
        """
        client_key = self._build_client_key(user_id, storage_name)
        if client_key in self._clients:
            client = self._clients.pop(client_key)
            # 异步关闭客户端连接
            asyncio.create_task(client.disconnect())
            logger.info(f"存储客户端已移除: {client_key}")
    
    def clear_all_clients(self) -> None:
        """清除所有客户端缓存"""
        client_keys = list(self._clients.keys())
        for client_key in client_keys:
            client = self._clients.pop(client_key)
            asyncio.create_task(client.disconnect())
        
        logger.info(f"已清除所有存储客户端缓存，数量: {len(client_keys)}")
    
    async def get_client(self, storage_id: int) -> Optional[StorageClient]:
        """
        根据存储ID获取存储客户端（简化接口）
        
        Args:
            storage_id: 存储配置ID
            
        Returns:
            存储客户端实例，如果找不到则返回None
        """
        try:
            # 获取存储配置
            from core.db import get_session
            from models.storage_models import StorageConfig
            
            with next(get_session()) as session:
                storage_config = session.query(StorageConfig).filter_by(id=storage_id).first()
                if not storage_config:
                    logger.error(f"存储配置不存在: {storage_id}")
                    return None
                
                # 使用ensure_client获取客户端
                return await self.ensure_client(
                    session=session,
                    user_id=storage_config.user_id,
                    storage_name=storage_config.name
                )
                
        except Exception as e:
            logger.error(f"获取存储客户端失败 {storage_id}: {e}")
            return None


# 全局存储服务实例
storage_service = StorageService()