# 删除对齐（Delete Sync）任务化方案 — 6A交付文档

## 1. Align（对齐）
- 现状问题：
  - 第二次扫描未出现的路径（如“蛟龙行动（2025）”）未被软删，数据库与扫描结果不一致。
  - 原实现在组合任务末尾内联执行删除同步，缺少任务化的重试/监控能力；路径前缀不一致导致缺失集合计算失效。
- 目标：
  - 将删除对齐改为标准队列任务（可重试、可监控、可并发控制）。
  - 统一路径前缀规范，确保缺失集合准确。
  - 软删→移动检测→递归级联清理，保证数据库与扫描结果一致。
- 约束：
  - 不改动已有扫描与刮削API契约；删除同步以新任务类型实现。

## 2. Architect（架构）
- 新增任务类型：`DELETE_SYNC`（或复用 `CLEANUP`）。
- 任务流：
  - 组合任务执行完扫描→元数据任务创建后，若启用删除同步，则创建 `DELETE_SYNC` 子任务。
  - `DELETE_SYNC` 任务读取：`storage_id`、`scan_path`、`encountered_media_paths`，执行对齐。
- DeleteSyncService 优化：
  - 缺失集合计算：仅按 `storage_id` 与“不在扫描集合”判定缺失，取消严格 `startswith(scan_path)`；或统一前缀后再过滤。
  - 移动检测：按 `etag` 构建新路径映射，先更新路径状态为 `moved`。
  - 软删分批：每批 N 条更新 `exists=false/status=deleted/deleted_at`，降低事务压力。
  - 递归级联：空集→空季→空系列层层清理；仅在无活动文件且无子项时删除。
- 配置项：
  - `COMBINED_RUN_METADATA_IF_NO_NEW`：无新文件时是否仍执行元数据任务（已加，默认 true）。
  - 新增 `DELETE_SYNC_BATCH_SIZE`（如 100）、`DELETE_SYNC_ENABLED`（默认 true）。

## 3. Atomize（原子化）
- 子任务拆分：
  1. 新增任务类型与调度入口：`TaskType.DELETE_SYNC`，`create_delete_sync_task()`。
  2. 执行器实现：`_execute_delete_sync_task()`，读取扫描结果并调用 `DeleteSyncService`。
  3. `compute_missing()` 修正前缀判定，或在调度器侧规范化 `encountered_media_paths`。
  4. `soft_delete_files()` 增加分批与统计日志。
  5. `detect_moves_by_etag()` 保持现有逻辑，返回更新计数。
  6. `cascade_recursive_cleanup()` 执行递归清理，返回删除统计。
- 输入契约：`{ storage_id, scan_path, encountered_media_paths }`。
- 输出契约：`{ missing_count, moved_files, removed_files, cascade_removed, batches }`。

## 4. Approve（审批）
- 检查清单：
  - 任务化后删除同步不阻塞组合任务，支持独立重试与监控。
  - 缺失集合与路径规范一致，能够识别未出现的文件。
  - 分批软删无锁等待异常，统计日志完整。
  - 递归级联仅在空对象时执行，避免误删。

## 5. Automate（实施）
- 实施步骤：
  1. 在 `TaskType` 增加 `DELETE_SYNC`。
  2. `UnifiedTaskScheduler`：新增 `create_delete_sync_task()` 与 `_execute_delete_sync_task()`；组合任务中改为创建子任务而非内联删除。
  3. `DeleteSyncService.compute_missing()`：取消或可选取消 `startswith(scan_path)`；统一前缀策略。
  4. `soft_delete_files()`：加入分批与详细日志输出；统计 `removed_files` 数量。
  5. 结果写入：在任务结果中记录对齐统计，便于 API 查询。
  6. 配置项：在 `Settings` 添加 `DELETE_SYNC_BATCH_SIZE` 与 `DELETE_SYNC_ENABLED`，并在调度器读取。
- 回退策略：
  - 若删除任务失败，仅影响该子任务；组合任务成功状态不受影响。
  - 通过队列重试与可视化日志定位。

## 6. Assess（评估）
- 验证场景：
  - 场景A：第一次扫描有A/B文件，第二次移除B，开启删除同步→数据库将 B 标记 `exists=false/status=deleted`。
  - 场景B：移动文件（相同 `etag`，不同路径）→数据库更新路径为新值，状态 `moved`。
  - 场景C：系列下空集/空季/空系列→递归清理，最终系列无残留。
- 指标：
  - `missing_count/moved_files/removed_files/cascade_removed` 与日志一致。
  - 删除任务执行时间与批量大小线性相关；无锁等待超时。

## API & 配置
- API：
  - 组合任务：`/api/scan/create-task`（保持不变，内部新增删除子任务）。
  - 任务查询：`/api/task/{task_id}` 可查看删除任务统计。
- 配置：
  - `.env`：
    - `COMBINED_RUN_METADATA_IF_NO_NEW=true|false`
    - `DELETE_SYNC_ENABLED=true|false`
    - `DELETE_SYNC_BATCH_SIZE=100`

## 实施备注
- 现行删除同步入口位于 `services/scan/unified_task_scheduler.py:389-419`；改造为任务后将迁移该逻辑至 `_execute_delete_sync_task()`，并保留现有服务 `services/media/delete_sync_service.py`。
- 为保证一致性，建议将 `FileAsset.full_path` 与 `encountered_media_paths` 都使用 WebDAV 绝对路径；若历史数据不一致，提供一次性路径规范化脚本。

## 验收标准
- 第二次扫描未出现的文件在数据库被软删或标记移动；删除任务结果显示统计数据准确。
- 无新文件时的元数据任务受配置控制；删除同步任务独立执行，不阻塞组合任务。
- 前缀差异不再阻碍缺失集合识别，数据库与扫描结果保持一致。