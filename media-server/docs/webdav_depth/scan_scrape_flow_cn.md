# 扫描与刮削流程图（统一架构）

## 流程概览

```mermaid
flowchart TD
  Client[API/前端] --> EASS[增强异步扫描服务]
  EASS --> UTS[统一任务调度器]
  UTS --> TQS[任务队列服务]
  TQS --> UTE[统一任务执行器]
  UTE --> USE[统一扫描引擎]
  UTE --> MTP[元数据任务处理器]
  USE --> DB[(SQLite 数据库)]
  USE --> Storage[(存储后端：WebDAV/本地/S3)]
  MTP --> Scrapers{刮削插件<br/>TMDB/豆瓣}
  Scrapers --> ExternalAPIs[外部接口：TMDB v4 / 豆瓣]
  MTP --> DB
  MTP --> Storage
```

## 扫描流程

```mermaid
flowchart LR
  A[获取存储客户端] --> B{连接存储}
  B -->|成功| C[批量遍历目录]
  C --> D[过滤媒体文件]
  D --> E[解析文件名与分辨率]
  E --> F{是否为小文件（<100MB）}
  F -->|是| G[计算文件哈希]
  F -->|否| H[跳过哈希计算]
  G --> I[数据库查重（哈希/路径）]
  H --> I
  I -->|存在| J[更新大小/时间戳]
  I -->|不存在| K[创建文件记录（FileAsset）]
  J --> L[统计更新文件数]
  K --> M[记录新文件ID]
  L --> N[累计统计]
  M --> N
  N --> O[生成扫描结果（ScanResult）]
```

## 刮削流程

```mermaid
flowchart LR
  S[输入文件ID] --> T[读取数据库中的文件记录]
  T --> U[解析标题/年份/季集信息]
  U --> V{确定媒体类型（电影/剧集/集）}
  V --> W[调用刮削管理器进行搜索]
  W --> X{是否命中结果}
  X -->|否| Y[记录未命中并返回失败]
  X -->|是| Z[选择最佳匹配并获取详情]
  Z --> AA[保存到媒体核心并关联文件]
  AA --> AB[写入NFO/海报/背景图到存储]
  AB --> AC[提交事务并返回成功]
```

## 任务生命周期

```mermaid
sequenceDiagram
  participant API as API
  participant EASS as 增强异步扫描服务
  participant UTS as 统一任务调度器
  participant TQS as 任务队列服务
  participant UTE as 统一任务执行器
  participant USE as 统一扫描引擎
  participant MTP as 元数据任务处理器

  API->>EASS: 启动扫描(start_async_scan)
  EASS->>UTS: 创建扫描任务(create_scan_task)
  UTS->>TQS: 入队(TaskType.SCAN)
  TQS-->>UTE: 拉取任务
  UTE->>USE: 执行扫描(scan_storage)
  USE-->>UTE: 返回扫描结果(含 new_file_ids)
  UTE-->>TQS: 更新队列任务结果
  UTE->>UTS: 扫描完成后是否创建刮削任务
  UTS->>TQS: 入队(TaskType.METADATA_FETCH)
  TQS-->>UTE: 拉取刮削任务
  UTE->>MTP: 执行元数据丰富(enrich)
  MTP-->>UTE: 返回刮削结果
  UTE-->>TQS: 更新任务状态
```

## 错误与保护

```mermaid
flowchart TD
  P[外部 API 限流] --> Q[限流器：TMDB 10/秒]
  R[故障隔离] --> S[熔断器：连续失败熔断]
  T[队列重试] --> U[重试 3 次，延迟 5 分钟]
  V[大文件哈希策略] --> W[仅计算前后 10MB]
  X[失败处理] --> Y[记录错误详情]
```

## 关键代码参考

- 扫描入口：`services/scan/unified_scan_engine.py:383`
- 单文件处理：`services/scan/unified_scan_engine.py:211`
- 哈希计算与大文件优化：`services/scan/unified_scan_engine.py:166`
- 入库逻辑（创建/更新）：`services/scan/unified_scan_engine.py:318`
- 异步任务创建：`services/scan/enhanced_async_scan_service.py:58`
- 调度器创建扫描任务：`services/scan/unified_task_scheduler.py:99`
- 调度器创建刮削任务（分批）：`services/scan/unified_task_scheduler.py:163`
- 刮削器丰富：`services/media/metadata_enricher.py:32`
- 侧车写入：`services/media/metadata_enricher.py:211`