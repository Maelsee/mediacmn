# ACCEPTANCE: 扫描与丰富化解耦

## 1. 功能验证
- [x] **事件发布**：扫描完成后，`UnifiedTaskScheduler` 正确发布了 `ScanCompletedEvent`。
- [x] **元数据丰富触发**：`ScanEventHandler` 监听到事件，根据 `enable_metadata_enrichment` 参数正确创建了 `METADATA_FETCH` 任务。
- [x] **删除同步触发**：`ScanEventHandler` 监听到事件，根据 `enable_delete_sync` 参数正确创建了 `DELETE_SYNC` 任务。
- [x] **参数传递**：扫描参数（如语言、快照）正确传递给了后续任务。

## 2. 代码质量
- **解耦**：`UnifiedTaskScheduler` 不再直接依赖 `MetadataTaskProcessor` 或直接操作元数据任务的创建逻辑。
- **可测试性**：新增了 `test_event_decoupling.py`，通过 Mock 验证了事件流转和处理逻辑。
- **结构清晰**：引入了简单的 `EventBus` 和 `ScanEventHandler`，职责分明。

## 3. 优化建议
- **异步持久化**：目前的 EventBus 是进程内的，如果服务重启，未处理的事件会丢失。未来可以考虑引入 Redis Stream 或 RabbitMQ 实现持久化消息队列。
- **重试机制**：事件处理如果失败，目前仅记录日志。可以增加重试机制或死信队列。
- **监控**：建议增加事件发布和消费的监控指标（Metrics），以便观察系统运行状态。

## 4. 结论
本次重构成功实现了扫描与丰富化的解耦，达到了预期目标。代码结构更加灵活，易于扩展。
