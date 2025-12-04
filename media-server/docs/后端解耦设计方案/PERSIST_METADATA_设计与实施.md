# PERSIST_METADATA 任务与批量持久化设计与实施

## 背景与目标
- 现状：丰富器在刮削后直接调用持久化写库，单文件频繁提交事务，耦合紧、吞吐受限。
- 目标：将持久化改为独立任务（`PERSIST_METADATA`），丰富器只负责刮削与构造契约并入队；持久化执行器批量消费与写库，降低事务开销并提升吞吐。

## 任务类型
- 新增任务类型：`persist_metadata`（`TaskType.PERSIST_METADATA`）。
  - 位置：`media-server/services/task/task_queue_service.py:46-57`（枚举）
  - 消费支持：`media-server/services/task/unified_task_executor.py:91-95` 增加消费类型；批量执行逻辑见同文件。
  - 调度执行：`media-server/services/task/unified_task_scheduler.py:261-271` 增加持久化任务分支。

## 任务参数契约（Envelope）
- `file_id:int`｜`user_id:int`｜`storage_id:Optional[int]`
- `contract_type:str` ∈ `movie|series|season|episode`
- `contract_payload:dict`（刮削详情，见下）
- `version_context:dict`（版本绑定线索）
  - `scope:"movie_single"|"season_group"|"series_group"|"episode_single"`
  - `quality:Optional[str]`｜`source:Optional[str]`｜`edition:Optional[str]`｜`variant_fingerprint:Optional[str]`
- `provider:str`｜`language:str`
- `idempotency_key:str`（建议：`"{user_id}:{file_id}:{provider}:{contract_type}:{external_primary_key}"`）

### movieresult（contract_type="movie"）
```json
{
  "movie_id": "550",
  "title": "Fight Club",
  "original_title": "Fight Club",
  "original_language": "en",
  "overview": "...",
  "release_date": "1999-10-15",
  "runtime": 139,
  "tagline": "Mischief. Mayhem. Soap.",
  "genres": ["Drama"],
  "poster_path": "https://image.tmdb.org/.../poster.jpg",
  "backdrop_path": "https://image.tmdb.org/.../backdrop.jpg",
  "vote_average": 8.4,
  "vote_count": 30000,
  "imdb_id": "tt0137523",
  "status": "Released",
  "belongs_to_collection": null,
  "popularity": 50.0,
  "provider": "tmdb",
  "provider_url": "https://www.themoviedb.org/movie/550",
  "artworks": [],
  "credits": [],
  "external_ids": [{"provider":"tmdb","external_id":"550"}],
  "raw_data": {"id": 550}
}
```

### episoderesult（contract_type="episode"，嵌套 series/season）
```json
{
  "episode_id": "123",
  "episode_number": 1,
  "season_number": 1,
  "name": "Pilot",
  "overview": "...",
  "air_date": "2020-01-01",
  "runtime": 45,
  "still_path": "https://image.tmdb.org/.../still.jpg",
  "vote_average": 7.0,
  "vote_count": 100,
  "provider": "tmdb",
  "provider_url": "https://www.themoviedb.org/tv/9999/season/1/episode/1",
  "artworks": [],
  "credits": [],
  "external_ids": [{"provider":"tmdb","external_id":"123"}],
  "episode_type": "standard",
  "absolute_episode_number": 1,
  "raw_data": {"id": 123},
  "season": {
    "season_id": "8888",
    "season_number": 1,
    "name": "Season 1",
    "poster_path": null,
    "overview": "...",
    "episode_count": 10,
    "air_date": "2020-01-01",
    "vote_average": 7.5,
    "provider": "tmdb",
    "provider_url": "https://www.themoviedb.org/tv/9999/season/1",
    "artworks": [],
    "credits": [],
    "external_ids": [],
    "raw_data": {"id": 8888}
  },
  "series": {
    "series_id": "9999",
    "name": "Show",
    "original_name": "Show",
    "origin_country": ["US"],
    "overview": "...",
    "tagline": null,
    "status": "Returning Series",
    "first_air_date": "2020-01-01",
    "last_air_date": "2020-02-01",
    "episode_run_time": [45],
    "number_of_episodes": 10,
    "number_of_seasons": 1,
    "genres": ["Drama"],
    "poster_path": null,
    "backdrop_path": null,
    "vote_average": 7.5,
    "vote_count": 1000,
    "popularity": 20.0,
    "provider": "tmdb",
    "provider_url": "https://www.themoviedb.org/tv/9999",
    "artworks": [],
    "credits": [],
    "external_ids": [{"provider":"tmdb","external_id":"9999"}],
    "raw_data": {"id": 9999},
    "subtype": "reality",
    "original_language": "en",
    "languages": ["en"],
    "networks": ["Netflix"]
  }
}
```

## 丰富器改造（入队持久化）
- 位置：`media-server/services/media/metadata_enricher.py:173-231` 改为入队 `PERSIST_METADATA`，不再直接写库。
- 补充：侧车本地化任务入队逻辑保留在同文件结尾处。
- 关键剧集详情补充 series/season：`media-server/services/media/metadata_enricher.py:148-161`。

## 执行器与调度器批量持久化
- 调度器新增持久化执行：`media-server/services/task/unified_task_scheduler.py:261-271`（单条），`media-server/services/task/unified_task_scheduler.py:309-377`（批量）。
- 执行器批量聚合：`media-server/services/task/unified_task_executor.py:126-169` 对 `PERSIST_METADATA` 使用数量（100）与时间窗（0.8s）聚合批量执行。
- 事务边界：每批统一 `session.commit()`，错误降级分片重试策略建议。

### 批量失败分片重试与监控统计
- 分片重试：当批量提交失败时，执行器在调度器批量方法中将批次二分（递归），直至单条定位失败项；成功分片提交后会合计结果。
  - 入口：`media-server/services/task/unified_task_scheduler.py:568`
  - 行为：`_run(ts)` 遇提交失败回滚并按二分法递归处理；单条失败返回 `commit_failed` 错误。
- 监控统计：执行器扩大统计集，记录批次数量、任务数、成功/失败计数、平均批量大小、最近批次耗时。
  - 入口：`media-server/services/task/unified_task_executor.py:47-60, 141-169, 192-210`
  - 汇总：`get_all_stats` 会包含批量指标汇总（原有汇总逻辑继续有效）。

### 聚合阈值与分桶优化（可配置）
- 环境配置新增：`PERSIST_BATCH_MAX_SIZE`、`PERSIST_BATCH_MAX_WAIT_MS`、`PERSIST_BUCKET_ENABLED`（`media-server/core/config.py:90-96`）。
- 执行器使用配置：
  - 阈值应用：`media-server/services/task/unified_task_executor.py:139-146`。
  - 分桶应用：按 `(contract_type, provider, user_id)` 分组执行，位置 `media-server/services/task/unified_task_executor.py:147-205`。

## 幂等与重试
- 幂等写入由 `metadata_persistence_service.apply_metadata(...)` 内部实现（`ExternalID` 去重等）。
- 队列层面沿用 `Task.max_retries/retry_delay/timeout`。
- 建议在 Envelope 携带 `idempotency_key`，用于任务去重或审计。

## 验收标准
- 丰富器调用后仅入队，不直接写库；每次只入队一条文件的刮削数据。
- `episoderesult` 在任务参数中包含完整 `series` 与 `season`。
- 持久化执行器能批量消费与写库，单批事务提交，统计成功/失败。

## 代码参考
- 枚举新增类型：`media-server/services/task/task_queue_service.py:46-57`
- 执行器消费类型：`media-server/services/task/unified_task_executor.py:91-95`
- 执行器批量聚合：`media-server/services/task/unified_task_executor.py:126-169`
- 调度器单条持久化：`media-server/services/task/unified_task_scheduler.py:261-271`
- 调度器批量持久化：`media-server/services/task/unified_task_scheduler.py:309-377`
- 丰富器入队改造：`media-server/services/media/metadata_enricher.py:173-231`
- 持久化入口：`media-server/services/media/metadata_persistence_service.py:304`

## 后续优化（建议）
- 批量执行失败分片重试策略与监控面板统计增强。
- 版本绑定逻辑根据 `version_context.scope` 细化到 `episode_single` 与季/系列聚合。
- Redis 队列健康检查与降级本地队列方案。


**触发时机**
- 单条持久化：当外界直接调用 `scheduler.execute_task(task)` 且类型为 `PERSIST_METADATA`，会走 `_execute_persist_metadata_task(...)`（`media-server/services/task/unified_task_scheduler.py:282-306`）。
- 批量持久化：当统一执行器主循环抓到 `PERSIST_METADATA`，会做半秒级聚合到至多 100 条，再调用 `execute_persist_batch(...)`（`media-server/services/task/unified_task_executor.py:126-169` → `media-server/services/task/unified_task_scheduler.py:568`）。

**完整任务流程**
- 扫描与元数据任务
  - 创建扫描任务：`UnifiedTaskScheduler.create_scan_task(...)`，入队 `SCAN`；执行于 `media-server/services/task/unified_task_scheduler.py:287-335`。
  - 组合任务（可选）：`COMBINED_SCAN` 在扫描后自动按新文件入队 `METADATA_FETCH`（`media-server/services/task/unified_task_scheduler.py:363-439`）。
- 元数据丰富
  - 执行 `METADATA_FETCH` 时，调度器逐文件调用丰富器 `metadata_enricher.enrich_media_file(...)`（`media-server/services/task/unified_task_scheduler.py:339-357`）。
  - 丰富器搜索与详情获取；若为剧集，会补充 `series/season`（`media-server/services/media/metadata_enricher.py:148-161`）。
  - 丰富器不再直接写库，而是为每个文件入队一条 `PERSIST_METADATA`（`media-server/services/media/metadata_enricher.py:173-231`），同时可入队 `SIDECAR_LOCALIZE`。
- 持久化执行
  - 执行器抓到 `PERSIST_METADATA` 时批量聚合（最多 100 条，等待不超过 0.8s），并调用 `scheduler.execute_persist_batch(...)`，统一事务写库（`media-server/services/task/unified_task_executor.py:126-169` → `media-server/services/task/unified_task_scheduler.py:568`）。
  - 若调用链是单条（例如测试或外部单次触发），则由调度器的 `_execute_persist_metadata_task(...)` 单条执行（`media-server/services/task/unified_task_scheduler.py:282-306`）。
- 侧车本地化
  - 独立任务 `SIDECAR_LOCALIZE` 在丰富器阶段入队（`media-server/services/media/metadata_enricher.py:231-266`），由调度器执行（`media-server/services/task/unified_task_scheduler.py:482-493`）。
- 监控统计
  - 执行器批量路径会记录批次数、批量任务数、成功/失败、平均批量大小、最近批次耗时（`media-server/services/task/unified_task_executor.py:47-60, 141-169, 192-210`）。
  - 管理器汇总接口保留现有成功率与总体统计（`media-server/services/task/unified_task_executor.py:267-292`）。

**如何理解“默认没有批量”**
- “默认”指调度器内部的通用 `execute_task(...)` 分派逻辑：当它被直接调用时，会把 `PERSIST_METADATA` 当单条处理（`media-server/services/task/unified_task_scheduler.py:282-283`）。
- “批量”是由执行器的业务策略触发：执行器在拉到一条 `PERSIST_METADATA` 后，主动在短时间窗继续拉取同类型任务，组装成批，调用调度器的批量接口（调度器自身并不自动聚合），因此 `execute_persist_batch(...)` 的用法是“由执行器调用”，不是“调度器默认执行”。

**可调参数与扩展建议**
- 聚合阈值与时间窗：在执行器 `media-server/services/task/unified_task_executor.py:126-134`，可调“100”和“0.8”以适配不同吞吐。
- 分桶优化：可在批量前按 `contract_type/provider/user_id` 分桶，进一步提升提交成功率与缓存命中（目前为通用批量）。
- 失败分片重试：批量提交失败会二分递归定位失败项（`media-server/services/task/unified_task_scheduler.py:568-658`），可增加最大分片深度或退避策略以平衡延迟与稳定性。
  
  
          
**策略实现位置**
- 执行器批量聚合与触发点在 `media-server/services/task/unified_task_executor.py:139-149`：
  - 当抓到一条 `PERSIST_METADATA` 时，执行器在一个短时间窗内（默认 0.8s）继续从队列拉取同类型任务，直到达到最大聚合数量（默认 100）或时间窗到期。
  - 聚合完成后调用 `scheduler.execute_persist_batch(batch)` 进行统一事务的批量持久化。

**可配置阈值**
- 新增配置项（从环境读取）：
  - `PERSIST_BATCH_MAX_SIZE`：最大批量任务数（默认 100）
  - `PERSIST_BATCH_MAX_WAIT_MS`：批量聚合最大等待毫秒数（默认 800）
  - `PERSIST_BUCKET_ENABLED`：是否启用分桶（默认 True）
- 配置定义：`media-server/core/config.py:90-96`
- 执行器使用配置：
  - 阈值应用：`media-server/services/task/unified_task_executor.py:139-146`

**分桶优化**
- 分桶维度：`(contract_type, provider, user_id)`
- 实现位置：`media-server/services/task/unified_task_executor.py:147-205`
  - 当开启 `PERSIST_BUCKET_ENABLED` 且批量任务数大于 1 时，执行器将批次按分桶维度拆分为多个组，逐组调用 `execute_persist_batch(group)` 提交。
  - 每个分桶分别统计成功/失败并完成任务回写；最后更新批量统计（批次数、平均批量大小、最近批次耗时等）。

**批量失败分片重试**
- 调度器批量执行函数：`media-server/services/task/unified_task_scheduler.py:568`
  - 内部 `_run(ts)` 尝试整批事务提交；提交失败则回滚并对批次按二分法递归分片（`mid = len(ts)//2`）。
  - 直至单条定位失败项（返回 `commit_failed`），成功分片会累积进“成功数与结果”。
  - 返回数据中包含 `processed/succeeded/results/errors`，执行器据此对每条任务写回结果。

**监控统计**
- 执行器统计字段：`media-server/services/task/unified_task_executor.py:47-60`
  - `batch_persist`: `batches/tasks/succeeded/failed/avg_batch_size/last_batch_duration`
- 更新统计逻辑：`media-server/services/task/unified_task_executor.py:141-169`（非分桶）与 `media-server/services/task/unified_task_executor.py:147-205`（分桶）
- 对外汇总：`get_stats()` 返回扩展的批量指标，管理器 `get_all_stats()` 汇总各执行器成功率与批量信息

**任务流程简述**
- 扫描任务（`SCAN/COMBINED_SCAN`）
  - 扫描完成后（组合任务）入队 `METADATA_FETCH`，详见 `media-server/services/task/unified_task_scheduler.py:363-439`
- 元数据任务（`METADATA_FETCH`）
  - 调用丰富器 `metadata_enricher.enrich_media_file(...)`，刮削后入队 `PERSIST_METADATA` 每文件一条
- 持久化任务（`PERSIST_METADATA`）
  - 执行器抓到单条→批量聚合→分桶执行→批量提交→失败分片重试；详见上述位置
- 侧车本地化（`SIDECAR_LOCALIZE`）
  - 丰富器阶段入队，调度器执行，见 `media-server/services/media/metadata_enricher.py:231-266` 和 `media-server/services/task/unified_task_scheduler.py:482-493`

**如何调整策略**
- 在 `media-server/.env` 或环境变量中设置：
  - `PERSIST_BATCH_MAX_SIZE=50`
  - `PERSIST_BATCH_MAX_WAIT_MS=1000`
  - `PERSIST_BUCKET_ENABLED=false`
- 无须重启执行器（如果设置在进程启动前加载），执行器从 `get_settings()` 读取配置并应用到批量聚合和分桶逻辑。

**参考定位**
- 阈值与分桶配置：`media-server/core/config.py:90-96`
- 批量聚合与分桶执行：`media-server/services/task/unified_task_executor.py:139-205`
- 调度器批量分片重试：`media-server/services/task/unified_task_scheduler.py:568`
- 单条持久化：`media-server/services/task/unified_task_scheduler.py:282-306`