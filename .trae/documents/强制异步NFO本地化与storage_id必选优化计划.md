# 现状与问题
- NFO生成逻辑：本地根据 `ScraperResult` 组装 XML（非从 TMDB 直接获取文件），生成函数 `services/media/metadata_enricher.py:1029`。
- 触发时机：当前已改为丰富器先入队 `SIDECAR_LOCALIZE`，但存在“队列不可用或缺少 storage_id 时回退同步写入”的路径（`metadata_enricher.py:219-259`）。
- 诉求：
  - 仅在异步本地化阶段生成 NFO（取消同步回退）。
  - `storage_id` 必选，缺失即不入队并提示。
  - 通过环境变量控制是否启用侧车本地化。

# 目标行为
- 当 `SIDE_CAR_LOCALIZATION_ENABLED=true` 时：在 `enrich_media_file` 完成 DB 写入后，强制入队侧车本地化任务；任务必须携带 `storage_id`；NFO 与海报仅在异步处理器中生成并上传。
- 当 `SIDE_CAR_LOCALIZATION_ENABLED=false` 时：跳过入队，不进行侧车写入（NFO/海报均不生成）。
- 不再进行“同步回退”；若入队失败或缺少 `storage_id`，仅记录告警，不写侧车。

# 修改方案
## 配置（env）
- 新增布尔开关：`SIDE_CAR_LOCALIZATION_ENABLED`，在 `core.config.get_settings` 中暴露；默认值建议为 `true`，可由环境变量覆盖。
- 可选扩展：`SIDE_CAR_LOCALIZATION_ARTWORK_LIMIT`（默认3）用于控制异步阶段图像数量。

## 丰富器（metadata_enricher.py）
- 在 `enrich_media_file(file_id, preferred_language, storage_id, existing_snapshot)` 中：
  - 检查 `SIDE_CAR_LOCALIZATION_ENABLED`；为 `false` 时直接跳过侧车入队，不写侧车。
  - 为 `true` 时：
    - 校验 `storage_id` 必填；缺失则记录错误并跳过入队。
    - 入队 `SIDECAR_LOCALIZE` 任务；移除所有“同步写入回退”路径。
- `_write_sidecar_files(...)` 保留，但仅由异步处理器调用，不在同步路径调用。

## 调度器与处理器
- 调度器已支持 `SIDECAR_LOCALIZE` 分支（`services/scan/unified_task_scheduler.py:254-264`）；无需接口变更，仅在侧车处理失败时返回失败状态。
- 侧车处理器 `SidecarLocalizeProcessor.process(file_id, storage_id, language)`：
  - 强制 `storage_id` 校验；缺失直接返回失败。
  - 用 `MediaCore.canonical_source` 与 `canonical_external_key` 或任一 `ExternalID` 重建详情；调用 `_write_sidecar_files(...)` 生成并上传 NFO 与海报。

## API 层与任务创建
- 现有 `create_metadata_task` 已向丰富器传递 `storage_id`（`services/scan/unified_task_scheduler.py:210-221`）；无需变更。
- 建议在发起扫描/组合任务的入口处确保 `storage_id` 有效（路由已根据存储名称解析 ID）。

# 验收标准
- 当开关为 `true` 且提供 `storage_id`：
  - 丰富器不再进行同步写侧车；日志仅显示“侧车本地化任务已入队”。
  - 执行器消费后由处理器写入 `.nfo` 与 `poster.jpg/fanart.jpg`；`Artwork.exists_local` 与 `local_path` 更新为真。
- 当开关为 `false` 或 `storage_id` 缺失：
  - 不入队侧车任务；不生成 `.nfo` 与海报；日志包含原因说明。
- 队列异常时：不写侧车，记录错误；不影响 DB 元数据落库与主任务成功态。

# 风险与回滚
- 取消同步回退将导致在队列或插件不可用时不产生侧车文件；但主链路（刮削、入库）不受影响。
- 若需要紧急恢复同步写入，可临时将开关逻辑改回允许回退；或在处理器端提供重试策略提升可靠性。

# 验证与观测
- 单元与集成测试：
  - 用 `SIDE_CAR_LOCALIZATION_ENABLED=true/false` 两态测试入队与跳过行为。
  - 缺失 `storage_id` 测试：确认不入队、不写侧车。
- 运行验证：
  - 观察 Redis 队列键 `task_queue:sidecar_localize:*` 的累计与消费。
  - 检查媒体目录 `.nfo` 与 `poster.jpg/fanart.jpg` 的生成与 Artwork 标记更新。

# 实施顺序
1. 增加配置开关并在丰富器读取。
2. 移除丰富器中的同步回退逻辑，强制 `storage_id` 校验。
3. 在处理器中再次校验 `storage_id` 并保持现有生成上传逻辑。
4. 增加测试用例与日志观测。
