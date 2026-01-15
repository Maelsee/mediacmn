# MediaCMN 后端 API 文档（Markdown 版）

本文件为前端/第三方调用的详细接口说明，统一基于 FastAPI，所有受保护接口使用 Bearer JWT 鉴权。

- 基础路径前缀：`/api`
- 文档入口：Swagger UI `/api/docs`，Redoc `/api/redoc`，OpenAPI JSON `/api/openapi.json`
- 认证方式：`Authorization: Bearer <access_token>`

## 通用约定

### 鉴权

- 受保护接口：请求头携带 `Authorization: Bearer <access_token>`
- 登录成功后获取 `access_token` 与 `refresh_token`：
  - `access_token` 用于访问受保护接口
  - `refresh_token` 用于换取新的 `access_token`

### Content-Type

- JSON 请求体：`Content-Type: application/json`

### 时间格式

- 文档中出现的时间字段均为 ISO 8601 字符串（例如：`2026-01-14T10:00:00Z`）

### 常见错误结构

- FastAPI 默认错误：
```json
{ "detail": "Not authenticated" }
```
- 业务错误（部分接口使用）：
```json
{
  "detail": {
    "code": "media_not_found",
    "message": "媒体不存在或无权限"
  }
}
```

---

## 认证（auth）

### 注册
- 方法与路径：`POST /api/auth/register`
- 鉴权：无需
- 请求体：
```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```
- 响应：`201`
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true
}
```

### 登录
- 方法与路径：`POST /api/auth/login`
- 鉴权：无需
- 请求体：
```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```
- 响应：`200`
```json
{
  "access_token": "<JWT>",
  "refresh_token": "<REFRESH_TOKEN>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 当前用户信息
- 方法与路径：`GET /api/auth/me`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true
}
```

### 刷新令牌
- 方法与路径：`POST /api/auth/refresh`
- 鉴权：无需
- 请求体：
```json
{
  "refresh_token": "<REFRESH_TOKEN>"
}
```
- 响应：`200`
```json
{
  "access_token": "<NEW_JWT>",
  "refresh_token": null,
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 吊销刷新令牌
- 方法与路径：`POST /api/auth/revoke`
- 鉴权：无需
- 请求体：
```json
{
  "refresh_token": "<REFRESH_TOKEN>"
}
```
- 响应：`200`
```json
{ "message": "Token revoked successfully" }
```

### 令牌信息
- 方法与路径：`GET /api/auth/tokens/info`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{
  "user_id": 1,
  "active_tokens": 2,
  "expires_at": "2026-01-14T12:00:00Z",
  "issued_at": "2026-01-14T11:00:00Z"
}
```

### 注销
- 方法与路径：`POST /api/auth/logout`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{ "message": "Successfully logged out. Revoked 2 tokens." }
```

---

## 健康检查（health）

### 存活检查
- 方法与路径：`GET /api/health/live`
- 鉴权：无需
- 响应：`200`
```json
{ "status": "live" }
```

### 就绪检查
- 方法与路径：`GET /api/health/ready`
- 鉴权：无需
- 响应：`200`
```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis_queue": "ok",
    "redis_cache": "ok"
  }
}
```

---

## 媒体（media）

### 过滤卡片
- 方法与路径：`GET /api/media/cards`
- 鉴权：Bearer JWT
- 查询参数：`page`、`page_size`、`q`、`type`、`genres`、`year`、`year_start`、`year_end`、`countries`、`sort`
- 响应：`200`
```json
{
  "page": 1,
  "page_size": 24,
  "total": 100,
  "items": [
    {
      "id": 12,
      "name": "示例电影",
      "cover_url": "https://.../poster.jpg",
      "rating": 8.5,
      "release_date": "2025-12-01",
      "media_type": "movie"
    }
  ]
}
```

### 首页卡片
- 方法与路径：`GET /api/media/cards/home`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{
  "genres": [{"id":1,"name":"剧情"}],
  "movie": [],
  "tv": [],
  "animation": [],
  "reality": []
}
```

### 媒体详情
- 方法与路径：`GET /api/media/{id}/detail`
- 鉴权：Bearer JWT
- 路径参数：`id`
- 响应：`200`
```json
{
  "id": 12,
  "title": "示例剧集",
  "poster_path": "...",
  "backdrop_path": "...",
  "rating": 8.1,
  "release_date": "2025-11-20",
  "overview": "...",
  "genres": ["剧情"],
  "versions": [{"id":101,"quality":"1080p","assets":[]}],
  "media_type": "tv",
  "season_count": 3,
  "episode_count": 24,
  "seasons": [{"id":22,"season_number":1,"title":"第一季"}]
}
```

### 播放直链
- 方法与路径：`GET /api/media/play/{file_id}`
- 鉴权：Bearer JWT
- 路径参数：`file_id`
- 响应：`200`
```json
{
  "file_id": 1001,
  "playurl": "https://dav.example.com/dav/series/S01/EP01.mkv",
  "headers": {"Authorization": "Basic base64(user:pass)"},
  "expires_at": 1736850000,
  "format": "file",
  "source_type": "webdav"
}
```

### 字幕列表
- 方法与路径：`GET /api/media/file/{file_id}/subtitles`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{
  "file_id": 1001,
  "items": [
    {"id":"sub-1","name":"中文","path":"/subs/ep01.zh.srt","size":10240,"language":"zh","url":"https://..."}
  ]
}
```

### 字幕内容
- 方法与路径：`GET /api/media/file/{file_id}/subtitles/content`
- 鉴权：Bearer JWT
- 查询参数：`path`
- 响应：`200`
```json
{ "file_id": 1001, "path": "/subs/ep01.zh.srt", "content": "SRT 文本..." }
```

### 选集列表
- 方法与路径：`GET /api/media/file/{file_id}/episodes`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{
  "file_id": 1001,
  "season_version_id": 777,
  "episodes": [
    {
      "id": 3001,
      "episode_number": 1,
      "title": "第1集",
      "still_path": "...",
      "assets": [{"file_id":1001,"path":"/S01/EP01.mkv"}]
    }
  ]
}
```

### 手动匹配（绑定 TMDB）
- 方法与路径：`PUT /api/media/{media_id}/manual-match`
- 鉴权：Bearer JWT
- 请求体（示例：绑定电影或剧集单集）：
```json
{
  "target": {
    "local_media_id": 12,
    "type": "tv",
    "provider": "tmdb",
    "tmdb_tv_id": 12345,
    "season_number": 1
  },
  "items": [
    {
      "file_id": 1001,
      "action": "bind_episode",
      "tmdb": {"episode_number": 1}
    }
  ],
  "client_request_id": "optional-guid"
}
```
- 响应：`200`
```json
{
  "success": true,
  "effective_media_id": 12,
  "task_id": "persist-batch-xyz",
  "accepted": 1,
  "updated": 1,
  "skipped": 0,
  "errors": []
}
```

---

## 播放记录（playback）

### 上报播放进度
- 方法与路径：`POST /api/playback/progress`
- 鉴权：Bearer JWT
- 请求体：
```json
{
  "file_id": 1001,
  "position_ms": 120000,
  "duration_ms": 300000,
  "status": "playing",
  "device_id": "browser-chrome",
  "platform": "web"
}
```
- 响应：`200` `{ "success": true }`

### 获取播放进度
- 方法与路径：`GET /api/playback/progress/{file_id}`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{ "position_ms": 120000, "duration_ms": 300000, "updated_at": "2026-01-14T10:00:00Z" }
```

### 删除播放进度
- 方法与路径：`DELETE /api/playback/progress/{file_id}`
- 鉴权：Bearer JWT
- 响应：`200` `{ "success": true }`

### 最近播放卡片
- 方法与路径：`GET /api/playback/recent`
- 鉴权：Bearer JWT
- 查询参数：`limit`、`page`、`page_size`、`sort`、`dedup`
- 响应：`200`
```json
[{
  "id": 12,
  "name": "示例剧集 第1季 第1集",
  "cover_url": "...",
  "media_type": "tv",
  "position_ms": 120000,
  "duration_ms": 300000,
  "file_id": 1001
}]
```

---

## 存储服务（storage-server）

### 测试连接
- 方法与路径：`GET /api/storage-server/{storage_id}/test`
- 鉴权：当前实现未强制
- 响应：`200`
```json
{ "success": true, "response_time_ms": 42.3 }
```

### 列出目录
- 方法与路径：`GET /api/storage-server/{storage_id}/list`
- 鉴权：当前实现未强制
- 查询参数：`path`、`depth`
- 响应：`200`
```json
{ "entries": [{"name":"S01","path":"/S01","is_dir":true}], "path": "/", "total_count": 1 }
```

### 仅列目录
- 方法与路径：`GET /api/storage-server/{storage_id}/listdir`
- 鉴权：当前实现未强制
- 查询参数：`path`、`depth`

### 存储信息
- 方法与路径：`GET /api/storage-server/{storage_id}/info`
- 鉴权：当前实现未强制
- 查询参数：`path`

### 文件信息
- 方法与路径：`GET /api/storage-server/{storage_id}/file-info`
- 鉴权：当前实现未强制
- 查询参数：`path`

### 创建目录
- 方法与路径：`POST /api/storage-server/{storage_id}/create-directory`
- 鉴权：当前实现未强制
- 查询参数：`path`

### 删除路径
- 方法与路径：`DELETE /api/storage-server/{storage_id}/delete`
- 鉴权：当前实现未强制
- 查询参数：`path`

### 启用/禁用配置
- 方法与路径：`POST /api/storage-server/{storage_id}/enable`
- 方法与路径：`POST /api/storage-server/{storage_id}/disable`
- 鉴权：Bearer JWT

---

## 存储配置（storage-config）

- 方法与路径：`GET /api/storage-config/statistics`
- 方法与路径：`GET /api/storage-config/`
- 方法与路径：`GET /api/storage-config/{storage_id}`
- 方法与路径：`POST /api/storage-config/`
- 方法与路径：`PUT /api/storage-config/{storage_id}`
- 方法与路径：`DELETE /api/storage-config/{storage_id}`

- 鉴权：Bearer JWT（全部接口）

请求/响应模型详见：`schemas/storage_serialization.py`

---

## 扫描（scan）

### 启动扫描
- 方法与路径：`POST /api/scan/start`
- 鉴权：Bearer JWT
- 请求体：
```json
{
  "storage_id": 10,
  "scan_path": ["/S01", "/S02"],
  "priority": "normal"
}
```
- 响应：`200`
```json
{
  "success": true,
  "message": "扫描任务已成功启动",
  "task_id": "task-xyz",
  "task_type": "scan",
  "status": "pending",
  "created_at": "2026-01-14T10:00:00Z"
}
```

### 查询任务状态
- 方法与路径：`GET /api/scan/status/{task_id}`
- 鉴权：Bearer JWT
- 响应：`200`
```json
{
  "task_id": "task-xyz",
  "task_type": "scan",
  "status": "running",
  "created_at": "...",
  "started_at": "...",
  "finished_at": null,
  "error_code": null,
  "error_message": null,
  "payload": {"user_id": 1, "storage_id": 10, "scan_path": "/S01"}
}
```

---

## 任务生产者（tasks）

- `POST /api/tasks/scan`（Query：`storage_id`,`scan_path`）
- `POST /api/tasks/metadata`（Body：`file_ids`，`storage_id?`）
- `POST /api/tasks/persist`（Body：`file_id`,`contract_type`,`contract_payload`,`path_info`）
- `POST /api/tasks/delete`（Body：`to_delete_ids`）
- `POST /api/tasks/localize`（Body：`file_id`,`storage_id`）
- `GET  /api/tasks/list`（Query：`status`,`type`,`limit`）
- `GET  /api/tasks/{task_id}`
- `POST /api/tasks/dlq/requeue/{task_id}`

- 鉴权：
  - create 系列（scan/metadata/persist/delete/localize）：Bearer JWT
  - list/status/requeue：当前实现未强制

示例响应（创建元数据任务）：
```json
{
  "success": true,
  "message": "元数据任务已创建",
  "task_id": "metadata-abc",
  "task_type": "metadata",
  "status": "pending"
}
```

---

## TMDB 代理（tmdb）

- `GET /api/tmdb/search/tv`（Query：`q`,`page`,`language`）
- `GET /api/tmdb/search/movie`（Query：`q`,`page`,`language`）
- `GET /api/tmdb/tv/{series_tmdb_id}`（Query：`language`）
- `GET /api/tmdb/tv/{series_tmdb_id}/season/{season_number}`（Query：`language`）

- 鉴权：Bearer JWT（全部接口）

示例响应（搜索电影）：
```json
{
  "page": 1,
  "total": 100,
  "items": [
    {"id": 603, "title": "黑客帝国", "original_language": "en", "release_date": "1999-03-31"}
  ]
}
```

---

## 错误返回与状态码

- 统一使用 HTTP 状态码：`400`（参数错误）、`401`（未认证）、`403`（无权限）、`404`（资源不存在）、`500/502/504`（服务/上游错误）
- 错误响应示例：
```json
{
  "detail": {
    "code": "media_not_found",
    "message": "媒体不存在或无权限"
  }
}
```

---

## 备注

- 部分下载直链在浏览器环境下可能使用 Basic Auth 头部（已在后端生成），前端调用时无需自行拼接。
- 所有受保护接口需携带 Bearer JWT；登录获取的 `access_token` 通过请求头传递。
