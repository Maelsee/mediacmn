## 目标
- 删除与媒体展示无关的旧路由：扫描相关、文件列表/详情、队列健康检查。
- 保留并整理两条媒体接口：卡片列表 `/media/cards` 与详情 `/media/{id}/detail`。
- 收敛 imports，移除未使用的依赖。

## 变更清单
- 移除：
  - POST `/media/scan/start`
  - GET `/media/scan/status`
  - POST `/media/scan/stop`
  - GET `/media/files`
  - GET `/media/files/{file_id}`
  - GET `/media/queue/health`
- 保留：
  - GET `/media/cards`
  - GET `/media/{id}/detail`
- 删除未用 imports：`EnhancedAsyncScanService`, `StorageConfig`, `ScanJob`, `select`, `BackgroundTasks`, 以及相关初始化变量。

## 验收
- 路由文件只暴露两条媒体展示接口；启动应用无 import/引用错误。