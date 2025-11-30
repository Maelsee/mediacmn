# 扫描与丰富化（刮削）解耦与优化方案

## 现状
- 组合任务中由调度器直接创建元数据任务，耦合扫描结果数据结构（`services/task/unified_task_scheduler.py:362`）。
- 丰富化核心在 `services/media/metadata_enricher.py:34`，限流与断路器在 `services/media/metadata_task_processor.py`。

## 目标
- 通过事件总线完成“扫描 → 丰富化”的解耦：扫描只发布事件，丰富化独立消费并创建自身任务。

## 方案
- 事件类型：`NewFilesDiscovered`、`FileUpdated`、`ScanCompleted`，载荷包括 `{storage_id, file_ids[], parse_snapshot_map?, encountered_paths[]}`。
- 生产者：统一扫描引擎/调度器；消费者：`MetadataTaskProcessor` 与删除对齐处理器。
- 调度器调整：移除硬编码的 `create_metadata_task` 调用，改为发布事件；元数据处理器订阅事件并批量创建 `METADATA_FETCH` 任务。
- 语言策略：由 `scraper_manager` 决策（语言回退与插件选择），扫描阶段不涉及语言参数。
- 侧车文件：继续异步化处理，参考 `docs/sidecar_async_localization.md:73`，与丰富化逻辑解耦。

## 可靠性
- 事件发布失败可重试；消费者失败不影响扫描任务完成状态。
- 限流与断路器保留在刮削侧，扫描只负责 I/O 枚举与入库。

## 验收
- 在扫描完成后，无需修改扫描代码即可替换或增加新的丰富化处理器。

## 参考定位
- 调度器组合任务：`services/task/unified_task_scheduler.py:362`
- 丰富化入口：`services/media/metadata_enricher.py:34`
- 元数据任务处理器：`services/media/metadata_task_processor.py:1-32`

