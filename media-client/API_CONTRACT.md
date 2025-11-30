# 前端 API 契约 v0.1

## 基础约定
- 基址：`AppConfig.baseUrl`（当前为 `http://127.0.0.1:8000`）
- 鉴权：HTTP 请求头携带 `Authorization: Bearer <token>`（登录成功后由客户端设置）
- 编码：`application/json; charset=utf-8`
- WebSocket：将 `http/https` 转换为 `ws/wss`，示例：`ws(s)://<host>/tasks/stream`

## 资源库（Sources）
- GET `/api/storage/`
  - Query：`storage_type?`（筛选：`webdav|smb|local|cloud`）
  - Res：`[{ id, user_id, name, storage_type, status? }]`
  - 状态值：`enabled|disabled|disconnected|error`（用于前端展示连接/可用性与启停状态）
-后端提供资源库所有列表的api：
- GET `/api/storage/`
  - Res：200 OK `[
  {
    "id": 0,
    "user_id": 0,
    "name": "string",
    "storage_type": "webdav|smb|local|cloud",
    "status": "string"
  }
]`



- POST `/sources`
- 后端POST /api/storage/
  - Req（WebDAV 示例）：
    ```json
    {
      "storage_type": "webdav",
      "name": "string",
      "config": {
        "hostname": "https://dav.example.com:5200",
        "login": "string",
        "password": "string",
        "root_path": "/",
        "verify_ssl": true
      }
    }
    ```
  - Res：`{ id: number, name: string, storage_type: string, created_at: string, updated_at: string }`
  - 类型化 `config`：
    - SMB：
      ```json
      {
        "storage_type": "smb",
        "name": "string",
        "config": {
          "server_host": "smb.example.com",
          "server_port": 445,
          "share_name": "movies",
          "username": "string?",
          "password": "string?",
          "domain": "WORKGROUP?",
          "client_name": "MEDIACMN",
          "use_ntlm_v2": true,
          "sign_options": "auto",
          "is_direct_tcp": true
        }
      }
      ```
    - Local：
      ```json
      {
        "storage_type": "local",
        "name": "string",
        "config": {
          "base_path": "/mnt/media",
          "auto_create_dirs": true,
          "use_symlinks": false,
          "follow_symlinks": false,
          "scan_depth_limit": 10,
          "exclude_patterns": "[\"*.tmp\", \".git/*\"]"
        }
      }
      ```
    - Cloud：
      ```json
      {
        "storage_type": "cloud",
        "name": "string",
        "config": {
          "cloud_provider": "aliyun|baidu|onedrive|google|dropbox",
          "access_token": "string?",
          "refresh_token": "string?",
          "client_id": "string?",
          "client_secret": "string?",
          "root_folder_id": "string?",
          "sync_interval": 300,
          "max_file_size": 104857600
        }
      }
      ```
  

- GET `/api/storage/{id}`
  - Res：`{ success: true, message: string, data: { id, user_id, name, hostname,login,root_path,select_path,storage_type, created_at, updated_at, status?, detail } }`

- PUT `/api/storage/{id}`
  - Req（示例）：`{ name: string }`
  - Res：`{ id, name, storage_type, is_active, priority, updated_at }`

- DELETE `/api/storage/{id}`
  - Res：`{ message: string }`

测试当前资源库是否连接成功：
- GET `/api/storage-unified/{storage_id}/test`
  - Res：`{ success: true, message: string }`



// 创建扫描任务
- POST `/sources/{id}/scan`
  - Req：`{ mode?: "manual" }`（当前前端未传 body，后端需兼容）
  - Res：`{ task_id: string }`

- POST /api/scan/create-task
  - Req：
    ```json
    {
    "storage_id": 0,
    "scan_path": "/",
    "scan_type": "full",
    "recursive": true,
    "max_depth": 10,
    "enable_metadata_enrichment": true,
    "enable_delete_sync": true,
    "priority": "normal",
    "batch_size": 100
    }
    ```
  - Res：`{
  "success": true,
  "message": "string",
  "task_id": "string",
  "task_type": "string",
  "status": "string",
  "created_at": "string"
}`


- POST `/sources/{id}/enable`
  - Res：`204`
  - 效果：源状态切换为 `enabled`

- POST `/sources/{id}/disable`
  - Res：`204`
  - 效果：源状态切换为 `disabled`

- GET `/tasks?sources={id}`
  - Res：`[{ id, source_id, status, progress, error? }]`

## 扫描任务（Scan/Tasks）
- POST `/scan/all`
  - Req：`{ sources?: [string] }`
  - Res：
    ```json
    {
      "group_id": "string",
      "status": "queued|running|succeeded|failed|cancelled",
      "progress": 0,
      "tasks": [
        { "id": "string", "source_id": "string", "status": "...", "progress": 0, "error": "string?" }
      ]
    }
    ```

- GET `/scan/groups/{group_id}`
  - Res：`{ tasks: [ { id, source_id, status, progress, error? } ] }`

- WS `/tasks/stream`
  - Event（单任务或分组内任务更新）：
    ```json
    { "id": "string", "source_id": "string", "status": "queued|running|succeeded|failed|cancelled", "progress": 0, "error": "string?" }
    ```

## 媒体库与搜索
- GET `/library/home`
  - Res：
    ```json
    {
      "categories": [ { "id": "string", "name": "string", "cover": "string?" } ],
      "recent": [],
      "movies": [ MediaItem ],
      "tv": [ MediaItem ],
      "scan_summary": { "running_tasks": 0, "last_global_scan": "timestamp", "added": 0, "failed": 0 }
    }
    ```
  媒体库首页后端真实api：
- GET `/api/media/cards/home`
  - Res：
    ```json
    {
  "genres": [
    {
      "id": 0,
      "name": "string"
    }
  ],
  "movie": [
    {
      "id": 0,
      "name": "string",
      "cover_url": "string",
      "rating": 0,
      "release_date": "string",
      "media_type": "string"
    }
  ],
  "tv": [
    {
      "id": 0,
      "name": "string",
      "cover_url": "string",
      "rating": 0,
      "release_date": "string",
      "media_type": "string"
    }
  ]
}
    ```

- GET `/library/categories/{categoryId}/items`
  - Query：`page`、`page_size`
  - Res：`{ total: number, items: [ MediaItem ] }`

- GET `/media/search`
  - Query：
    - `q`: string
    - `page`: number
    - `page_size`: number
    - `kind?` → 后端用 `type?`: `movie|tv`
    - `genres?`: 逗号分隔字符串
    - `year?`: string（或 `year_start`/`year_end`）
    - `region?` → 后端用 `countries?`: 逗号分隔字符串
    - `rating_min?`: number
    - `resolution?`: string
    - `hdr?`: `true|false`
  - Res 对接后端：
    - GET `/api/media/cards`
    - 返回：`{ page, page_size, total, items: [{ id, name, cover_url, rating, release_date, media_type }], type_counts }`
    - 前端映射：`items → [ MediaItem ]`（name→title、cover_url→poster、media_type→kind、release_date→year）
后端搜索api:
- GET `/api/media/cards`
  - req:
    page: int
    page_size: int
    q: Optional[str]
    type: Optional[str] = Query(None, description="movie|tv")
    genres: Optional[str]
    year: Optional[int]
    year_start: Optional[int]
    year_end: Optional[int]
    countries: Optional[str]
  - Res：
    ```json
        {
      "page": 0,
      "page_size": 0,
      "total": 0,
      "items": [
        {
          "id": 0,
          "name": "string",
          "cover_url": "string",
          "rating": 0,
          "release_date": "string",
          "media_type": "string"
        }
      ],
      "type_counts": {
        "movie": 0,
        "tv": 0
      }
    }
    ```



## 媒体详情与播放
- GET `/api/media/{id}/detail`
  - Res：
    ```json
    {
      "id": 0,
      "title": "string",
      "poster_path": "string?",
      "backdrop_path": "string?",
      "rating": 0.0,
      "release_date": "string?",
      "overview": "string?",
      "genres": [ "string" ],
      "versions": [ VersionItem ],
      "cast": [ { "name": "string", "character": "string?" } ],
      "media_type": "movie|tv",
      "seasons": [ SeasonDetail ]
    }
    ```
真实后端详情api：
- GET `/api/media/{id}/detail`
 
  - Res：
    ```json
 {
  "id": 0,
  "title": "string",
  "backdrop_path": "string",
  "poster_path": "string",
  "rating": 0,
  "release_date": "string",
  "runtime": 0,
  "runtime_text": "string",
  "genres": [
    "string"
  ],
  "source_path": "string",
  "cast": [
    {
      "name": "string",
      "character": "string",
      "tmdbid": 0,
      "image_url": "string"
    }
  ],
  "directors": [
    {}
  ],
  "writers": [
    {}
  ],
  "overview": "string",
  "versions": [
    {
      "id": 0,
      "label": "string",
      "quality": "string",
      "source": "string",
      "edition": "string",
      "assets": [
        {
          "file_id": 0,
          "path": "string",
          "type": "string",
          "playurl": "string",
          "size": 0,
          "size_text": "string",
          "language": "string"
        }
      ]
    }
  ],
  "technical": {
    "resolution": "string",
    "size": 0,
    "size_text": "string",
    "duration": 0,
    "container": "string",
    "video_codec": "string",
    "audio_codec": "string",
    "hdr": true,
    "audio_channels": 0,
    "bitrate_kbps": 0,
    "storage": {},
    "playurl": "string"
  },
  "media_type": "string",
  "season_count": 0,
  "episode_count": 0,
  "seasons": [
    {
      "id": 0,
      "season_number": 0,
      "title": "string",
      "air_date": "string",
      "cover": "string",
      "overview": "string",
      "rating": 0,
      "cast": [
        {
          "name": "string",
          "character": "string",
          "tmdbid": 0,
          "image_url": "string"
        }
      ],
      "episodes": [
        {
          "id": 0,
          "episode_number": 0,
          "title": "string",
          "release_date": "string",
          "rating": 0,
          "still_path": "string",
          "assets": [
            {
              "file_id": 0,
              "path": "string",
              "type": "string",
              "playurl": "string",
              "size": 0,
              "size_text": "string",
              "language": "string"
            }
          ],
          "technical": {}
        }
      ]
    }
  ]
}
    ```

- GET `/subtitles/{file_id}`
  - Res：`[{ lang?: "string", url: "string", type: "string" }]`

- 直链/HLS 路径
  - 前端将 `AssetItem.path` 转为绝对 URL：`path` 若非 `http(s)` 则拼接 `baseUrl + path`

## 鉴权
- POST `/api/auth/login`
  - Req：`{ email: string, password: string }`
  - Res：
    ```json
    {
      "access_token": "string",
      "refresh_token": "string",
      "token_type": "bearer",
      "expires_in": 3600
    }
    ```
  - 客户端行为：
    - 读取并保存：`access_token|token`（至少其一）、`refresh_token?`、`token_type?`、`expires_in?`
    - 后续请求头加入：`Authorization: Bearer <access_token>`

- POST `/api/auth/refresh`
  - Req：`{ refresh_token: string }`
  - Res：
    ```json
    { "refresh_token": "string" }
    ```
  - 客户端行为：更新本地 `refresh_token`（当前后端不返回新的 `access_token`，前端仅替换刷新令牌）

- GET `/api/auth/me`
  - Res：`{
  "id": 0,
  "email": "user@example.com",
  "is_active": true
}`   
  - 客户端行为：用于“我的”首页展示用户信息（头像/脱敏账号），并决定是否显示“退出登录”入口；若 `is_active=false` 或请求返回 401/403，客户端回退为未登录状态并引导重新登录

  
- POST `/api/auth/logout`
  - Req：无（需携带 `Authorization` 头，形如 `Authorization: Bearer <access_token>`）
  - Res：204（无内容）
  - 客户端行为：清空本地令牌与相关状态（`token`、`refresh_token`、`token_type`、`expires_at`），并刷新登录态 UI
  

## 模型摘要
- `MediaItem`：`{ id, kind, title, poster?, backdrop?, rating?, year? }`
- `VersionItem`：`{ id, label?, quality?, source?, edition?, assets: [ AssetItem ] }`
- `AssetItem`：`{ file_id, path, type, size?, size_text? }`
- `SeasonDetail`：`{ season_number, episodes: [ EpisodeDetail ] }`
- `EpisodeDetail`：`{ episode_number, title, assets: [ AssetItem ], technical?, still_path? }`
- `ScanTask`：`{ id, source_id, status, progress, error? }`
- `ScanGroup`：`{ group_id, status, progress, tasks: [ ScanTask ] }`

## 错误与分页约定
- 错误响应：`{ code, message, details? }`（HTTP status 对应语义）
- 分页约定：
  - Query：`page`（从 1 开始）、`page_size`（默认 20，最大 100）
  - 响应：`{ total, items: [...] }`
