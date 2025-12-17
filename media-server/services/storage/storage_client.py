"""
统一存储客户端接口定义

提供所有存储后端（WebDAV、SMB、Local、Cloud）的统一抽象接口，
支持连接测试、文件列表、上传下载等核心操作。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Iterator, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StorageEntry:
    """存储条目信息"""
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    modified: Optional[datetime] = None
    content_type: Optional[str] = None
    etag: Optional[str] = None



@dataclass
class StorageInfo:
    """存储系统信息"""
    total_space: Optional[int] = None
    used_space: Optional[int] = None
    free_space: Optional[int] = None
    readonly: bool = False
    supports_resume: bool = False
    supports_range: bool = False
    max_file_size: Optional[int] = None


class StorageError(Exception):
    """存储操作基础异常"""
    
    def __init__(self, message: str, code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code or "STORAGE_ERROR"
        self.details = details or {}


class StorageConnectionError(StorageError):
    """存储连接异常"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CONNECTION_ERROR", details)


class StorageNotFoundError(StorageError):
    """存储路径不存在异常"""
    def __init__(self, message: str, path: str):
        super().__init__(message, "NOT_FOUND_ERROR", {"path": path})


class StoragePermissionError(StorageError):
    """存储权限异常"""
    def __init__(self, message: str, path: str):
        super().__init__(message, "PERMISSION_ERROR", {"path": path})


class StorageClient(ABC):
    """
    统一存储客户端抽象基类
    
    为所有存储后端提供统一的接口，支持：
    - 连接测试和健康检查
    - 文件和目录的基本操作
    - 流式上传下载
    - 权限和空间信息管理
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化存储客户端
        
        Args:
            name: 存储配置名称
            config: 存储配置参数
        """
        self.name = name
        self.config = config
        self._connected = False
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        建立存储连接
        
        Returns:
            连接成功返回True
            
        Raises:
            StorageConnectionError: 连接失败
        """
        # logger.info(f"尝试连接存储客户端: {self.name}") 
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开存储连接"""
        pass
    
    @abstractmethod
    async def check_connection(self) -> Tuple[bool, Optional[str]]:
        """
        测试存储连接
        
        Returns:
            (连接状态, 错误信息)
            连接成功时错误信息为None
        """
        pass
    
    @abstractmethod
    async def info(self, path: str = "/") -> StorageInfo:
        """
        获取存储系统信息
        
        Args:
            path: 路径（用于获取特定路径的信息）
            
        Returns:
            存储系统信息
        """
        pass
    
    @abstractmethod
    async def list_dir(self, path: str = "/", depth: int = 1) -> List[StorageEntry]:
        """
        列出目录内容
        
        Args:
            path: 目录路径
            depth: 递归深度（默认1，仅当前目录）
            
        Returns:
            存储条目列表
            
        Raises:
            StorageNotFoundError: 路径不存在
            StoragePermissionError: 权限不足
        """
        pass
    
    @abstractmethod
    async def get_file_info(self, path: str) -> StorageEntry:
        """
        获取文件/目录详细信息
        
        Args:
            path: 文件或目录路径
            
        Returns:
            存储条目详细信息
            
        Raises:
            StorageNotFoundError: 路径不存在
        """
        pass
    
    @abstractmethod
    async def stat(self, path: str) -> StorageEntry:
        pass
    
    @abstractmethod
    async def download_iter(self, path: str, chunk_size: int = 64 * 1024, offset: int = 0) -> Iterator[bytes]:
        """
        流式下载文件
        
        Args:
            path: 文件路径
            chunk_size: 块大小（字节）
            offset: 起始偏移量（字节）
            
        Returns:
            文件数据迭代器
            
        Raises:
            StorageNotFoundError: 文件不存在
            StoragePermissionError: 读取权限不足
        """
        pass
    
    @abstractmethod
    async def upload(self, path: str, data: bytes, 
                    content_type: Optional[str] = None) -> bool:
        """
        上传文件
        
        Args:
            path: 目标路径
            data: 文件数据
            content_type: 内容类型（可选）
            
        Returns:
            上传成功返回True
            
        Raises:
            StoragePermissionError: 写入权限不足
            StorageError: 上传失败
        """
        pass
    
    @abstractmethod
    async def create_dir(self, path: str) -> bool:
        """
        创建目录
        
        Args:
            path: 目录路径
            
        Returns:
            创建成功返回True
            
        Raises:
            StoragePermissionError: 创建权限不足
            StorageError: 创建失败
        """
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        删除文件或目录
        
        Args:
            path: 要删除的路径
            
        Returns:
            删除成功返回True
            
        Raises:
            StorageNotFoundError: 路径不存在
            StoragePermissionError: 删除权限不足
        """
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        检查路径是否存在
        
        Args:
            path: 要检查的路径
            
        Returns:
            存在返回True
        """
        pass
    
    @abstractmethod
    async def move(self, source_path: str, dest_path: str) -> bool:
        """
        移动/重命名文件或目录
        
        Args:
            source_path: 源路径
            dest_path: 目标路径
            
        Returns:
            移动成功返回True
            
        Raises:
            StorageNotFoundError: 源路径不存在
            StoragePermissionError: 操作权限不足
        """
        pass
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()


class StorageClientFactory:
    """存储客户端工厂类"""
    
    _clients: Dict[str, type] = {}
    
    @classmethod
    def register(cls, storage_type: str, client_class: type):
        """注册存储客户端实现"""
        if not issubclass(client_class, StorageClient):
            raise ValueError(f"Client class must inherit from StorageClient")
        cls._clients[storage_type] = client_class
    
    @classmethod
    def create(cls, storage_type: str, name: str, config: Dict[str, Any]) -> StorageClient:
        """创建存储客户端实例"""
        if storage_type not in cls._clients:
            raise ValueError(f"Unsupported storage type: {storage_type}")
        
        client_class = cls._clients[storage_type]
        return client_class(name, config)
    
    @classmethod
    def get_supported_types(cls) -> List[str]:
        """获取支持的存储类型列表"""
        return list(cls._clients.keys())
