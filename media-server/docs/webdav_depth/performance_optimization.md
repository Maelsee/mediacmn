# Media Server 性能优化说明

## 概述
- 目标：降低单文件元数据丰富与侧车本地化总体耗时；减少日志噪声，提升吞吐与可观测性。
- 范围：TMDB刮削插件、元数据丰富器侧车写入、统一任务队列与执行器日志策略、配置项与并发建议。

## 已实施优化
- 刮削阶段：
  - 共享会话复用，减少HTTP握手与连接开销。
  - 图片配置缓存（TTL 30分钟），避免重复获取。
  - 详情聚合参数 `append_to_response=external_ids,keywords,credits,images`，在 `get_details` 优先消费聚合返回的 `credits/images`，仅在缺失时请求独立端点。
- 侧车阶段：
  - 有界并发上传（并发=2），同时上传 `.nfo` 与精选艺术作品。
  - 艺术作品筛选：语言优先与评分排序，限额由 `SIDE_CAR_LOCALIZATION_ARTWORK_LIMIT` 控制（默认 2）。
  - 上传耗时打印（debug），用于并发与限额调优。
- 日志策略：
  - 任务队列：仅在任务完成时输出 info；连接、入队、出队、取消、清理等降为 debug。
  - 执行器/调度器：流程性日志降为 debug，仅保留任务完成（成功/失败）必要日志。

## 配置项
- `SIDE_CAR_LOCALIZATION_ENABLED`（bool，默认 true）：是否启用侧车异步本地化。
- `SIDE_CAR_LOCALIZATION_ARTWORK_LIMIT`（int，默认 2）：侧车阶段写入的艺术作品最大数量（建议 2：`poster.jpg` + `fanart.jpg`）。
- `TASK_EXECUTOR_COUNT`（int，默认 1）：统一任务执行器并发数（建议 2–3，需结合限流/熔断）。

## 运行指标与样例
- 优化前：
  - `metadata_fetch` ≈ 9.85s；`sidecar_localize` ≈ 13.36s；总计 ≈ 23s。
- 优化后（样例日志）：
  - `metadata_fetch` ≈ 3.58s；`sidecar_localize` ≈ 4.79–5.91s；总计 ≈ 8–10s。
- 观测方法：
  - 查看统一调度器统计的任务耗时（完成日志 info）。
  - 侧车上传耗时（debug）用于评估并发与限额效果。

## 操作指南
- 调整侧车限额：在 `.env` 设置 `SIDE_CAR_LOCALIZATION_ARTWORK_LIMIT=2`。
- 调整执行器并发：在 `.env` 设置 `TASK_EXECUTOR_COUNT=2` 或 `3`，启动时读取并按值创建执行器。
- 并发与速率：
  - 根据侧车上传耗时日志（debug）评估网络状况，选择并发=2–3；过大并发可能触发远端限流或不稳定。
  - 与 `MetadataTaskProcessor` 的限流与熔断策略协同，避免批量刮削触发外部API限制。

## 日志策略清单
- 队列服务（TaskQueueService）：
  - `complete_task`：info；其余（connect、enqueue、dequeue、cancel、cleanup）：debug。
- 执行器（UnifiedTaskExecutor）：
  - 开始/启动/停止/被取消：debug。
  - 任务成功：info；失败：warning/error。
- 调度器（UnifiedTaskScheduler）：
  - 初始化、创建任务、执行开始/完成、组合任务中间信息、删除对齐完成：debug。
  - 错误与权限警告：error/warning。

## 未来工作
- 详情聚合完全落地：TV端点兼容性检测，确保 credits/images 聚合覆盖更多场景。
- 响应缓存：为 `details:{provider_id}:{language}` 增加短期缓存（Redis），提升重复刮削命中率。
- 并发与限流联动：将插件请求计数与失败计数暴露给 `plugin_manager`，与处理器的 `RateLimiter/CircuitBreaker` 动态联动。