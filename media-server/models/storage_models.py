"""
存储配置相关模型集合

该文件包含所有存储配置相关的模型类，统一管理不同类型的存储配置、状态监控和扫描任务。
"""

from typing import Optional, List
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint, String


# ============================================
# 基础存储配置模型
# ============================================

class StorageConfig(SQLModel, table=True):
    """存储配置基类模型 - 统一管理所有存储类型的配置"""
    
    __tablename__ = "storage_config"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_storage_config_user_name"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True, description="存储配置唯一标识")
    user_id: int = Field(index=True, foreign_key="users.id", description="所属用户ID")
    name: str = Field(index=True, description="存储配置名称（用户自定义标识）")
    
    storage_type: str = Field(
        sa_type=String(20),
        description="存储类型：webdav|smb|local|cloud"
    )
    
    is_active: bool = Field(default=True, description="配置是否激活（True激活，False禁用）")
    # is_online: bool = Field(default=False, description="配置是否在线（True已连接，False未连接）")
    priority: int = Field(default=100, description="优先级（数值越小优先级越高）")
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="配置创建时间（UTC时间）"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="配置最后更新时间（UTC时间）"
    )
    
    # 关系定义
    webdav_config: Optional["WebdavStorageConfig"] = Relationship(back_populates="storage_config")
    smb_config: Optional["SmbStorageConfig"] = Relationship(back_populates="storage_config")
    local_config: Optional["LocalStorageConfig"] = Relationship(back_populates="storage_config")
    cloud_config: Optional["CloudStorageConfig"] = Relationship(back_populates="storage_config")
    status: Optional["StorageStatus"] = Relationship(back_populates="storage_config")
    scan_tasks: List["StorageScanTask"] = Relationship(back_populates="storage_config")
    
    def __repr__(self):
        return f"<StorageConfig(id={self.id}, name='{self.name}', type='{self.storage_type}')>"


# ============================================
# WebDAV 存储配置
# ============================================

class WebdavStorageConfig(SQLModel, table=True):
    """WebDAV存储配置模型 - 适配新的存储配置架构"""
    
    __tablename__ = "webdav_storage_config"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="WebDAV配置唯一标识")
    storage_config_id: int = Field(foreign_key="storage_config.id", description="关联的存储配置ID")
    
    # WebDAV服务器连接信息
    hostname: str = Field(description="WebDAV服务器主机名（包含协议，如https://dav.example.com:5244）")
    login: str = Field(description="登录用户名")
    password: str = Field(description="登录密码")
    root_path: str = Field(default="/", description="WebDAV根路径（默认为根目录）")
    select_path: str = Field(default="[]", description="用户在根路径的基础上选择的路径（JSON格式，默认为空列表）")
    
    
    # 连接配置
    timeout_seconds: int = Field(default=30, description="请求超时时间（秒）")
    verify_ssl: bool = Field(default=True, description="是否验证SSL证书（True验证，False跳过验证）")
    
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
    custom_headers: Optional[str] = Field(
        default=None, 
        description="自定义HTTP头信息（JSON格式）"
    )
    proxy_config: Optional[str] = Field(
        default=None, 
        description="代理配置（JSON格式）"
    )
    
    # 关系
    storage_config: StorageConfig = Relationship(back_populates="webdav_config")
    
    def __repr__(self):
        return f"<WebdavStorageConfig(id={self.id}, hostname='{self.hostname}')>"


# ============================================
# SMB 存储配置
# ============================================

class SmbStorageConfig(SQLModel, table=True):
    """SMB/CIFS存储配置模型"""
    
    __tablename__ = "smb_storage_config"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="SMB配置唯一标识")
    storage_config_id: int = Field(foreign_key="storage_config.id", description="关联的存储配置ID")
    
    # SMB服务器连接信息
    server_host: str = Field(description="SMB服务器主机名或IP地址")
    server_port: int = Field(default=445, description="SMB服务器端口（默认445）")
    share_name: str = Field(description="共享名称")
    
    # 认证信息
    username: Optional[str] = Field(default=None, description="用户名（可选）")
    password: Optional[str] = Field(default=None, description="密码（可选）")
    domain: Optional[str] = Field(default=None, description="域/工作组（可选）")
    
    # 客户端配置
    client_name: str = Field(default="MEDIACMN", description="客户端名称")
    use_ntlm_v2: bool = Field(default=True, description="是否使用NTLMv2认证")
    sign_options: str = Field(default="auto", description="签名选项：auto|required|disabled")
    is_direct_tcp: bool = Field(default=True, description="是否使用Direct TCP协议")
    
    # 关系
    storage_config: StorageConfig = Relationship(back_populates="smb_config")
    
    def __repr__(self):
        return f"<SmbStorageConfig(id={self.id}, server='{self.server_host}', share='{self.share_name}')>"


# ============================================
# 本地存储配置
# ============================================

class LocalStorageConfig(SQLModel, table=True):
    """本地目录存储配置模型"""
    
    __tablename__ = "local_storage_config"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="本地存储配置唯一标识")
    storage_config_id: int = Field(foreign_key="storage_config.id", description="关联的存储配置ID")
    
    # 基础路径配置
    base_path: str = Field(description="本地存储基础路径（绝对路径）")
    auto_create_dirs: bool = Field(default=True, description="是否自动创建缺失目录")
    
    # 符号链接配置
    use_symlinks: bool = Field(default=False, description="是否使用符号链接代替复制")
    follow_symlinks: bool = Field(default=False, description="扫描时是否跟随符号链接")
    
    # 扫描限制配置
    scan_depth_limit: int = Field(default=10, description="扫描深度限制（防止递归过深）")
    
    # 过滤配置
    exclude_patterns: Optional[str] = Field(
        default=None, 
        description="排除模式（JSON格式，支持通配符，如['*.tmp', '.git/*']）"
    )
    
    # 关系
    storage_config: StorageConfig = Relationship(back_populates="local_config")
    
    def __repr__(self):
        return f"<LocalStorageConfig(id={self.id}, path='{self.base_path}')>"


# ============================================
# 云盘存储配置
# ============================================

class CloudStorageConfig(SQLModel, table=True):
    """云盘存储配置模型"""
    
    __tablename__ = "cloud_storage_config"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="云盘存储配置唯一标识")
    storage_config_id: int = Field(foreign_key="storage_config.id", description="关联的存储配置ID")
    
    # 云盘提供商
    cloud_provider: str = Field(
        description="云盘提供商：aliyun|baidu|onedrive|google|dropbox|other"
    )
    
    # 认证信息
    access_token: Optional[str] = Field(default=None, description="访问令牌（敏感信息）")
    refresh_token: Optional[str] = Field(default=None, description="刷新令牌（敏感信息）")
    token_expiry: Optional[datetime] = Field(default=None, description="令牌过期时间")
    
    # OAuth配置
    client_id: Optional[str] = Field(default=None, description="客户端ID")
    client_secret: Optional[str] = Field(default=None, description="客户端密钥（敏感信息）")
    
    # 云盘路径配置
    remote_root_path: str = Field(default="/", description="云盘根路径")
    
    # 传输配置
    chunk_size_mb: int = Field(default=100, description="分块上传大小（MB）")
    max_concurrent_uploads: int = Field(default=3, description="最大并发上传数")
    max_concurrent_downloads: int = Field(default=5, description="最大并发下载数")
    
    # 特定云盘配置（JSON格式）
    provider_specific_config: Optional[str] = Field(
        default=None, 
        description="特定云盘配置（JSON格式，存储各云盘特有配置）"
    )
    
    # 关系
    storage_config: StorageConfig = Relationship(back_populates="cloud_config")
    
    def __repr__(self):
        return f"<CloudStorageConfig(id={self.id}, provider='{self.cloud_provider}')>"


# ============================================
# 存储状态监控
# ============================================

class StorageStatus(SQLModel, table=True):
    """存储状态监控模型 - 实时监控存储可用性和状态"""
    
    __tablename__ = "storage_status"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="存储状态记录唯一标识")
    storage_id: int = Field(index=True, foreign_key="storage_config.id", description="关联的存储配置ID")
    
    # 状态信息
    status: str = Field(
        description="存储状态：online（在线）|offline（离线）|error（错误）|scanning（扫描中）"
    )
    
    # 时间记录
    last_check_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="最后检查时间（UTC时间）"
    )
    last_success_time: Optional[datetime] = Field(
        default=None, description="最后成功连接时间（UTC时间）"
    )
    
    # 性能指标
    connection_latency_ms: Optional[int] = Field(
        default=None, description="连接延迟（毫秒）"
    )
    available_space_bytes: Optional[int] = Field(
        default=None, description="可用空间（字节）"
    )
    total_space_bytes: Optional[int] = Field(
        default=None, description="总空间（字节）"
    )
    
    # 扫描进度
    scan_progress_percent: float = Field(
        default=0.0, description="扫描进度百分比（0-100）"
    )
    
    # 错误信息
    last_error_message: Optional[str] = Field(
        default=None, description="最后错误信息"
    )
    error_count: int = Field(
        default=0, description="连续错误次数"
    )
    
    # 关系
    storage_config: StorageConfig = Relationship(back_populates="status")
    
    def __repr__(self):
        return f"<StorageStatus(id={self.id}, storage_id={self.storage_id}, status='{self.status}')>"


# ============================================
# 存储扫描任务
# ============================================

class StorageScanTask(SQLModel, table=True):
    """存储扫描任务模型 - 管理各存储源的扫描任务"""
    
    __tablename__ = "storage_scan_task"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="存储扫描任务唯一标识")
    
    # 关联信息
    storage_id: int = Field(index=True, foreign_key="storage_config.id", description="关联的存储配置ID")
    scan_job_id: Optional[int] = Field(default=None, foreign_key="scan_job.id", description="关联的扫描作业ID（可选）")
    
    # 扫描配置
    scan_path: Optional[str] = Field(default=None, description="扫描路径（相对存储根路径）")
    scan_type: str = Field(
        default="full", 
        description="扫描类型：full（全量）|incremental（增量）|quick（快速）"
    )
    
    # 过滤配置
    file_patterns: str = Field(
        default="*", 
        description="文件匹配模式（JSON格式，如['*.mp4', '*.mkv']）"
    )
    exclude_patterns: Optional[str] = Field(
        default=None, 
        description="排除模式（JSON格式，如['*.tmp', '.git/*']）"
    )
    
    # 时间记录
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="任务创建时间（UTC时间）"
    )
    started_at: Optional[datetime] = Field(
        default=None, description="任务开始时间（UTC时间）"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="任务完成时间（UTC时间）"
    )
    
    # 状态信息
    status: str = Field(
        default="pending",
        description="任务状态：pending（待处理）|running（运行中）|completed（已完成）|failed（失败）"
    )
    
    # 进度统计
    files_found: int = Field(default=0, description="发现的文件数")
    files_processed: int = Field(default=0, description="处理的文件数")
    files_added: int = Field(default=0, description="新增的文件数")
    files_updated: int = Field(default=0, description="更新的文件数")
    files_removed: int = Field(default=0, description="移除的文件数")
    
    # 错误信息
    error_message: Optional[str] = Field(default=None, description="错误信息")
    
    # 关系
    storage_config: StorageConfig = Relationship(back_populates="scan_tasks")
    
    def __repr__(self):
        return f"<StorageScanTask(id={self.id}, storage_id={self.storage_id}, status='{self.status}')>"
