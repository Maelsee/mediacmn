# ADR-001 存储与扫描解耦方案

## 结论
- 目前已基本实现对存储后端的抽象与解耦（统一 `StorageClient`、工厂模式、服务层封装），但扫描引擎仍存在跨层依赖与接口漂移，尚未达到“扫描仅依赖稳定契约”的理想状态。

## 现状概览
- 存储抽象：统一抽象在 `media-server/services/storage/storage_client.py`，基类 `StorageClient`（66）定义核心能力，工厂 `StorageClientFactory`（279）负责注册与创建。
- 客户端实现：`WebDAVStorageClient`（media-server/services/storage/storage_clients/webdav_client.py）与 `LocalStorageClient`、`SMBStorageClient` 分别实现接口。
- 服务层：`StorageService`（media-server/services/storage/storage_service.py）负责按用户与配置创建并缓存客户端，提供 `ensure_client()` 与 `get_client()` 简化获取。
- 扫描引擎：`UnifiedScanEngine.scan_storage()`（media-server/services/scan/unified_scan_engine.py:485）通过 `StorageService.get_client()`（storage_service.py:369）获取客户端并驱动扫描逻辑。

## 主要耦合点与缺陷
- 接口漂移：扫描处理器调用了基类未声明的方法与参数
  - `stat()`：`FileAssetProcessor._calculate_file_hash()` 调用 `storage_client.stat(file_path)`（media-server/services/scan/unified_scan_engine.py:227），但基类未定义该方法。
  - `download_iter(offset=...)`：处理器使用了偏移参数（251），但基类 `download_iter()` 未声明 `offset`（storage_client.py:167）。
- 服务定位器耦合：扫描引擎直接依赖 `StorageService` 获取客户端（unified_scan_engine.py:507），而非通过外部注入，降低可测试性与替换性。
- 跨层持久化耦合：处理器直接使用数据库会话与 ORM 模型（如 `FileAsset` 的查询、更新与创建），使扫描与存储持久化逻辑强耦合，难以复用与单测。
- 路径语义不统一：不同后端的 `path` 可能携带不同基路径语义，扫描层需要稳定的“规范化路径”约束以避免后续处理混乱。

## 目标
- 扫描引擎仅依赖稳定契约：`StorageClient` 能力 + `FileAssetRepository` 能力 + `ScanProcessor` 能力。
- 消除服务定位器耦合，改为构造器/方法注入。
- 统一流式与文件信息的最小必要契约，避免实现分歧。
- 提升可测试性：可用内存存储或假实现替换后端与持久层进行单元测试。

## 解耦设计方案
- 契约统一
  - 将 `StorageClient` 的最小能力稳定化：
    - `get_file_info(path) -> StorageEntry`（已有），新增显式别名 `stat(path) -> StorageEntry` 或在基类中将 `stat` 设为抽象，以统一调用。
    - `download_iter(path, chunk_size=64*1024, offset=0) -> Iterator[bytes]` 在基类中声明 `offset` 参数，体现断点能力；对不支持偏移的实现，文档化回退策略。
    - 在 `StorageInfo` 中明确 `supports_resume: bool` 与可选 `supports_range: bool`，指导调用方是否可安全使用 `offset`。
  - 规范化路径类型：约定 `StorageEntry.path` 为“后端根相对路径”，由服务层处理远端基路径拼接，扫描层不再拼接 URL。
- 依赖注入
  - `UnifiedScanEngine` 构造器接收 `StorageClient` 与 `FileAssetRepository`（接口）实例；或 `scan_storage(storage_client, repo, ...)` 方法参数注入，避免直接依赖 `StorageService` 与 ORM。
  - 新增 `FileAssetRepository` 接口，定义：`find_by_hash(hash)`, `find_by_path(path)`, `create(entry, info, hash)`, `update(file, entry)` 等方法；提供 SQLAlchemy 实现。
- 分层职责
  - `StorageService` 负责从配置与用户上下文创建 `StorageClient`，并作为编排层在路由/任务入口处注入给扫描引擎。
  - `UnifiedScanEngine` 专注扫描、分类与调用处理器链，不直接做数据库会话管理。
  - `ScanProcessor` 保持插件化，不触达持久化层；将变更通过引擎统一提交给 `FileAssetRepository`。
- 统一能力标识
  - 在 `StorageClient.info()` 返回的 `StorageInfo` 增加能力位，驱动引擎是否进行偏移读取或完整读取的策略选择。

## 参考代码位置
- 抽象与工厂：`media-server/services/storage/storage_client.py:66,167,279`
- 服务层获取客户端：`media-server/services/storage/storage_service.py:110,147,369`
- 扫描引擎入口与调用：`media-server/services/scan/unified_scan_engine.py:485,507,512`
- 接口漂移样例：`media-server/services/scan/unified_scan_engine.py:227,251`

## 渐进式改造步骤（建议）
1. 在基类中补齐契约：为 `StorageClient` 增加 `stat(path)` 与 `download_iter(..., offset=0)` 的抽象签名；将各实现同步适配。
2. 在 `UnifiedScanEngine` 中去掉对 `StorageService` 的直接依赖，改为方法参数注入 `storage_client` 与 `repo`。
3. 抽出 `FileAssetRepository` 接口与 SQLAlchemy 适配层，替换现有会话内联操作。
4. 引入路径规范化工具，确保不同后端的 `path` 语义一致。
5. 编写替身实现（内存存储、内存仓储）并补充单元测试，覆盖：小文件完整哈希、大文件分段读取、增量更新等。

## 验收标准
- 扫描引擎不再直接引用 `StorageService` 与 ORM 模型；仅通过接口交互。
- 基类与实现对 `stat` 与 `offset` 能力一致，行为可通过 `StorageInfo` 能力位配置。
- 路由与任务入口处以编排方式注入依赖，支持更换后端与仓储实现进行测试。
- 单元测试可在无真实后端与数据库的情况下跑通核心逻辑。

## 风险与回退
- 基类签名变更需要同步调整所有实现；可先通过向后兼容的默认参数与方法别名平滑过渡。
- 处理器链改造需逐步替换数据库访问为仓储接口，建议以适配层方式先行包裹现有逻辑。

## 后续工作
- 形成接口文档与示例实现，补充端到端测试脚本；必要时在 `DEVELOPMENT.md` 新增“契约与依赖注入约定”章节进行团队对齐。
