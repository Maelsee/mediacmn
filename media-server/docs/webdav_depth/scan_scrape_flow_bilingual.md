# 扫描与刮削流程图（中英双语版）

## 流程概览

```mermaid
flowchart TD
  Client[API/前端] --> EASS[EnhancedAsyncScanService<br/>增强异步扫描服务]
  EASS --> UTS[UnifiedTaskScheduler<br/>统一任务调度器]
  UTS --> TQS[TaskQueueService<br/>任务队列服务]
  TQS --> UTE[UnifiedTaskExecutor<br/>统一任务执行器]
  UTE --> USE[UnifiedScanEngine<br/>统一扫描引擎]
  UTE --> MTP[MetadataTaskProcessor<br/>元数据任务处理器]
  USE --> DB[(SQLite 数据库)]
  USE --> Storage[(存储后端：WebDAV/本地/S3)]
  MTP --> Scrapers{刮削插件<br/>TMDB/Douban}
  Scrapers --> ExternalAPIs[外部接口：TMDB v4 / 豆瓣]
  MTP --> DB
  MTP --> Storage
```

## 扫描流程

```mermaid
flowchart LR
  A[获取存储客户端<br/>Get StorageClient] --> B{连接存储<br/>Connect Storage}
  B -->|成功<br/>Success| C[批量遍历目录<br/>Batch Traverse Directory]
  C --> D[过滤媒体文件<br/>Filter Media Files]
  D --> E[解析文件名与分辨率<br/>Parse Filename & Resolution]
  E --> F{是否为小文件（<100MB）<br/>Small File?}
  F -->|是<br/>Yes| G[计算文件哈希<br/>Calculate File Hash]
  F -->|否<br/>No| H[跳过哈希计算<br/>Skip Hash Calculation]
  G --> I[数据库查重（哈希/路径）<br/>DB Duplicate Check]
  H --> I
  I -->|存在<br/>Exists| J[更新大小/时间戳<br/>Update Size/Timestamp]
  I -->|不存在<br/>Not Exists| K[创建文件记录（FileAsset）<br/>Create File Record]
  J --> L[统计更新文件数<br/>Count Updated Files]
  K --> M[记录新文件ID<br/>Record New File IDs]
  L --> N[累计统计<br/>Aggregate Statistics]
  M --> N
  N --> O[生成扫描结果（ScanResult）<br/>Generate ScanResult]
```

## 刮削流程

```mermaid
flowchart LR
  S[输入文件ID<br/>Input File ID] --> T[读取数据库中的文件记录<br/>Read File Record from DB]
  T --> U[解析标题/年份/季集信息<br/>Parse Title/Year/Season/Episode]
  U --> V{确定媒体类型（电影/剧集/集）<br/>Determine Media Type}
  V --> W[调用刮削管理器进行搜索<br/>Call Scraper Manager Search]
  W --> X{是否命中结果<br/>Has Results?}
  X -->|否<br/>No| Y[记录未命中并返回失败<br/>Record Miss and Return False]
  X -->|是<br/>Yes| Z[选择最佳匹配并获取详情<br/>Select Best Match & Get Details]
  Z --> AA[保存到媒体核心并关联文件<br/>Save to MediaCore & Link File]
  AA --> AB[写入NFO/海报/背景图到存储<br/>Write NFO/Poster/Fanart to Storage]
  AB --> AC[提交事务并返回成功<br/>Commit Transaction & Return True]
```

## 任务生命周期

```mermaid
sequenceDiagram
  participant API as API
  participant EASS as 增强异步扫描服务<br/>EnhancedAsyncScanService
  participant UTS as 统一任务调度器<br/>UnifiedTaskScheduler
  participant TQS as 任务队列服务<br/>TaskQueueService
  participant UTE as 统一任务执行器<br/>UnifiedTaskExecutor
  participant USE as 统一扫描引擎<br/>UnifiedScanEngine
  participant MTP as 元数据任务处理器<br/>MetadataTaskProcessor

  API->>EASS: 启动扫描(start_async_scan)<br/>Start Scan
  EASS->>UTS: 创建扫描任务(create_scan_task)<br/>Create Scan Task
  UTS->>TQS: 入队(TaskType.SCAN)<br/>Enqueue SCAN Task
  TQS-->>UTE: 拉取任务<br/>Pull Task
  UTE->>USE: 执行扫描(scan_storage)<br/>Execute Scan
  USE-->>UTE: 返回扫描结果(含 new_file_ids)<br/>Return Scan Result
  UTE-->>TQS: 更新队列任务结果<br/>Update Task Result
  UTE->>UTS: 扫描完成后是否创建刮削任务<br/>Check if Create Metadata Task
  UTS->>TQS: 入队(TaskType.METADATA_FETCH)<br/>Enqueue METADATA Task
  TQS-->>UTE: 拉取刮削任务<br/>Pull Metadata Task
  UTE->>MTP: 执行元数据丰富(enrich)<br/>Execute Metadata Enrichment
  MTP-->>UTE: 返回刮削结果<br/>Return Metadata Result
  UTE-->>TQS: 更新任务状态<br/>Update Task Status
```

## 错误与保护

```mermaid
flowchart TD
  P[外部 API 限流<br/>External API Rate Limit] --> Q[限流器：TMDB 10/秒<br/>RateLimiter: TMDB 10/sec]
  R[故障隔离<br/>Fault Isolation] --> S[熔断器：连续失败熔断<br/>CircuitBreaker: Consecutive Failures]
  T[队列重试<br/>Queue Retry] --> U[重试 3 次，延迟 5 分钟<br/>Retry 3 times, 5 min delay]
  V[大文件哈希策略<br/>Large File Hash Strategy] --> W[仅计算前后 10MB<br/>Calculate first & last 10MB only]
  X[失败处理<br/>Failure Handling] --> Y[记录错误详情<br/>Record Error Details]
```

## 关键代码参考

| 功能 | 文件路径 | 行号 | 说明 |
|------|----------|------|------|
| 扫描入口 | `services/scan/unified_scan_engine.py` | 383 | 统一扫描引擎主入口 |
| 单文件处理 | `services/scan/unified_scan_engine.py` | 211 | 处理单个文件的逻辑 |
| 哈希计算与大文件优化 | `services/scan/unified_scan_engine.py` | 166 | 大文件哈希计算优化 |
| 入库逻辑（创建/更新） | `services/scan/unified_scan_engine.py` | 318 | 文件记录创建与更新 |
| 异步任务创建 | `services/scan/enhanced_async_scan_service.py` | 58 | 创建异步扫描任务 |
| 调度器创建扫描任务 | `services/scan/unified_task_scheduler.py` | 99 | 统一任务调度器创建扫描任务 |
| 调度器创建刮削任务（分批） | `services/scan/unified_task_scheduler.py` | 163 | 分批创建元数据任务 |
| 刮削器丰富 | `services/media/metadata_enricher.py` | 32 | 元数据丰富主入口 |
| 侧车写入 | `services/media/metadata_enricher.py` | 211 | 写入NFO、海报等侧车文件 |

## 方法解释（中文）

### 统一扫描引擎（UnifiedScanEngine）
统一扫描引擎是整个系统的核心组件，负责从各种存储后端（WebDAV、本地、S3）中发现和扫描媒体文件。它采用插件化架构，支持多种文件类型的识别和处理。

**主要功能：**
- 连接多种存储后端
- 批量遍历目录结构
- 智能识别媒体文件（视频、音频、图片、字幕）
- 解析文件名提取元数据（标题、年份、季集信息）
- 计算文件哈希用于去重
- 与数据库交互，创建或更新文件记录

**优化策略：**
- 大文件（>100MB）采用前后10MB分段哈希，避免完整读取
- 批量处理减少数据库操作次数
- 增量扫描基于文件大小和时间戳变化

### 统一任务调度器（UnifiedTaskScheduler）
任务调度器负责任务的生命周期管理，协调扫描任务和元数据丰富任务的执行顺序，支持任务依赖和优先级管理。

**核心能力：**
- 创建和管理扫描任务
- 批量创建元数据丰富任务
- 任务状态实时跟踪
- 支持任务优先级（紧急、高、普通、低）
- 任务执行结果统计

**任务协调：**
- 扫描任务完成后自动触发元数据任务
- 支持组合任务（扫描+元数据）
- 任务失败重试机制（3次重试，5分钟间隔）

### 增强异步扫描服务（EnhancedAsyncScanService）
提供对外的异步API接口，封装了任务创建的复杂性，为前端提供简单易用的扫描控制接口。

**API功能：**
- 启动异步扫描任务
- 启动元数据丰富任务
- 查询任务状态
- 获取用户任务列表
- 取消正在执行的任务

**性能特点：**
- 响应时间 <500ms
- 支持批量任务创建
- 提供任务执行时间预估

### 元数据任务处理器（MetadataTaskProcessor）
负责调用外部刮削API（TMDB、豆瓣）获取媒体元数据，并将结果保存到数据库和侧车文件中。

**刮削流程：**
1. 解析文件名提取标题、年份、季集信息
2. 根据媒体类型调用相应的刮削器
3. 搜索最佳匹配结果
4. 获取详细信息（剧情、演员、评分等）
5. 保存到数据库（MediaCore表）
6. 生成NFO文件和下载海报图片

**限流保护：**
- TMDB：10次/秒
- 豆瓣：5次/秒
- 连续失败触发熔断机制
- 支持多种语言（中文、英文等）

### 错误处理与保护机制
系统内置多层保护机制，确保在高并发和外部服务不稳定的情况下仍能稳定运行。

**保护策略：**
- **限流器**：防止对外部API的过度调用
- **熔断器**：连续失败时自动熔断，避免级联故障
- **重试机制**：失败后自动重试，最多3次，间隔5分钟
- **错误记录**：详细记录失败原因，便于排查问题
- **大文件优化**：避免对大文件进行完整哈希计算

这些机制共同保证了系统的稳定性和可靠性，即使在网络不稳定或外部服务暂时不可用的情况下，也能优雅地处理错误并恢复正常运行。