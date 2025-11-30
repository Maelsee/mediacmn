# 后端架构重构设计方案 (2025)

## 1. 概述

本设计方案旨在解决当前 `media-server` 后端存在的耦合度高、扩展性差的问题。主要目标包括：
1.  **存储与扫描解耦**：支持 WebDAV, SMB, 本地存储, 云盘等多种存储后端。
2.  **扫描与丰富化解耦**：实现基于事件或队列的异步处理，提高系统吞吐量。
3.  **丰富化扩展性**：支持综艺、动漫、音乐等多种媒体类型的元数据刮削。
4.  **持久化与数据库扩展性**：设计灵活的数据库架构和持久化策略，适应未来业务增长。

---

## 2. 存储与扫描解耦 (Storage Provider Pattern)

### 2.1 现状问题
目前 `enhanced_async_scan_service.py` 和底层扫描逻辑可能与 WebDAV 客户端强绑定，导致无法轻易接入 SMB 或本地文件系统。

### 2.2 解决方案：存储抽象层 (Storage Abstraction Layer)
引入 `StorageProvider` 接口，所有具体存储（WebDAV, SMB, Local）均实现该接口。扫描服务仅依赖该接口。

#### 2.2.1 接口定义 (Python Protocol)

```python
from typing import Protocol, List, Optional, AsyncIterator
from dataclasses import dataclass
from datetime import datetime

@dataclass
class FileEntry:
    path: str
    name: str
    size: int
    is_dir: bool
    modified_time: datetime
    etag: Optional[str] = None

class StorageProvider(Protocol):
    """存储提供者接口"""
    
    async def connect(self) -> bool:
        """连接存储"""
        ...

    async def list_files(self, path: str, recursive: bool = False) -> AsyncIterator[FileEntry]:
        """列出文件"""
        ...

    async def get_file_info(self, path: str) -> Optional[FileEntry]:
        """获取文件详情"""
        ...
        
    async def exists(self, path: str) -> bool:
        """检查是否存在"""
        ...
```

#### 2.2.2 架构变更
- **Current**: `ScanService` -> `WebDAVClient`
- **New**: `ScanService` -> `StorageProviderFactory` -> `StorageProvider` (WebDAV/SMB/Local)

---

## 3. 扫描与丰富化解耦 (Event-Driven Architecture)

### 3.1 现状问题
`enhanced_async_scan_service.py` 在扫描流程中直接调用 `create_metadata_task` 或混合逻辑，导致扫描速度受限于元数据刮削速度，且逻辑耦合。

### 3.2 解决方案：生产者-消费者模型

#### 3.2.1 流程设计
1.  **Scanning Phase (Producer)**: 扫描服务只负责遍历文件系统，对比数据库差异。
    - 新增文件 -> 发布 `FileDiscoveredEvent` 或推入 `ScanQueue`。
    - 删除文件 -> 发布 `FileDeletedEvent`。
2.  **Dispatching Phase**: 任务调度器消费事件。
3.  **Enrichment Phase (Consumer)**: 独立的 Worker 进程/协程监听队列，执行元数据刮削。

#### 3.2.2 队列设计
建议复用现有的 `UnifiedTaskScheduler`，但明确分离队列：
- `queue:file_scan`: 仅处理文件系统遍历 (High Priority)。
- `queue:metadata_fetch`: 处理元数据刮削 (Normal Priority)。
- `queue:image_download`: 处理图片下载 (Low Priority)。

---

## 4. 丰富化扩展性 (Strategy Pattern)

### 4.1 现状问题
`MetadataEnricher` 中充斥着 `if media_type == MOVIE: ... elif media_type == TV: ...` 的硬编码逻辑，难以添加"综艺"或"动漫"。

### 4.2 解决方案：元数据策略模式

#### 4.2.1 策略接口

```python
class IMetadataStrategy(ABC):
    @abstractmethod
    async def search(self, query: str, year: Optional[int] = None) -> List[SearchResult]:
        pass
        
    @abstractmethod
    async def fetch_details(self, external_id: str, provider: str) -> MediaDetail:
        pass
        
    @abstractmethod
    def get_supported_type(self) -> MediaType:
        pass
```

#### 4.2.2 实现类
- `MovieStrategy`: 处理电影。
- `TVSeriesStrategy`: 处理剧集。
- `VarietyStrategy`: 处理综艺（可能需要基于日期的集数逻辑）。
- `AnimeStrategy`: 处理动漫（可能需要绝对集数逻辑）。

#### 4.2.3 上下文管理
`MetadataEnricher` 转变为 `EnrichmentContext`，根据文件名解析结果或用户指定类型，从 `StrategyFactory` 获取对应策略执行。

---

## 5. 数据库与持久化扩展 (Polymorphism & Schema Design)

### 5.1 现状问题
`MediaCore` 表虽然通用，但扩展表 (`MovieExt`, `TVSeriesExt`) 是硬编码的。持久化服务 `metadata_persistence_service.py` 也是硬编码的大量 `if/else`。

### 5.2 解决方案：组合模式与数据映射器

#### 5.2.1 数据库模型优化
保持 `MediaCore` 作为核心索引表，引入更灵活的扩展机制：

1.  **Core Table (`media_core`)**: 保持不变，存储 `title`, `year`, `kind`, `poster` 等通用展示字段。
2.  **Generic Extension (`media_attributes`)**: (可选方案) 使用 EAV 模型存储非结构化属性。
    - `core_id`, `key`, `value`, `type`
3.  **Specialized Extensions**: 继续使用独立表，但通过注册机制管理。
    - `VarietyExt`: `host`, `guest`, `air_date`
    - `AnimeExt`: `studio`, `absolute_episode`

#### 5.2.2 持久化层重构 (Persistence Mappers)

```python
class BasePersistenceMapper(Generic[T]):
    def save(self, session, core: MediaCore, data: T):
        # 保存通用 Core 信息
        self._save_core(session, core, data)
        # 钩子方法：保存特定扩展
        self._save_extension(session, core, data)

class VarietyMapper(BasePersistenceMapper[VarietyDetail]):
    def _save_extension(self, session, core, data):
        # 保存综艺特有信息到 VarietyExt
        pass
```

`MetadataPersistenceService` 维护一个 `Dict[MediaType, BasePersistenceMapper]` 注册表，根据数据类型自动分发。

---

## 6. 总结：重构路线图

1.  **Phase 1 (基础解耦)**: 提取 `StorageProvider` 接口，重构扫描服务。
2.  **Phase 2 (流程异步化)**: 完善 `TaskScheduler`，拆分扫描与丰富化队列。
3.  **Phase 3 (丰富化重构)**: 实现 `IMetadataStrategy`，重构 `MetadataEnricher`。
4.  **Phase 4 (持久化重构)**: 引入 Mapper 模式，重构 `MetadataPersistenceService`，并新增综艺/动漫支持。

此文档为架构设计的蓝图，后续代码实现需严格遵循此规范。
