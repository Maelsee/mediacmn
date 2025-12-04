"""模型包初始化。

该包包含所有数据库模型定义，按功能模块组织：
- 基础模型：用户、扫描任务等
- 媒体模型：媒体核心、电影、电视剧、文件资产等  
- 存储模型：存储配置、状态监控、扫描任务等
"""

# ============================================
# 基础模型
# ============================================
from .user import User  # noqa: F401

# ============================================
# 媒体相关模型（新的统一组织）
# ============================================
from .media_models import (  # noqa: F401
    # 媒体核心模型
    MediaCore,
    MediaVersion,
    # 电影扩展模型
    MovieExt,
    # 剧集扩展模型
    TVSeriesExt,
    SeasonExt,
    EpisodeExt,
    # 文件资源模型
    FileAsset,
    # 艺术作品模型
    Artwork,
    # 外部ID模型
    ExternalID,
    # 流派模型
    Genre,
    MediaCoreGenre,
    # 人员信用模型
    Person,
    Credit
)

# ============================================
# 存储配置模型（新的统一组织）
# ============================================
from .storage_models import (  # noqa: F401
    StorageConfig,
    WebdavStorageConfig,
    SmbStorageConfig, 
    LocalStorageConfig,
    CloudStorageConfig,
    StorageStatus,
    StorageScanTask
)

# ============================================
# 向后兼容导入（保持现有代码兼容性）
# ============================================
# 存储配置模型别名（保持向后兼容）
StorageConfig = StorageConfig  # 避免循环导入警告
WebdavStorageConfig = WebdavStorageConfig
SmbStorageConfig = SmbStorageConfig
LocalStorageConfig = LocalStorageConfig
CloudStorageConfig = CloudStorageConfig
StorageStatus = StorageStatus
StorageScanTask = StorageScanTask

# 媒体模型别名（保持向后兼容）
# 注意：以下独立模型文件将在后续清理中移除
# 目前通过别名保持向后兼容，但建议使用新的统一导入
MediaCore = MediaCore
MediaVersion = MediaVersion
MovieExt = MovieExt
TVSeriesExt = TVSeriesExt
SeasonExt = SeasonExt
EpisodeExt = EpisodeExt
FileAsset = FileAsset
Artwork = Artwork
ExternalID = ExternalID
Genre = Genre
MediaCoreGenre = MediaCoreGenre
Person = Person
Credit = Credit
