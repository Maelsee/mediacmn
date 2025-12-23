"""
存储配置相关请求/响应模型定义 - 支持不同类型存储的特定配置参数。
"""
from __future__ import annotations

from typing import Optional, Dict, Any, Union, List
from pydantic import BaseModel, Field, field_validator, validator, ConfigDict


# ============================================
# 基础存储配置模型
# ============================================

class BaseStorageConfig(BaseModel):
    """基础存储配置"""
    name: str = Field(..., description="存储配置名称")
    storage_type: str = Field(..., description="存储类型 (webdav/smb/local/cloud)")


# ============================================
# WebDAV 存储配置
# ============================================

class WebdavConfig(BaseModel):
    """WebDAV 存储特定配置"""
    hostname: str = Field(..., description="WebDAV服务器主机名（包含协议，如https://dav.example.com）")
    login: str = Field(..., description="登录用户名")
    password: str = Field(..., description="登录密码")
    root_path: str = Field(default="/", description="WebDAV根路径（默认为根目录）")
    select_path: List[str] = Field(default=[], description="用户在根路径的基础上选择的路径（默认为空）")
    
    # 连接配置
    timeout_seconds: int = Field(default=30, description="请求超时时间（秒）")
    verify_ssl: bool = Field(default=True, description="是否验证SSL证书")
    
    # 连接池配置
    pool_connections: int = Field(default=10, description="连接池连接数")
    pool_maxsize: int = Field(default=10, description="连接池最大连接数")
    
    # 重试配置
    retries_total: int = Field(default=3, description="重试总次数")
    retries_backoff_factor: float = Field(default=0.5, description="重试退避因子")
    retries_status_forcelist: str = Field(
        default="[429,500,502,503,504]", 
        description="强制重试的HTTP状态码列表（JSON格式）"
    )
    
    # 高级配置
    custom_headers: Optional[str] = Field(None, description="自定义HTTP头信息（JSON格式）")
    proxy_config: Optional[str] = Field(None, description="代理配置（JSON格式）")


class WebdavConfigUpdate(BaseModel):
    hostname: Optional[str] = Field(None, description="WebDAV服务器主机名")
    login: Optional[str] = Field(None, description="登录用户名")
    password: Optional[str] = Field(None, description="登录密码")
    root_path: Optional[str] = Field(None, description="WebDAV根路径")
    select_path: Optional[List[str]] = Field(None, description="选择路径")
    timeout_seconds: Optional[int] = Field(None, description="请求超时时间")
    verify_ssl: Optional[bool] = Field(None, description="是否验证SSL证书")
    pool_connections: Optional[int] = Field(None, description="连接池连接数")
    pool_maxsize: Optional[int] = Field(None, description="连接池最大连接数")
    retries_total: Optional[int] = Field(None, description="重试总次数")
    retries_backoff_factor: Optional[float] = Field(None, description="重试退避因子")
    retries_status_forcelist: Optional[str] = Field(None, description="强制重试的HTTP状态码列表")
    custom_headers: Optional[str] = Field(None, description="自定义HTTP头信息")
    proxy_config: Optional[str] = Field(None, description="代理配置")


# ============================================
# SMB 存储配置
# ============================================

class SmbConfig(BaseModel):
    """SMB/CIFS 存储特定配置"""
    server_host: str = Field(..., description="SMB服务器主机名或IP地址")
    server_port: int = Field(default=445, description="SMB服务器端口（默认445）")
    share_name: str = Field(..., description="共享名称")
    
    # 认证信息
    username: Optional[str] = Field(None, description="用户名（可选）")
    password: Optional[str] = Field(None, description="密码（可选）")
    domain: Optional[str] = Field(None, description="域/工作组（可选）")
    
    # 客户端配置
    client_name: str = Field(default="MEDIACMN", description="客户端名称")
    use_ntlm_v2: bool = Field(default=True, description="是否使用NTLMv2认证")
    sign_options: str = Field(default="auto", description="签名选项：auto|required|disabled")
    is_direct_tcp: bool = Field(default=True, description="是否使用Direct TCP协议")


class SmbConfigUpdate(BaseModel):
    server_host: Optional[str] = Field(None, description="SMB服务器主机名或IP地址")
    server_port: Optional[int] = Field(None, description="SMB服务器端口")
    share_name: Optional[str] = Field(None, description="共享名称")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    domain: Optional[str] = Field(None, description="域/工作组")
    client_name: Optional[str] = Field(None, description="客户端名称")
    use_ntlm_v2: Optional[bool] = Field(None, description="是否使用NTLMv2认证")
    sign_options: Optional[str] = Field(None, description="签名选项")
    is_direct_tcp: Optional[bool] = Field(None, description="是否使用Direct TCP协议")


# ============================================
# 本地存储配置
# ============================================

class LocalConfig(BaseModel):
    """本地目录存储特定配置"""
    # 基础路径配置
    base_path: str = Field(..., description="本地存储基础路径（绝对路径）")
    auto_create_dirs: bool = Field(default=True, description="是否自动创建缺失目录")
    
    # 符号链接配置
    use_symlinks: bool = Field(default=False, description="是否使用符号链接代替复制")
    follow_symlinks: bool = Field(default=False, description="扫描时是否跟随符号链接")
    
    # 扫描限制配置
    scan_depth_limit: int = Field(default=10, description="扫描深度限制（防止递归过深）")
    
    # 过滤配置
    exclude_patterns: Optional[str] = Field(
        None, 
        description="排除模式（JSON格式，支持通配符，如['*.tmp', '.git/*']）"
    )


class LocalConfigUpdate(BaseModel):
    base_path: Optional[str] = Field(None, description="本地存储基础路径")
    auto_create_dirs: Optional[bool] = Field(None, description="是否自动创建缺失目录")
    use_symlinks: Optional[bool] = Field(None, description="是否使用符号链接代替复制")
    follow_symlinks: Optional[bool] = Field(None, description="扫描时是否跟随符号链接")
    scan_depth_limit: Optional[int] = Field(None, description="扫描深度限制")
    exclude_patterns: Optional[str] = Field(None, description="排除模式")


# ============================================
# 云盘存储配置
# ============================================

class CloudConfig(BaseModel):
    """云盘存储特定配置"""
    # 云盘提供商
    cloud_provider: str = Field(
        ..., 
        description="云盘提供商：aliyun|baidu|onedrive|google|dropbox|other"
    )
    
    # 认证信息
    access_token: Optional[str] = Field(None, description="访问令牌（敏感信息）")
    refresh_token: Optional[str] = Field(None, description="刷新令牌")
    client_id: Optional[str] = Field(None, description="客户端ID")
    client_secret: Optional[str] = Field(None, description="客户端密钥")
    
    # 云盘特定配置
    root_folder_id: Optional[str] = Field(None, description="根文件夹ID")
    sync_interval: int = Field(default=300, description="同步间隔（秒）")
    max_file_size: int = Field(default=1024*1024*100, description="最大文件大小（字节）")


class CloudConfigUpdate(BaseModel):
    cloud_provider: Optional[str] = Field(None, description="云盘提供商")
    access_token: Optional[str] = Field(None, description="访问令牌")
    refresh_token: Optional[str] = Field(None, description="刷新令牌")
    client_id: Optional[str] = Field(None, description="客户端ID")
    client_secret: Optional[str] = Field(None, description="客户端密钥")
    root_folder_id: Optional[str] = Field(None, description="根文件夹ID")
    sync_interval: Optional[int] = Field(None, description="同步间隔")
    max_file_size: Optional[int] = Field(None, description="最大文件大小")


# ============================================
# 统一的创建请求模型
# ============================================

class CreateStorageRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    storage_type: str 
    # 使用 Discriminated Unions 提高校验效率
    config: Union[WebdavConfig, SmbConfig, LocalConfig, CloudConfig]

    @field_validator('storage_type')
    def validate_type(cls, v):
        if v not in ['webdav', 'smb', 'local', 'cloud']:
            raise ValueError("Invalid storage type")
        return v


# ============================================
# 响应模型
# ============================================

class CreateStorageResponse(BaseModel):
    """创建存储配置响应"""
    id: int = Field(..., description="存储配置ID")
    name: str = Field(..., description="存储配置名称")
    storage_type: str = Field(..., description="存储类型")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    
    model_config = ConfigDict(from_attributes=True)


# ============================================
# 更新请求模型
# ============================================

class UpdateStorageRequest(BaseModel):
    name: Optional[str] = Field(None, description="存储配置名称")
    is_active: Optional[bool] = Field(None, description="是否激活")
    priority: Optional[int] = Field(None, description="优先级")
    config: Optional[Union[WebdavConfigUpdate, SmbConfigUpdate, LocalConfigUpdate, CloudConfigUpdate]] = Field(
        None, description="存储类型特定的配置参数")
    
    model_config = ConfigDict(extra="forbid")

# 列出用户存储配置响应模型
class ListUserStoragesResponse(BaseModel):
    id : int = Field(None, description="存储配置ID")
    user_id: int = Field(None, description="用户ID")
    name: str = Field(None, description="配置名称")
    storage_type: str = Field(None, description="存储类型")
    status: Optional[str] = Field(None, description="连接状态")
                
