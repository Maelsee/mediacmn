# 并发与部署建议（草稿）

本章节用于指导团队在多租户场景下，如何安全、可预期地扩容后端服务，特别是任务队列（Dramatiq）、异步数据库、刮削器与扫描/持久化链路的并发配置。

## 1. 整体并发模型

### 1.1 基本原则

- **单机内优先使用「多进程 + 单线程 + async」模型**：  
  通过 `--processes N --threads 1` 结合服务内部的 async 并发（`asyncio`、`max_concurrency`、异步数据库）来扩容。
- **避免在当前架构下启用 Dramatiq 多线程**：  
  目前存在大量全局单例 + `asyncio.Lock`/Task 的组合（如 `ScraperManager`），多线程会引入跨线程事件循环问题。
- **多租户隔离依赖 user_id**：  
  所有核心表与任务都应带 `user_id`，不同用户之间的数据天然分区，冲突主要集中在「同一用户 + 同一部剧/电影」的并发写入上。

### 1.2 推荐基础配置

- 开发 / 小规模部署：
  - Dramatiq：`dramatiq services.task.consumers --processes 2 --threads 1`
- 生产单机：
  - Dramatiq：`dramatiq services.task.consumers --processes 4 --threads 1`
  - 根据 CPU/内存与数据库承载能力，可提高到 `--processes 6~8`，每次调参后观察数据库连接数与负载。

## 2. 任务队列与多租户

### 2.1 任务维度

- 核心任务类型：
  - `scan`：扫描存储并写入 FileAsset
  - `metadata`：元数据丰富化（调用刮削器 + 解析文件命名）
  - `persist`：单文件元数据持久化
  - `persist_batch`：批量元数据持久化
  - `delete`：清理已删除文件与孤立核心数据
  - `localize`：侧车本地化任务

### 2.2 多租户并发注意点

- 不同用户之间：可以放心并行，不会在行级产生冲突。
- 同一用户内部：
  - 同一部剧/电影的多个文件（多版本、多集）可能同时触发「创建或更新同一个 MediaCore / Series / Season / Episode」。
  - 需要通过数据库唯一约束 + 幂等键 + 适度序列化来避免重复插入或死锁。

## 3. 各服务并发与部署策略

### 3.1 存储服务（`services/storage`）

- 代表文件：`services/storage/storage_service.py`
- 特点：
  - 使用 `AsyncSessionLocal` 获取异步数据库配置。
  - `StorageService` 为单例，但当前 `get_client(storage_id)` 每次都会创建新的客户端对象，不共享连接。
- 部署建议：
  - **不需要依赖 Dramatiq 多线程提速**，存储侧 I/O 并发主要通过上层 Scan 引擎内部的 async 协程实现。
  - 如未来恢复「客户端连接池 + 缓存」，需要特别注意：
    - **不要在单例上存放跨线程共享的 `asyncio.Lock`**。
    - 如需跨任务串行化连接，应使用进程内 async 锁，而非跨线程共享锁。

### 3.2 刮削器管理（`services/scraper`）

- 代表文件：`services/scraper/manager.py`
- 特点：
  - `ScraperManager` 是全局单例 `scraper_manager`。
  - 内部维护：
    - `_op_lock: asyncio.Lock`
    - `_inflight: Dict[Tuple[Any, ...], asyncio.Task]` + `_inflight_lock: asyncio.Lock`
    - 本地详情缓存 `_LocalDetailCache` 与可选 Redis 缓存。
- 并发行为：
  - 在单线程事件循环内，通过 async 并发（`asyncio.gather`、singleflight 去重）放大刮削吞吐。
- 线程安全风险：
  - `asyncio.Lock` 与 `Task` 均绑定某个事件循环，**不能跨线程使用**。
  - 若 Dramatiq 开启 `--threads > 1`，多个线程共用同一个 `scraper_manager`，会出现「锁/任务绑定到不同 loop」的错误。
- 部署建议：
  - **强烈建议在当前设计下保持 `--threads 1`**。
  - 如需进一步放大刮削能力：
    - 提高 `metadata_enricher` 中使用 `ScraperManager` 的 async 并发参数（例如批内 `max_concurrency`）。
    - 水平扩展 Dramatiq 进程数或节点数。
  - 若未来要支持多线程：
    - 需要重构 `ScraperManager`，避免在单例中使用 `asyncio.Lock` 和跨线程 Task 缓存。

### 3.3 元数据丰富化（`metadata_enricher.py`）

- 代表文件：`services/media/metadata_enricher.py`
- 特点：
  - 使用 `AsyncSessionLocal` 查询 FileAsset 与用户语言。
  - 按父目录分组（同一剧集/电影目录作为一组），使用 async 并发 + 信号量控制并发度：
    - `iter_enrich_multiple_files` 提供流式异步迭代接口。
  - 落地例子：`metadata_worker` 通过 `async for` 流式消费结果，边丰富边派发持久化任务。
- 并发策略：
  - 推荐通过 `max_concurrency` 控制 enrichment 内部的并发度。
  - 不需要依赖 Dramatiq 多线程，**一个线程内的 async 协程并发足以支撑高吞吐**。
- 部署建议：
  - 保持 `--threads 1`。
  - 根据 CPU 与外部 API 限流调整：
    - `max_concurrency=10~20`：在刮削 API 有 QPS 限制时适度减小。
    - 批大小由调用方（例如 `metadata_worker`）控制，以防一次性 enrich 太多文件。

### 3.4 元数据持久化（`metadata_persistence_service.py` & async 版）

- 代表文件：
  - 同步核心：`services/media/metadata_persistence_service.py`
  - 异步包装：`services/media/metadata_persistence_async_service.py`
- 特点：
  - 同步核心实现了复杂的电影/剧集/季/集/人员/海报等映射逻辑。
  - 异步版通过 `AsyncSessionLocal` + `run_sync` 复用现有逻辑：
    - `apply_metadata_single`：单条持久化。
    - `apply_metadata_batch`：批量持久化。
- 并发风险：
  - **数据库层面**：
    - 同一用户下，同一部剧/电影的多个任务可能并发写同一个 `MediaCore` 或 `ExternalID`。
    - 批量持久化是长事务，可能持有多个核心行的锁，增加锁等待与死锁概率。
  - **线程安全层面**：
    - 当前实现中每次调用都从 `AsyncSessionLocal` 创建独立 session，不在线程间共享，线程安全。
- 部署与扩容建议：
  - 主要通过以下方式扩展：
    - 使用 `persist_batch` 任务结合 `apply_metadata_batch`，减少 DB 往返。
    - 通过多进程扩展，而非依赖多线程。
  - 持久化队列（特别是 `persist_batch`）应适度控制并发度，避免对数据库产生过大压力。
  - 如未来确实需要多线程：
    - 必须在 DB 层设计可靠的唯一约束、重试与死锁处理策略（例如检测特定错误码并重试）。

### 3.5 文件扫描（`services/scan`）

- 代表文件：
  - 扫描引擎：`services/scan/unified_scan_engine.py`
  - 仓库：`services/scan/file_asset_repository.py`
- 特点：
  - 扫描引擎内部已经采用 async 并发模型：
    - 使用 `asyncio.Queue` + 多个 scanner 协程 + 一个 processor 协程。
    - 在单线程事件循环内就能实现高并发扫描。
  - 仓库 `SqlFileAssetRepository` 为单例，但每次方法调用都会通过 `AsyncSessionLocal` 创建自己的 session。
- 并发与部署建议：
  - 不需要通过 Dramatiq 多线程提速扫描本身。
  - 扩展方式：
    - 调整 `UnifiedScanEngine.max_workers` 以及存储客户端的 `get_max_concurrency()`。
    - 提高执行 `scan` 队列的 Dramatiq 进程数。
  - 删除/清理逻辑中已经使用异步会话与事务，注意任务并发时的删除范围与租户隔离。

## 4. Dramatiq 线程数的权衡

### 4.1 为什么当前推荐 `--threads 1`

- 存在多个全局单例（`scraper_manager`、`storage_service`、`file_asset_repo` 等），其中 ScraperManager 内部使用了 `asyncio.Lock` 与 Task 缓存，**默认假设在单事件循环下运行**。
- 在 `--threads 1` 模式下：
  - 每个进程只有一个事件循环，所有 `asyncio` 对象都绑定到同一个 loop；
  - 全局单例不会被跨线程共享使用，极大简化并发语义。

### 4.2 若未来要启用多线程，需要的重构方向

若确实需要 `--threads > 1`，需要注意：

- ScraperManager:
  - 需要避免在单例中使用 `asyncio.Lock` 和 `Task` 跨线程共享。
  - 可以考虑将管理器从「全局单例」改为「每进程/每线程实例」，或使用 Redis 锁实现跨任务 singleflight。
- StorageService:
  - 若启用客户端连接缓存，需要确保不将 `asyncio.Lock` 挂在跨线程单例上。
- 全局状态:
  - 所有带有 async 对象（Lock、Event、Task）的全局变量，都需要审查其线程/loop 绑定。

在大规模业务之前，不建议投入大量成本重构为多线程模型。当前模式下，通过「多进程 + async」已经可以支持高并发与多租户。

## 5. 调优建议清单（Checklist）

### 5.1 提升吞吐时的步骤

1. **优先增加 Dramatiq 进程数**：
   - 从 2 → 4 → 6，观察 CPU 使用率、数据库连接数与延迟。
2. **逐步调大内部 async 并发参数**：
   - 刮削：`metadata_enricher` / ScraperManager 的 `max_concurrency`。
   - 扫描：`UnifiedScanEngine.max_workers` + 存储客户端内部并发参数。
3. **对 `persist_batch` 合理设置批大小**：
   - 例如 50~100 条一批，避免事务过大导致锁时间过长。
4. **监控与报警**：
   - 数据库连接数、事务锁等待时间。
   - 外部刮削服务的响应时间、错误率（防止被封 IP / 限流）。

### 5.2 避免的问题

- 不要在没有充分评估的情况下启用 `--threads > 1`：
  - 容易触发 Scraper 管理器中的跨线程事件循环错误。
  - 排查难度远大于多进程 + async 模式。
- 不要在 Service 层缓存长生命周期的数据库 Session：
  - 每次操作应通过 `AsyncSessionLocal` 创建短生命周期会话，避免跨任务/线程复用。

---

本章节为草稿，后续在实际压测与生产运行中如发现新的瓶颈或问题，应在此文基础上持续更新最佳实践。 


## 6. 单例、线程与 asyncio 的关系说明（FAQ）

### 6.1 单例和多线程是否冲突？

- **不天然冲突**：  
  单例本质上只是「进程内只有一个实例」。只要这个实例内部：
  - 不持有线程不安全的共享状态（或对共享状态加了恰当的锁），
  - 不持有绑定某个线程/事件循环的对象（例如特定 loop 的 `Task`、`asyncio.Lock`），  
  那么在多线程下是可以安全使用单例的。

- **当前架构中的关键点**：  
  - `StorageService` 的单例主要持有配置与工厂逻辑，内部每次调用自己创建 `AsyncSession`，相对安全。
  - `ScraperManager` 的单例则持有 `asyncio.Lock` 和 `Task`，这些对象依赖事件循环，因此**不适合作为跨线程共享的单例状态**。

### 6.2 使用多线程是不是不能用 asyncio / asyncio.gather / wait_for？

- **可以用，但每个线程需要自己的事件循环**：
  - Python 允许每个线程各自拥有一个 `asyncio` 事件循环。
  - 在某个线程里，只要在这个线程的 loop 上运行协程，就可以在其中使用 `asyncio.gather` / `asyncio.wait_for` 等。
  - 禁止的情况是：在 A 线程的 loop 上创建的 `Task` / `Lock`，拿到 B 线程的 loop 里去 await 或操作。

- **当前推荐模式**：
  - 我们选择「每个进程只有一个线程 + 一个事件循环」，这样所有 `asyncio` 对象都在同一个 loop 内，行为简单清晰。

### 6.3 asyncio 并发是不是「单线程里的协程并发」？

- 理解可以总结为：
  - **是的，asyncio 默认就是单线程事件循环里的协程并发模型**。
  - 一个事件循环在一个线程中运行，同一时间只有一个协程在执行 Python 字节码，但遇到 I/O 等待时会主动让出控制权，让其他协程运行。
  - 对于网络 I/O、磁盘 I/O 等场景，这种协作式并发可以在单线程中获得很好的吞吐能力。

- 和多线程的关系：
  - 多线程可以让多个事件循环并行运行（每线程一个 loop），但会显著增加复杂度。
  - 在当前项目中，更推荐使用「多进程 + 单线程 + asyncio」来扩展并发。

## 7. 若采用多进程 + 多线程，应如何重构 storage 与 scraper

> ⚠️ 本节是「如果未来必须上多线程」的设计草案，不是当前的实施方案。  
> 当前推荐仍然是：多进程 + 单线程 + asyncio。

### 7.1 总体目标

在多进程 + 多线程模式下（例如 `--processes=4 --threads=4`）：

- 每个线程拥有自己的事件循环（loop）。
- 避免在不同线程之间共享绑定到某个 loop 的 `asyncio` 对象（`Lock`、`Task` 等）。
- 保证跨线程共享的单例对象只包含：
  - 只读配置；
  - 或可通过线程安全原语（`threading.Lock`）保护的普通数据结构；
  - 不包含任何依赖特定事件循环的对象。

下面分别对 storage 与 scraper 给出重构方向。

### 7.2 Storage 重构方案（`services/storage`）

#### 7.2.1 问题点

当前 `StorageService` 使用单例模式，但尚未启用连接缓存，因此在多线程下问题不大。一旦开启「客户端缓存 + 连接复用」，典型实现往往需要：

- 在单例中维护 `_clients: Dict[storage_id, StorageClient]`。
- 为每个 `storage_id` 维护异步锁 `_connection_locks: Dict[str, asyncio.Lock]` 防止并发连接。

在多线程环境下：

- 这些 `asyncio.Lock` 绑定在创建它们的事件循环上，不能被其他线程的事件循环 await。
- 如果多个线程共享同一个 `StorageService` 单例，就会出现锁绑定 loop 不匹配的问题。

#### 7.2.2 重构方向 A：单例仅存放「同步状态」，异步资源由每线程管理

设计思路：

- 保留 `StorageService` 单例，但限制它只持有：
  - 存储类型与配置读取逻辑；
  - 同步的元数据（例如 mapper、静态配置）。
- 不在单例中缓存 `StorageClient` 实例或 `asyncio.Lock`。

接口形态：

- `StorageService.get_client(storage_id)` 每次返回一个新的 `StorageClient` 对象：
  - 由调用方在自己的事件循环中 `async with client` 使用；
  - 不跨线程共享 client。

优点：

- 与当前实现差异最小；
- 不会引入跨线程的 async 对象；
- 简化心智模型：每次使用都获取「一次性 client」。

缺点：

- 无法在进程/线程级别复用长连接；
- 如需提升远程存储访问性能，需要依赖存储客户端内部的连接池支持，而不是在服务层做缓存。

#### 7.2.3 重构方向 B：按线程/loop 管理缓存

如果以后确实要在服务层缓存客户端，可采用「按线程 + 按事件循环」的分域缓存：

- 使用 `threading.local()` 或 `contextvars` 存放「当前线程/当前 loop」下的客户端缓存：
  - 例如 `thread_local.storage_clients: Dict[loop_id, Dict[storage_id, StorageClient]]`。
- 每个线程初始化自己的事件循环并在该 loop 上生命周期内维护对应的 client 集合。
- 对于同一 `storage_id` 的并发连接竞争：
  - 使用该 loop 内部的 `asyncio.Lock` 进行串行化；
  - 不在多个线程之间共享此锁。

优点：

- 可以在每个线程/loop 内复用存储客户端连接；
- 不会出现跨线程操作 async 对象的问题。

缺点：

- 实现复杂度高；
- 缓存粒度切分为「线程 × loop」，进程内不同线程之间不能复用连接；
- 调试成本高，一般不建议在当前项目阶段实施。

### 7.3 Scraper 重构方案（`services/scraper`）

Scraper 管理器是当前架构中和多线程最冲突的部分。

#### 7.3.1 问题点

现状（`services/scraper/manager.py`）：

- `ScraperManager` 是全局单例 `scraper_manager`。
- 内部包含：
  - `_op_lock: asyncio.Lock`
  - `_inflight: Dict[Tuple[Any, ...], asyncio.Task]` + `_inflight_lock: asyncio.Lock`
  - 与 loop 强绑定的缓存与任务管理逻辑。

在多线程下：

- 不同线程的事件循环会试图共用同一组 `asyncio.Lock` 与 `Task`，导致：
  - `RuntimeError: <Lock/Task> attached to a different loop`；
  - 或不可预期的行为。

#### 7.3.2 重构方向 A：取消全局单例，改为「每线程/每进程一个 ScraperManager」

设计思路：

- 提供工厂函数而不是全局实例：
  - 例如 `get_scraper_manager()`：
    - 在每个线程/进程首次调用时创建 `ScraperManager` 实例；
    - 放入 `threading.local()` 或进程内单例；
    - 确保每个实例只在创建它的事件循环内使用。
- 所有调用方（元数据丰富化等）通过 `get_scraper_manager()` 获取本线程/本 loop 所属的 manager。

优点：

- 每个 ScraperManager 实例只绑定一个事件循环，`asyncio.Lock` 与 Task 的语义清晰；
- 可以根据线程/进程数量水平扩展刮削能力。

缺点：

- 原本的全局缓存（如 `_detail_cache`、 Redis singleflight 等）会按实例分片：
  - 不同线程/进程之间不能共享本地缓存；
  - 需要依赖 Redis 等外部缓存实现跨实例去重。

#### 7.3.3 重构方向 B：将并发控制从 asyncio 移到 Redis / 数据库

进一步的演进方向是：

- 减少 ScraperManager 内部对 `asyncio.Lock`/Task 的依赖；
- 将「请求去重 / singleflight / 限流」这类逻辑迁移到 Redis 层：
  - 通过 Redis 分布式锁实现「同一 series 详情一次只跑一个请求」；
  - 通过 Redis 计数器实现跨进程/线程的 QPS 限制。

这样 ScraperManager 可以被简化为：

- 只负责拼装参数、调用插件协程和处理结果；
- 并发控制由外部基础设施负责，更易于在多进程多线程环境下维护一致性。

### 7.4 多进程 + 多线程 的优缺点对比（相对于当前模式）

**优点：**

- 理论上可以在单机上进一步提高并行执行度，尤其是在：
  - CPU 较多但单个进程负载不高时；
  - 某些 I/O 操作不能完全通过 async 封装时。
- 可以让不同线程处理不同类型的任务，实现更细粒度的资源隔离（例如把 IO 重的任务放在线程池里）。

**缺点：**

- 需要全面审查并重构所有「全局单例 + asyncio 对象」的代码路径：
  - ScraperManager，未来如果在 StorageService 中加入 async 锁/缓存，也会受影响。
- 调试难度大幅上升：
  - 涉及线程调度、事件循环、异步任务的交织；
  - 某些问题只会在高并发/高负载下偶现。
- 对现有收益不明显：
  - 当前通过「多进程 + async」已经可以在单机上获得很高吞吐；
  - 更大的扩展空间可以通过横向扩容（多节点跑多个 Dramatiq worker）获得。

### 7.5 当前推荐与未来演进路径

- **当前阶段推荐**：
  - 继续使用「多进程 + 单线程 + asyncio」：
    - Dramatiq：`--processes N --threads 1`；
    - 通过调整内部 async 并发参数和进程数来扩容。
- **如果未来业务量激增且单机利用率成为瓶颈，再考虑多线程重构**：
  - 优先从 ScraperManager 入手，拆分全局单例与 asyncio 锁；
  - 同时评估监控与调试成本，确保团队有足够的时间和工具支撑这类重构。


toolName: search_codebase
            
status: success
          
query: storage service implementations and patterns
          

        
            
toolName: search_codebase
            
status: success
          
query: scraper manager and services
          

        
            
toolName: search_codebase
            
status: success
          
query: metadata enrichment and persistence services
          

        
            
toolName: search_codebase
            
status: success
          
query: scan file asset repository and scanning services
          
下面这份可以直接当成“多线程与多租户并发策略设计文档”使用，我会按模块把：

- 现在的并发模型讲清楚
- 如果 `--threads > 1` 会引入哪些额外问题
- 每个服务在多线程下要怎么改、为什么要这么改
- 哪些服务适合多线程，哪些最好继续单线程/多进程 + async

---

## **0. 总体结论（先给答案）**

在你现在这套架构下：

- Dramatiq 命令：  
  `dramatiq services.task.consumers --processes 4 --threads 1`
- 核心服务大量使用 `asyncio` + `AsyncSessionLocal`（异步数据库）
- 还存在全局单例对象（`scraper_manager`、`storage_service`、`file_asset_repo` 等）

**推荐策略：**

- **任务队列层保持 `--threads 1`**，通过 `--processes` 和服务内部的 `async/await` 并发（`max_concurrency`、`scan` 里的 worker 数）来扩展吞吐。
- **不要在当前设计下给 Dramatiq 增加线程数**，否则：
  - 会引入 **“多线程 + 多事件循环 + 全局 asyncio.Lock 单例”** 这种高风险组合；
  - 要改的代码非常多（尤其是 `ScraperManager` 和存储客户端缓存），性价比不高。

如果**坚持要用多线程**，可以在下面各模块的“修改方案”基础上做重构，但这是一个较大的工程，不建议作为短期优化手段。

下面按模块详细展开。

---

## **1. 任务队列与多租户总体并发模型**

当前模型：

- Dramatiq：`processes = 4, threads = 1`
- 多租户：所有重要表都带 `user_id`，逻辑上按租户隔离
- 异步 DB：`AsyncSessionLocal` + async engine，session 使用 `async with` 在每次调用内部创建和销毁

在这个模型下：

- **并发来源**：4 个进程 × 每进程一个事件循环 + 事件循环内部的 async 并发（例如 `metadata_enricher` 的 `max_concurrency=20`，Scan 引擎的 `max_workers=10`）。
- **租户隔离**：
  - 不同 `user_id` 的数据在逻辑上分区；
  - 同一时间多个进程/任务操作不同用户的数据，数据库行级冲突很少。
- **持久化冲突**：
  - 只会发生在**同一个 user 下、同一 core 或 series** 的并行持久化上（这个之前已经分析）。

**如果增加 `--threads`：**

- 每个进程变成：多个线程 + 每线程一个事件循环 + 共享全局单例对象
- 会带来新的问题：
  - **asyncio 对象（Lock、Event、Task 等）不是跨线程安全的**，而你的单例中正好有这些对象（`ScraperManager._op_lock` / `_inflight_lock` 等）。
  - 全局单例存储（`scraper_manager`、`storage_service`）会被多个线程同时访问。

因此，后面所有服务的分析都围绕这个前提：**一旦 `--threads > 1`，就要考虑“全局单例 + asyncio + 线程”组合带来的问题**。

---

## **2. Storage 服务（`services/storage`）**

### 2.1 当前实现要点

- 代表文件：`services/storage/storage_service.py:1-434`
- 特点：
  - `StorageService` 是 **单例**（`_instance` + `threading.Lock`，线程安全构造）
  - 数据库使用：每个方法内部 `async with AsyncSessionLocal() as session`，不持有全局 session
  - 当前 `get_client(storage_id)` 返回一个**新建 client**，没有启用全局 `_clients` 缓存（缓存逻辑是注释掉的）

### 2.2 多线程下的风险与修改建议

**风险来源主要在你如果未来恢复连接缓存逻辑**：

- 被注释的 `_clients` + `_connection_locks` 里：
  - `_connection_locks` 是 `asyncio.Lock` 的字典
  - 如果多线程共享同一个 `StorageService` 实例，**不同线程的事件循环去 await 同一个 asyncio.Lock** 是不被支持的（会抛异常或行为未定义）

**当前版本（无缓存）在多线程下是相对安全的**，原因：

- 单例构造用 `threading.Lock`，本身是线程安全的
- 每个方法内部用自己的 `AsyncSessionLocal` 和 `storage_client`，没有共享可变状态

### 2.3 建议与结论

- **是否需要多线程**：
  - Storage 的 I/O 主要通过 async 调用客户端实现（WebDAV/SMB/本地 IO），内部已经可以用 `asyncio` 并发（比如 Scan 引擎里 `get_client` 后开多个 scanner 协程）。
  - 在 Dramatiq 层再叠加多线程收益有限，反而增加复杂度。
- **如果将来要恢复缓存并且多线程**：
  - 不要在全局单例上挂 `asyncio.Lock`。
  - 要改成：
    - **每个进程内使用单线程 + async**（推荐），或
    - 使用真正的线程安全原语（`threading.Lock` + 不跨线程共享 asyncio 对象），并避免跨线程复用同一个已连接的 `StorageClient`。

**建议结论**：  
Storage 服务本身不需要通过 Dramatiq 多线程来提速，保持 `threads=1`，在 Scan/Media 业务里用 async 并发足够。

---

## **3. Scraper 管理（`services/scraper`）**

### 3.1 当前实现要点

- 管理器：`services/scraper/manager.py:57-737`
- 关键特性：
  - `ScraperManager` 是**单例**，全局对象 `scraper_manager = ScraperManager()`
  - 内部状态：
    - `_op_lock: asyncio.Lock`
    - `_inflight: Dict[Tuple[Any, ...], asyncio.Task]`
    - `_inflight_lock: asyncio.Lock`
    - `_detail_cache` 本地缓存（`_LocalDetailCache`）
    - 可选 Redis cache

### 3.2 多线程下的具体问题

**这是整个系统里最不适合多线程的模块之一：**

- `asyncio.Lock`、`asyncio.Task`、`asyncio.get_running_loop()` 都假定在一个事件循环内使用。
- 如果 Dramatiq 让每个线程有一个事件循环，但共享一个 `ScraperManager` 单例：
  - 线程 A 创建 `_op_lock`（绑定 A 的 loop）
  - 线程 B 在自己的 loop 里 await `_op_lock`，**直接报错：`attached to a different loop`**。
- `_inflight` 里缓存的是 Task 对象，也只能在创建它的 loop 中操作。

### 3.3 多线程支持下的修改方案（成本很高）

如果**强行要线程>1**，Scraper 层需要大改：

1. **取消 ScraperManager 全局单例跨线程共享**
   - 不再使用 `scraper_manager = ScraperManager()` 这种模式；
   - 改为 `get_scraper_manager()`，返回：
     - 每个进程内一个实例，且该实例只在一个事件循环中使用；或者
     - 每个线程一个实例（可以用 `contextvars` 或 `threading.local()`）。

2. **避免在 ScraperManager 中使用 `asyncio.Lock` 跨线程协调**
   - 若确实要用锁，锁的作用域必须限制在**单线程事件循环内**（当前就是这个假设）。
   - 对于“跨任务”去重、singleflight，可以改为：
     - 在 Redis 中做分布式锁；
     - 或者在每个线程内的局部内存做 singleflight，而不要跨线程共享 `_inflight`。

**建议结论**：  
Scraper 管理器强依赖 AsyncIO + 单事件循环 + 单例模式，**不建议在当前设计下增加 Dramatiq 线程数**。  
如果要提高刮削吞吐，应该：

- 保持 `threads=1`；
- 在 `ScraperManager` 内部继续使用 async 并发（已有 `asyncio.gather` / `wait_for` 等）；
- 通过增加 Dramatiq **进程数** 来水平扩展。

---

## **4. 元数据丰富化（`metadata_enricher.py`）**

### 4.1 当前实现要点

- 文件：`services/media/metadata_enricher.py`
- 用法：
  - 内部通过 `AsyncSessionLocal` 获取异步 DB session；
  - 使用 async + `asyncio.Semaphore(max_concurrency)` 控制每组并发；
  - 封装了 `iter_enrich_multiple_files` 这样的异步迭代器，外部 `metadata_worker` 用 `async for` 流式消费。

### 4.2 多线程影响

- **线程安全方面**：
  - 每次调用都创建自己的 `AsyncSessionLocal`，不共享 session，线程安全。
  - 局部变量（grouped、semaphore 等）都是函数内部的，不共享。
- **最大的问题是它依赖 `scraper_manager`**：
  - 所有刮削调用（search/detail）都是走 ScraperManager；
  - Scraper 本身如上所述，不适合跨线程共享。

### 4.3 建议

- **适合多并发，但不适合多线程**：
  - 丰富化本身是 IO + CPU 混合型，非常适合在单线程事件循环里用 `max_concurrency` 放大吞吐；
  - 不建议通过 Dramatiq 多线程来加速，而是通过提高 `max_concurrency` + 进程数。
- **如果坚持多线程**：
  - 必须先解决 ScraperManager 的线程/loop 安全问题（见上），否则一旦多线程调用，Scraper 层一定会出问题。

---

## **5. 元数据持久化（`metadata_persistence_service.py` + Async 版）**

### 5.1 当前实现要点

- 同步版：`services/media/metadata_persistence_service.py:54-2408`
  - 使用 `Session` （同步）+ 复杂的映射逻辑；
  - 没有持有全局 session，所有 session 都由调用方管理。
- 异步包装版：`services/media/metadata_persistence_async_service.py:1-84`
  - 使用 `AsyncSessionLocal`；
  - 通过 `async_session.run_sync(_run)` 调用同步的 `apply_metadata` 和批量方法。

### 5.2 多线程下的线程安全性

- SQLAlchemy 的 Engine / AsyncEngine 本身是为多进程/多线程场景设计的，只要：
  - **Session 不在线程间共享**（你现在是每次调用内部创建，符合这个要求）。
- `MetadataPersistenceService` 自身几乎无 mutable state，只是一堆映射函数：线程安全。

### 5.3 多线程会新增的问题（逻辑层面）

**这些不是 Python 线程安全问题，而是 DB 级别的并发问题：**

- 同一个用户、同一个 series/movie 被多个线程同时处理：
  - 可能同时插入同一个 `MediaCore` 或 `ExternalID`，触发唯一约束冲突；
  - 多线程会比单线程更容易放大这个问题。
- 批量持久化中的长事务：
  - 一个批次锁住多个 core/episode 行，如果另一个线程也要写这些行，会造成锁等待，甚至死锁。

### 5.4 建议与修改方案

- **是否需要多线程**：
  - 持久化是 DB 密集 + 少量 CPU 的操作，理想模型是：
    - 单线程事件循环里排队执行（避免 DB 锁竞争）；
    - 通过增加进程数扩展。
- **若要在持久化层用多线程提速（不推荐）**，需要：
  - 在关键查询处增加 `SELECT ... FOR UPDATE` 或类似机制保证顺序；
  - 在 Dramatiq Actor 上配置重试策略，捕获 `Deadlock` 与 `IntegrityError`；
  - 保证 `apply_metadata_batch` 的 batch 大小合适（不要太大）。

**建议结论**：  
持久化层不建议因 Dramatiq 多线程而提速，应优先通过 **批量持久化接口 + 多进程 + async DB** 来扩展。

---

## **6. 文件扫描（`services/scan`）**

### 6.1 当前实现要点

- 扫描引擎：`services/scan/unified_scan_engine.py:1-425`
  - 内部大量用 `asyncio.Queue` + 多个 `scanner_worker` 协程 + 一个 `_processor_worker` 协程；
  - 实际上已经在单线程事件循环内部实现了**“小分队并发扫描”**。
- 仓库：`services/scan/file_asset_repository.py:1-227`
  - `SqlFileAssetRepository` 是单例（`threading.Lock`），但每个方法内部 `async with AsyncSessionLocal()`；
  - 不持有全局 session 或缓存，线程安全。

### 6.2 多线程下的情况

- **扫描引擎本身已经是 async 并发架构**：
  - 单个 Dramatiq worker 线程就可以在一个 loop 里开很多协程并发扫描；
  - 多线程只能让多个 loop 并行，但每个任务本身的 scan 逻辑不用改。
- **需要注意的只有 storage_client 共享问题**：
  - 目前 `UnifiedScanEngine` 在一个 scan 任务内获取一个 `storage_client`（`async with raw_client as storage_client`），然后在多个 scanner 协程中共享：
    - 这是 **事件循环内的并发**，是安全的（假设 client 本身是协程安全的）。
  - 如果多线程运行多个 scan 任务，每个任务都会拿到自己的 client，不会跨线程共享 client。

### 6.3 建议

- **扫描非常适合多并发，但已经实现了 async 并发**：
  - 不需要通过 Dramatiq 多线程来提速；
  - 建议：
    - 调整 `max_workers` 和 storage client 的 `get_max_concurrency()`，控制单任务扫描并发。
- **多线程对 scan 的额外收益不大，但会跟 Storage/Scraper 共同引入复杂性**。

---

## **7. 综合建议：哪些需要多线程，哪些不需要？**

用一个总结表来回答你的核心问题：

| 模块 | 适合多线程？ | 建议 | 主要风险/改动点 |
|------|--------------|------|-----------------|
| `services/storage` | 不推荐在 Dramatiq 层多线程 | 保持 `threads=1`，在内部 async 并发 | 若启用 client 缓存，`asyncio.Lock` + 单例在多线程下会出错 |
| `services/scraper` | 强烈不推荐 | 只能多进程 + async 并发 | 单例 `ScraperManager` 内部使用 `asyncio.Lock`、`Task`，跨线程一定出问题 |
| `metadata_enricher` | 从业务上适合高并发，但不通过多线程 | 用 `max_concurrency` 和多进程扩展 | 依赖 `scraper_manager`，多线程会放大 Scraper 的线程/loop 问题 |
| `metadata_persistence_service` / async 版 | 不推荐依赖多线程扩展 | 用批量持久化 + 多进程 + async DB | 多线程会放大 DB 锁竞争和死锁概率 |
| `services/scan` | 已经是 async 并发，不需要 Dramatiq 多线程 | 调整 scan 内部 worker 数 | 多线程收益不大，反而与存储/持久化一起让并发模型更复杂 |

---

## **8. 总体推荐实践**

综上，我的建议是：

1. **保持 Dramatiq 配置为：**
   ```bash
   dramatiq services.task.consumers --processes 4 --threads 1
   ```
2. **扩展吞吐的手段放在：**
   - 增加 `--processes`，例如 4 → 8，根据机器 CPU/内存和数据库承受能力。
   - 在每个服务内部使用 async 并发：
     - `metadata_enricher` 的 `max_concurrency`；
     - `UnifiedScanEngine.max_workers`；
     - 刮削器内部使用 `aiohttp` 连接池。
3. **如果未来真的要上多线程模式：**
   - 必须先重构 `ScraperManager` 和潜在的 `StorageService` 缓存逻辑，避免在全局单例中使用 `asyncio.Lock`、`Task` 等跨线程对象；
   - 对持久化层增加更严格的锁、重试和幂等策略。

这套方案既符合你现在的多租户架构，又尽量避免进入“多线程 + async + 全局单例”这个高风险区域。如果你希望，我可以下一步帮你写一版 `DEVELOPMENT.md` 中的“并发与部署建议”章节草稿，让团队成员都能按同一策略来扩容和调优。
