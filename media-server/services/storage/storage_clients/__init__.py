"""
存储客户端实现包

提供各种存储后端的统一客户端实现
"""

# 延迟导入以避免循环依赖
def _register_clients():
    """注册所有存储客户端到工厂"""
    from ..storage_client import StorageClientFactory
    from .webdav_client import WebDAVStorageClient
    from .smb_client import SMBStorageClient
    from .local_client import LocalStorageClient
    
    StorageClientFactory.register("webdav", WebDAVStorageClient)
    StorageClientFactory.register("smb", SMBStorageClient)
    StorageClientFactory.register("local", LocalStorageClient)

# 在首次导入时注册客户端
_register_clients()

# 导出客户端类和工厂
from ..storage_client import StorageClientFactory
from .webdav_client import WebDAVStorageClient
from .smb_client import SMBStorageClient
from .local_client import LocalStorageClient

__all__ = ['StorageClientFactory', 'WebDAVStorageClient', 'SMBStorageClient', 'LocalStorageClient']