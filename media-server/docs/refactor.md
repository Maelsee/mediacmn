# Media-Server 重构方案

> 基于深度代码分析生成，目标：**支撑万人并发、优化架构结构、清理冗余代码、提升可维护性**
> 原则：**只优化结构和架构，不改功能行为**

---

## 一、现状诊断摘要

| 维度 | 现状 | 严重度 |
|------|------|--------|
| 代码量 | 107 个 Python 文件，~29,739 行 | — |
| 最大文件 | `metadata_persistence_service.py` 2,486 行（God Object） | 🔴 严重 |
| 死代码 | `services/task/old/` 1,794 行 + 注释路由 658 行 + 29 个幽灵 .pyc | 🟡 中 |
| 架构问题 | Sync/Async 混用、内联迁移、循环依赖、队列声明缺失 | 🔴 严重 |
| 扩展性 | 单进程 Uvicorn、Dramatiq 默认配置、无连接池调优、无缓存分层 | 🔴 严重 |
| 依赖冗余 | loguru（未用）、pika（未用）、aiohttp+httpx 双 HTTP 客户端 | 🟡 中 |

---

## 二、结构与架构优化

### 2.1 目录结构重组

**现状问题：** `services/media/` 承载了扫描后的全部处理逻辑（enrichment、persistence、sidecar），职责过于集中；`consumers.py` 是 547 行的巨型消费者文件。

**目标结构：**

```
media-server/
├── api/                          # 路由层（不变，但清理注释代码）
│   ├── routes_health.py
│   ├── routes_auth.py
│   ├── routes_media.py
│   ├── routes_playback.py
│   ├── routes_scan.py
│   ├── routes_tasks.py           # 合并 routes_scan.py 中的任务管理端点
│   ├── routes_tmdb.py
│   ├── routes_storage_config.py
│   ├── routes_storage_server.py
│   └── routes_danmu.py
├── core/                         # 基础设施（不变）
│   ├── config.py
│   ├── db.py
│   ├── security.py
│   ├── errors.py
│   ├── logging.py
│   └── encryption.py
├── models/                       # 数据模型（不变）
├── schemas/                      # 序列化模型（不变）
├── services/
│   ├── auth/                     # 不变
│   ├── storage/                  # 不变
│   ├── scraper/                  # 不变
│   ├── danmu/                    # 不变
│   ├── media/                    # 拆分后的媒体服务
│   │   ├── media_service.py      # 查询类（cards/detail/subtitles/episodes）精简后
│   │   ├── play_service.py       # 【新】从 media_service.py 拆出 play URL 组装逻辑
│   │   ├── enricher.py           # 重命名自 metadata_enricher.py，职责不变
│   │   └── sidecar.py            # 合并 sidecar_localize_processor.py + sidecar_fixup.py
│   ├── persistence/              # 【新目录】从 services/media/ 拆出
│   │   ├── __init__.py
│   │   ├── core_repo.py          # MediaCore + Extension 表的 CRUD（从 metadata_persistence_service.py 拆出）
│   │   ├── artwork_repo.py       # Artwork + ExternalID 持久化（从 metadata_persistence_service.py 拆出）
│   │   ├── credit_repo.py        # Credit + Person 持久化（从 metadata_persistence_service.py 拆出）
│   │   ├── genre_repo.py         # Genre + MediaCoreGenre 持久化（从 metadata_persistence_service.py 拆出）
│   │   ├── batch_service.py      # 批量编排逻辑（原 metadata_persistence_async_service.py）
│   │   └── contracts.py          # 持久化契约模型定义（从 producer.py 的 Payload 类提取）
│   ├── scan/                     # 不变
│   └── task/                     # 任务队列重构（详见第四节）
│       ├── broker.py
│       ├── state_store.py
│       ├── producer.py
│       ├── scan_worker.py        # 【新】从 consumers.py 拆出
│       ├── metadata_worker.py    # 【新】从 consumers.py 拆出
│       ├── persist_worker.py     # 【新】从 consumers.py 拆出
│       ├── delete_worker.py      # 【新】从 consumers.py 拆出
│       ├── localize_worker.py    # 【新】从 consumers.py 拆出
│       ├── progress.py           # 重命名自 scan_progress.py
│       └── encoder.py            # 重命名自 custom_encoder.py
└── tests/
```

**变更清单：**

| 操作 | 源 | 目标 | 说明 |
|------|---|------|------|
| 拆分 | `services/media/media_service.py` 中 play 相关函数 | `services/media/play_service.py` | `_compose_playinfo_inline`、play URL 组装、refresh 逻辑 |
| 拆分 | `services/media/metadata_persistence_service.py`（2,486 行） | `services/persistence/` 下 4 个 repo 文件 | 按实体类型拆分：core、artwork、credit、genre |
| 重命名 | `metadata_enricher.py` | `enricher.py` | 去掉冗余前缀 |
| 合并 | `sidecar_localize_processor.py` + `sidecar_fixup.py` | `sidecar.py` | 同一领域的两个文件合并 |
| 拆分 | `consumers.py`（547 行） | 5 个独立 worker 文件 | 每个队列一个文件，消除循环依赖 |
| 删除 | `services/task/old/` | — | 1,794 行死代码 |
| 删除 | `services/media/metadata_task_processor.py` | — | 561 行遗留代码，无活跃引用 |
| 删除 | `services/media/metadata_persistence_async_service.py` | — | 并入 `persistence/batch_service.py` |
| 清理 | `api/routes_scraper.py`、`api/routes_collections.py` | — | 整文件注释，删除 |

### 2.2 Sync/Async 统一

**现状问题：** 项目存在严重的 Sync/Async 混用——`main.py` 启动调用 sync `init_db()`、`persist_worker` 在 async actor 内使用 sync session、`routes_playback.py` 和 `routes_auth.py` 使用 sync Session。

**优化方案：**

1. **统一启动流程**：`main.py` 改用 `init_async_db()`，移除 sync `init_db()` 中的内联迁移代码，全部交给 Alembic
2. **统一路由 Session**：`routes_playback.py` 和 `routes_auth.py` 改为 `AsyncSession` + `await`
3. **统一 Worker Session**：所有 Dramatiq worker 使用 `AsyncSessionLocal` + `run_sync()` 桥接，不再混用 `get_session()`
4. **移除 psycopg2-binary**：仅保留 `psycopg`（v3）作为 sync driver（Alembic 用），`asyncpg` 作为 runtime driver

### 2.3 数据库迁移规范化

**现状问题：** `db.py` 中 `init_db()` 和 `init_async_db()` 各有 ~100 行内联 `ALTER TABLE` / `CREATE INDEX` SQL，绕过 Alembic，且两份代码重复。

**优化方案：**

1. 将所有内联迁移转为正式 Alembic migration revision
2. `init_async_db()` 仅保留 `create_all()`（开发环境）和连接池初始化
3. 生产环境启动时执行 `alembic upgrade head`，不再依赖内联 SQL

---

## 三、技术栈优化（支撑万人并发）

### 3.1 ASGI 服务器

| 维度 | 现状 | 优化 | 理由 |
|------|------|------|------|
| 服务器 | Uvicorn 单进程 | **Gunicorn + UvicornWorker** | 多进程利用多核，Gunicorn 管理 worker 生命周期 |
| Worker 数 | 1 | `CPU_CORES * 2 + 1`（建议 4~8 个） | 万人并发需要多进程 |
| 连接池 | asyncpg 默认（10） | `pool_size=20, max_overflow=10` | 万人场景下 DB 连接是瓶颈 |
| 保持连接 | 默认 | 启用 `keepalives_idle=30` | 防止长连接被中间件断开 |

**启动命令变更：**
```bash
# 开发
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产
gunicorn main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000 --timeout 120
```

### 3.2 数据库层

| 优化项 | 方案 |
|--------|------|
| 连接池 | asyncpg `pool_size=20, max_overflow=10, pool_recycle=3600` |
| 读写分离（可选） | 引入 PostgreSQL 只读副本，查询类路由走 replica |
| 查询优化 | `media_service.py` 中的首页卡片查询添加复合索引 `(user_id, kind, created_at)` |
| N+1 检测 | 引入 `sqlalchemy-continuum` 或手动 `selectinload` 消除详情页 N+1 |
| 慢查询日志 | 设置 `log_min_duration_statement = 200`（ms） |

### 3.3 缓存分层

**现状：** Redis 仅用于任务状态存储和刮削缓存，API 层无缓存。

**引入三层缓存：**

```
请求 → L1: 内存缓存 (cachetools TTLCache, 30s)
     → L2: Redis 缓存 (热门数据, 5min TTL)
     → L3: PostgreSQL (源数据)
```

| 缓存对象 | 层级 | TTL | 策略 |
|----------|------|-----|------|
| 首页卡片 | L1+L2 | 30s / 5min | 用户维度 key，写后失效 |
| 媒体详情 | L2 | 10min | `media:detail:{id}`，更新时失效 |
| TMDB 搜索 | L2 | 1h | `tmdb:search:{query_hash}`，只增不删 |
| 弹幕数据 | L2 | 30min | `danmu:{episode_id}`，已有实现 |
| 存储配置 | L1 | 60s | 低频变更，适合内存缓存 |

### 3.4 任务队列增强

| 优化项 | 现状 | 方案 |
|--------|------|------|
| Broker | 单 Redis 实例 | 主从 Redis 或 Redis Cluster（可选） |
| Worker 进程 | `dramatiq --processes 2` | `--processes 4 --threads 2`（IO 密集型任务用线程） |
| 队列优先级 | 无 | `scan` 和 `delete` 用默认优先级，`metadata` 和 `persist_batch` 用低优先级队列，避免刮削任务饿死扫描 |
| 重试策略 | 固定 3 次 | 指数退避：`5s → 30s → 120s`，区分可重试/不可重试错误 |
| 死信队列 | 有 StateStore 但无告警 | 添加 DLQ 监控：超过阈值时写日志 + 可选通知 |
| 幂等性 TTL | 60s（太短） | 扫描任务：300s；持久化任务：120s；删除任务：60s |

### 3.5 依赖清理

| 操作 | 包 | 理由 |
|------|---|------|
| 移除 | `loguru` | 未使用，项目用 stdlib logging |
| 移除 | `pika` | 未使用，项目用 Redis 作为 broker |
| 移除 | `aiohttp` | 与 `httpx` 功能重复，保留 `httpx` 即可 |
| 移除 | `psycopg2-binary` | 保留 `psycopg`（v3）即可 |
| 移除 | `requests-cache` | 未使用，项目用自定义 Redis 缓存 |
| 移除 | `gevent` / `greenlet` | async-dramatiq 已提供异步支持，gevent 未使用 |
| 升级 | `cryptography 42.0.8` → `44.x` | 安全更新 |

---

## 四、任务队列深度优化

### 4.1 consumers.py 拆分

**现状：** 6 个 worker 全部在一个 547 行的 `consumers.py` 中，通过延迟导入避免循环依赖。

**拆分方案：** 每个 worker 独立为一个文件，消除延迟导入。

```
services/task/
├── workers/
│   ├── __init__.py          # 导出所有 worker actor
│   ├── _base.py             # 公共逻辑：状态更新、错误处理、日志
│   ├── scan_worker.py       # scan 队列消费者
│   ├── metadata_worker.py   # metadata 队列消费者
│   ├── persist_worker.py    # persist_batch 队列消费者
│   ├── delete_worker.py     # delete 队列消费者
│   └── localize_worker.py   # localize 队列消费者
```

**`_base.py` 公共逻辑提取：**

```python
# 伪代码示意
async def run_worker(task_id: str, payload: dict, handler: Callable):
    """所有 worker 的公共骨架"""
    state_store.update_status(task_id, TaskStatus.RUNNING)
    try:
        result = await handler(payload)
        state_store.update_status(task_id, TaskStatus.SUCCESS, result=result)
    except RetryableError as e:
        state_store.update_status(task_id, TaskStatus.FAILED, error=str(e))
        raise  # Dramatiq 重试
    except Exception as e:
        state_store.update_status(task_id, TaskStatus.DEADLETTER, error=str(e))
        logger.exception(f"Task {task_id} dead-lettered")
```

### 4.2 scan_worker 优化

**现状问题：**
- 扫描全量文件后一次性提交 metadata 任务（可能数万个 file_id）
- 进度回调每次都写 Redis + Pub/Sub，高并发时 Redis 压力大

**优化方案：**

1. **分批提交 metadata 任务**：每 500 个 file_id 为一批，避免单个 metadata 任务 payload 过大
2. **进度回调节流**：每 100 个文件或每 5 秒更新一次进度，减少 Redis 写入频率
3. **增量扫描**：对比文件 mtime，仅对变更文件触发 metadata 任务（现状已部分实现，需完善）

### 4.3 metadata_worker 优化

**现状问题：**
- 串行处理每个文件的 enrichment（filename parse → TMDB search → TMDB detail）
- 单个文件 TMDB 请求失败会导致整批失败
- 100 条一批的 persist_batch 可能因单条失败而全部重试

**优化方案：**

1. **并发 enrichment**：使用 `asyncio.Semaphore(10)` 限制并发数，同时并行处理多个文件
2. **单文件错误隔离**：单个文件 enrichment 失败时跳过（记录日志），不影响其他文件
3. **persist_batch 分批容错**：每条 item 独立 try/except，部分失败时只重试失败项
4. **刮削结果缓存**：相同 title+year 的查询命中 ScraperManager 的 Redis 缓存，避免重复 TMDB 请求

### 4.4 persist_batch_worker 优化

**现状问题：**
- `MetadataPersistenceService`（2,486 行）是 God Object，每次批量持久化都在一个事务中操作 10+ 张表
- 单条失败导致整批回滚

**优化方案：**

1. **拆分持久化逻辑**（见 2.1 目录结构重组）：`core_repo`、`artwork_repo`、`credit_repo`、`genre_repo` 各自独立事务
2. **单条事务隔离**：每条 item 在独立子事务（SAVEPOINT）中处理，失败不影响其他条目
3. **Upsert 优化**：使用 PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` 替代先 SELECT 再 INSERT/UPDATE 的模式
4. **批量写入**：Artwork、Genre、Credit 等附属表使用 `session.add_all()` 批量提交

### 4.5 delete_worker 优化

**现状问题：** 清理孤立 MediaCore 的查询可能全表扫描。

**优化方案：**

1. **索引优化**：`FileAsset(core_id)` 添加索引（如不存在）
2. **延迟清理**：不立即清理孤立 Core，改为定期批量清理（APScheduler 定时任务）
3. **软删除确认**：软删除后保留 7 天，超过后由定时任务硬删除

### 4.6 localize_worker 优化

**现状问题：** NFO 文件写入和图片下载是串行 IO 操作。

**优化方案：**

1. **并发处理**：使用 `asyncio.Semaphore(5)` 并发下载图片
2. **跳过已存在**：检查目标文件是否已存在且大小一致，跳过重复下载
3. **失败重试分离**：图片下载失败不应阻塞 NFO 写入，分为两个独立步骤

### 4.7 Broker 配置优化

```python
# broker.py 优化后配置
broker = RedisBroker(
    url=settings.REDIS_URL,
    # 连接池
    connection_pool_kwargs={"max_connections": 20},
)

# 声明所有队列（修复 persist_batch 缺失 bug）
for queue in ["scan", "metadata", "persist_batch", "persist", "delete", "localize"]:
    broker.declare_queue(queue)

# 中间件
broker.add_middleware(TimeLimit(time_limit=600_000))  # 10 分钟（原 360s 对大库扫描不够）
broker.add_middleware(
    Retries(
        max_retries=3,
        min_backoff=5_000,
        max_backoff=120_000,  # 原 60s → 120s
        retry_when=lambda exc: isinstance(exc, (ConnectionError, TimeoutError, IOError))
    )
)
broker.add_middleware(AsyncIO())
```

---

## 五、清理废弃代码清单

### 5.1 立即删除（零风险）

| 文件/目录 | 行数 | 说明 |
|-----------|------|------|
| `services/task/old/` | 1,794 | 旧任务系统，无活跃引用 |
| `api/routes_scraper.py` | 380 | 整文件注释 |
| `api/routes_collections.py` | 278 | 整文件注释 |
| `services/media/metadata_task_processor.py` | 561 | 遗留独立处理器，无活跃引用 |
| `services/__pycache__/*.pyc`（29 个幽灵文件） | — | 无对应 .py 源 |

**合计删除：~3,013 行死代码**

### 5.2 拆分后删除

| 文件 | 行数 | 去向 |
|------|------|------|
| `services/media/metadata_persistence_service.py` | 2,486 | 拆分为 `persistence/` 下 4 个 repo |
| `services/media/metadata_persistence_async_service.py` | 84 | 并入 `persistence/batch_service.py` |
| `services/task/consumers.py` | 547 | 拆分为 5 个独立 worker 文件 |
| `services/media/sidecar_localize_processor.py` + `sidecar_fixup.py` | 649 | 合并为 `sidecar.py` |

### 5.3 代码块清理

| 文件 | 清理内容 | 预估行数 |
|------|----------|----------|
| `consumers.py` | 删除注释掉的单文件 persist 逻辑 | ~80 行 |
| `main.py` | 删除注释掉的 scraper/collections 导入 | ~10 行 |
| `routes_playback.py` | 删除注释掉的 platform API | ~30 行 |
| `routes_storage_server.py` | 删除 `from ast import stmt` 无用导入 | 1 行 |

---

## 六、API 层优化

### 6.1 合并重复的扫描入口

**现状：** `routes_scan.py`（`POST /scan/start`）和 `routes_tasks.py`（`POST /tasks/scan`）都创建扫描任务，逻辑不同。

**方案：** 统一到 `routes_tasks.py`，`routes_scan.py` 仅保留进度查询和 WebSocket 端点。`POST /scan/start` 改为调用 `routes_tasks.py` 的服务层。

### 6.2 提取内联业务逻辑

**现状：** `routes_media.py` 中 `_compose_playinfo_inline()` 有 66 行直接操作数据库的业务逻辑。

**方案：** 移入 `services/media/play_service.py`，路由层仅做参数解析和响应格式化。

### 6.3 统一响应格式

**现状：** 部分端点返回 `ApiResponse` 包装，部分返回裸数据。

**方案：** 全部统一为 `ApiResponse[T]` 格式：
```json
{"success": true, "data": {...}, "message": null}
```

---

## 七、实施优先级

### P0 — 立即修复（影响正确性）

| 项 | 说明 | 预估工作量 |
|----|------|-----------|
| 修复 `persist_batch` 队列声明 | `broker.py` 中补充声明 | 5 分钟 |
| 修复 `main.py` 启动函数 | `init_db()` → `init_async_db()` | 30 分钟 |
| 删除死代码 | `old/`、注释路由、幽灵 pyc | 1 小时 |

### P1 — 短期优化（1-2 周，显著提升性能和可维护性）

| 项 | 说明 | 预估工作量 |
|----|------|-----------|
| `consumers.py` 拆分为 5 个 worker 文件 | 消除循环依赖，提升可读性 | 1 天 |
| `metadata_persistence_service.py` 拆分 | God Object 分解为 4 个 repo | 2 天 |
| 引入 Gunicorn + 多 worker | 生产部署多进程 | 半天 |
| 数据库连接池调优 | `pool_size`、`pool_recycle` 参数 | 半天 |
| 引入 API 层缓存 | 首页卡片、媒体详情 Redis 缓存 | 1 天 |
| 统一 Sync/Async | 路由和 worker 统一为 AsyncSession | 1 天 |
| 内联迁移转 Alembic | 正式化数据库迁移 | 半天 |

### P2 — 中期优化（2-4 周，支撑万人规模）

| 项 | 说明 | 预估工作量 |
|----|------|-----------|
| 缓存分层（L1+L2） | 内存缓存 + Redis 缓存 | 2 天 |
| metadata_worker 并发 enrichment | Semaphore 并发 + 错误隔离 | 1 天 |
| persist_batch 单条容错 | SAVEPOINT 隔离 + Upsert 优化 | 1 天 |
| 进度回调节流 | 扫描进度减少 Redis 写入 | 半天 |
| 统一响应格式 | 全部端点使用 `ApiResponse` | 1 天 |
| 合并扫描 API 入口 | 消除 routes_scan 和 routes_tasks 重复 | 半天 |
| 依赖清理 | 移除 loguru/pika/aiohttp 等 | 半天 |

### P3 — 长期演进（按需）

| 项 | 说明 |
|----|------|
| 读写分离 | PostgreSQL 只读副本 |
| Redis Cluster | 任务队列高可用 |
| Prometheus 指标暴露 | 已引入 prometheus_client，需接入 Grafana |
| 分布式追踪 | 引入 OpenTelemetry |
| 微服务拆分（如需） | 扫描/刮削/播放可独立部署 |

---

## 八、万人并发关键指标

| 指标 | 当前估算 | 优化后目标 |
|------|----------|-----------|
| API 并发连接 | ~200（单 Uvicorn） | ~5,000（4 UvicornWorker + 连接池） |
| 数据库连接 | 10（asyncpg 默认） | 40（4 worker × pool_size=20，含 overflow） |
| 任务吞吐 | ~10 tasks/s（2 Dramatiq 进程） | ~50 tasks/s（4 进程 × 2 线程） |
| 首页响应时间 | ~500ms（无缓存） | ~50ms（L1 缓存命中） |
| 扫描速度 | ~100 files/s（串行解析） | ~300 files/s（并发解析 + 批量 upsert） |

---

## 九、风险与注意事项

1. **Alembic 迁移正式化**：需要将 `db.py` 中的内联 SQL 导出为 migration revision，注意与现有 migration 的顺序关系
2. **Gevent 移除**：确认 `async-dramatiq` 不依赖 gevent 后再移除，避免 worker 启动失败
3. **缓存一致性**：引入缓存后需要在所有写入路径添加缓存失效逻辑，遗漏会导致数据不一致
4. **拆分 `metadata_persistence_service.py`**：这是最大的重构项，需要充分的集成测试覆盖
5. **向前兼容**：`routes_scan.py` 的 `POST /scan/start` 端点需要保留（或提供兼容路由），避免客户端 break
