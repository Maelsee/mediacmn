# 扫描与存储解耦重构方案

## 目标
- 支持任意后端存储（WebDAV/SMB/Local/Cloud），扫描与具体协议完全解耦。
- 以统一抽象契约驱动扫描，新增存储仅需扩展一个适配器，不影响扫描引擎。

## 设计
- 统一存储抽象：`StorageClient`（`services/storage/storage_client.py`）提供 `connect/info/list_dir` 等操作，具体协议在 `storage_clients/*`。
- 扫描源适配器：在扫描引擎内引入 `ScanSource`（协议无关），包装 `StorageClient` 产出 `StorageEntry` 流；实现分页、限流、重试。
- 扫描管线：`Enumerator → Classifier → FileAssetProcessor → PostProcessors`，全部依赖 `StorageEntry` 与文件名解析器，不感知协议类型。
- 调度分层：扫描任务由 `UnifiedTaskScheduler` 下发（`services/task/unified_task_scheduler.py:108`），扫描执行仅依赖 `ScanSource`；组合任务不直接调用丰富化，而是发布事件（解耦见另文）。

## 扩展支持
- SMB/Local 已具备客户端实现（`services/storage/storage_clients/smb_client.py`、`local_client.py`），只需接入 `ScanSource`。
- Cloud：基于 `CloudStorageConfig`（`services/storage/storage_service.py:64`），新增如 S3/GDrive 适配器，实现只读枚举与分页；在 `StorageClientFactory` 注册。

## 关键策略
- 路径归一与相对路径：以存储根为基，持久化 `FileAsset.relative_path`；保证跨协议一致性。
- 批处理与幂等：枚举层 batch 推送，处理器幂等 upsert；失败记录但不中断扫描。
- 观测与配额：在适配器层统计 `list_dir` 次数与延迟，暴露到健康监控；必要时限流。

## 代码定位
- 存储服务：`services/storage/storage_service.py:110, 369`
- WebDAV 客户端：`services/storage/storage_clients/webdav_client.py`
- SMB 客户端：`services/storage/storage_clients/smb_client.py`
- Local 客户端：`services/storage/storage_clients/local_client.py`
- 扫描引擎与处理器：`services/scan/unified_scan_engine.py:457, 470`

