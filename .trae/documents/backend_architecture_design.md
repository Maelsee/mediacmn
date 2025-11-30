# MediaCMN 后端架构设计文档

## 1. 架构概述

MediaCMN是一个现代化的媒体管理系统，采用FastAPI框架构建，支持多用户、多存储类型的媒体文件管理与元数据刮削。系统采用分层架构设计，确保高内聚低耦合，支持水平扩展和微服务化部署。

### 1.1 系统架构图

```mermaid
graph TD
    A[Flutter Frontend] -->|HTTPS/JWT| B[FastAPI Gateway]
    B --> C[Authentication Layer]
    B --> D[API Routes Layer]
    B --> E[Service Layer]
    
    C --> C1[JWT Middleware]
    C --> C2[RBAC Authorization]
    C --> C3[User Isolation]
    
    D --> D1[Media Routes]
    D --> D2[Storage Routes]
    D --> D3[Scan Routes]
    D --> D4[Auth Routes]
    
    E --> E1[Media Service]
    E --> E2[Storage Service]
    E --> E3[Scan Service]
    E --> E4[Metadata Service]
    E --> E5[Queue Service]
    
    E --> F[Data Access Layer]
    F --> G[(PostgreSQL)]
    F --> H[(Redis Cache)]
    F --> I[(Redis Queue)]
    
    E2 --> J1[WebDAV Client]
    E2 --> J2[SMB Client]
    E2 --> J3[Local Storage]
    E2 --> J4[Cloud Storage]
    
    E4 --> K1[TMDB Plugin]
    E4 --> K2[Douban Plugin]
    E4 --> K3[TVmaze Plugin]
    
    style B fill:#4CAF50
    style E fill:#2196F3
    style F fill:#FF9800
```

### 1.2 技术栈

- **后端框架**: FastAPI 0.115+
- **数据库**: PostgreSQL 15+ (生产), SQLite (开发)
- **缓存**: Redis 7+
- **任务队列**: Redis-based优先级队列
- **ORM**: SQLModel 0.14+
- **认证**: PyJWT 2.8+
- **密码哈希**: bcrypt 4.0+
- **HTTP客户端**: aiohttp 3.9+
- **异步任务**: asyncio + ThreadPoolExecutor
- **限流**: aiolimiter 1.1+
- **数据验证**: Pydantic 2.5+

## 2. 数据库设计

### 2.1 核心数据模型

```mermaid
erDiagram
    User ||--o{ StorageConfig : "manages"
    User ||--o{ MediaCore : "owns"
    User ||--o{ ScanJob : "creates"
    User ||--o{ RefreshToken : "has"
    
    StorageConfig ||--o| WebdavStorageConfig : "extends"
    StorageConfig ||--o| SmbStorageConfig : "extends"
    StorageConfig ||--o| LocalStorageConfig : "extends"
    StorageConfig ||--o| CloudStorageConfig : "extends"
    StorageConfig ||--o| StorageStatus : "monitors"
    StorageConfig ||--o{ StorageScanTask : "triggers"
    StorageConfig ||--o{ FileAsset : "contains"
    
    MediaCore ||--o{ MediaVersion : "has versions"
    MediaCore ||--o{ MovieExt : "extends"
    MediaCore ||--o{ TVSeriesExt : "extends"
    MediaCore ||--o{ SeasonExt : "extends"
    MediaCore ||--o{ EpisodeExt : "extends"
    MediaCore ||--o{ ExternalID : "maps"
    MediaCore ||--o{ Artwork : "has"
    MediaCore ||--o{ Credit : "features"
    MediaCore ||--o{ MediaCoreGenre : "categorizes"
    
    MediaVersion ||--o{ FileAsset : "contains"
    EpisodeExt ||--o{ FileAsset : "links"
    
    Credit }o--|| Person : "involves"
    MediaCoreGenre }o--|| Genre : "belongs to"
    
    ScanJob ||--o{ StorageScanTask : "includes"
```

### 2.2 表结构详细设计

#### 用户相关表

**users** - 用户基础信息表
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**refresh_tokens** - JWT刷新令牌表
```sql
CREATE TABLE refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### 存储配置表

**storage_config** - 统一存储配置基表
```sql
CREATE TABLE storage_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    storage_type VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**webdav_storage_config** - WebDAV详细配置
```sql
CREATE TABLE webdav_storage_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_config_id INTEGER NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    login VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL,
    root_path VARCHAR(255) DEFAULT '/',
    timeout_seconds INTEGER DEFAULT 30,
    verify_ssl BOOLEAN DEFAULT TRUE,
    pool_connections INTEGER DEFAULT 10,
    pool_maxsize INTEGER DEFAULT 10,
    retries_total INTEGER DEFAULT 3,
    retries_backoff_factor REAL DEFAULT 0.5,
    retries_status_forcelist VARCHAR(50) DEFAULT '[429,500,502,503,504]',
    custom_headers TEXT,
    proxy_config TEXT,
    FOREIGN KEY (storage_config_id) REFERENCES storage_config(id) ON DELETE CASCADE
);
```

**smb_storage_config** - SMB/CIFS配置
```sql
CREATE TABLE smb_storage_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_config_id INTEGER NOT NULL,
    server_host VARCHAR(255) NOT NULL,
    server_port INTEGER DEFAULT 445,
    share_name VARCHAR(100) NOT NULL,
    username VARCHAR(100),
    password VARCHAR(255),
    domain VARCHAR(100),
    client_name VARCHAR(50) DEFAULT 'MEDIACMN',
    use_ntlm_v2 BOOLEAN DEFAULT TRUE,
    sign_options VARCHAR(20) DEFAULT 'auto',
    is_direct_tcp BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (storage_config_id) REFERENCES storage_config(id) ON DELETE CASCADE
);
```

**local_storage_config** - 本地存储配置
```sql
CREATE TABLE local_storage_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_config_id INTEGER NOT NULL,
    base_path VARCHAR(500) NOT NULL,
    auto_create_dirs BOOLEAN DEFAULT TRUE,
    use_symlinks BOOLEAN DEFAULT FALSE,
    follow_symlinks BOOLEAN DEFAULT FALSE,
    scan_depth_limit INTEGER DEFAULT 10,
    exclude_patterns TEXT,
    FOREIGN KEY (storage_config_id) REFERENCES storage_config(id) ON DELETE CASCADE
);
```

**cloud_storage_config** - 云盘存储配置
```sql
CREATE TABLE cloud_storage_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_config_id INTEGER NOT NULL,
    cloud_provider VARCHAR(50) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    token_expiry TIMESTAMP,
    client_id VARCHAR(255),
    client_secret VARCHAR(255),
    remote_root_path VARCHAR(255) DEFAULT '/',
    chunk_size_mb INTEGER DEFAULT 100,
    max_concurrent_uploads INTEGER DEFAULT 3,
    max_concurrent_downloads INTEGER DEFAULT 5,
    provider_specific_config TEXT,
    FOREIGN KEY (storage_config_id) REFERENCES storage_config(id) ON DELETE CASCADE
);
```

#### 媒体数据表

**media_core** - 媒体核心信息表
```sql
CREATE TABLE media_core (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    original_title VARCHAR(255),
    year INTEGER,
    plot TEXT,
    group_key VARCHAR(255),
    canonical_tmdb_id INTEGER,
    nfo_exists BOOLEAN DEFAULT FALSE,
    nfo_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**media_version** - 媒体版本表
```sql
CREATE TABLE media_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    core_id INTEGER NOT NULL,
    tags VARCHAR(100) NOT NULL,
    quality VARCHAR(50),
    source VARCHAR(50),
    edition VARCHAR(100),
    UNIQUE(user_id, core_id, tags),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (core_id) REFERENCES media_core(id) ON DELETE CASCADE
);
```

**movie_ext** - 电影扩展信息
```sql
CREATE TABLE movie_ext (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    core_id INTEGER NOT NULL,
    tagline VARCHAR(255),
    collection_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (core_id) REFERENCES media_core(id) ON DELETE CASCADE
);
```

**tv_series_ext** - 剧集系列扩展
```sql
CREATE TABLE tv_series_ext (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    core_id INTEGER NOT NULL,
    aired_from TIMESTAMP,
    aired_to TIMESTAMP,
    episode_count INTEGER,
    season_count INTEGER,
    status VARCHAR(50),
    rating REAL,
    poster_path VARCHAR(500),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (core_id) REFERENCES media_core(id) ON DELETE CASCADE
);
```

**file_asset** - 文件资源表
```sql
CREATE TABLE file_asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    full_path VARCHAR(1000) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    relative_path VARCHAR(1000) NOT NULL,
    core_id INTEGER,
    version_id INTEGER,
    episode_core_id INTEGER,
    size BIGINT NOT NULL,
    mimetype VARCHAR(100),
    video_codec VARCHAR(50),
    audio_codec VARCHAR(50),
    resolution VARCHAR(20),
    duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, full_path),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (core_id) REFERENCES media_core(id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES media_version(id) ON DELETE CASCADE,
    FOREIGN KEY (episode_core_id) REFERENCES media_core(id) ON DELETE CASCADE
);
```

#### 关联数据表

**external_ids** - 外部ID映射
```sql
CREATE TABLE external_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    core_id INTEGER NOT NULL,
    source VARCHAR(20) NOT NULL,
    key VARCHAR(100) NOT NULL,
    UNIQUE(user_id, core_id, source),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (core_id) REFERENCES media_core(id) ON DELETE CASCADE
);
```

**artwork** - 艺术作品资源
```sql
CREATE TABLE artwork (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    core_id INTEGER NOT NULL,
    type VARCHAR(20) NOT NULL,
    remote_url VARCHAR(1000),
    local_path VARCHAR(1000),
    width INTEGER,
    height INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (core_id) REFERENCES media_core(id) ON DELETE CASCADE
);
```

**genre** - 流派标签表
```sql
CREATE TABLE genre (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    UNIQUE(user_id, name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**person** - 人员基础表
```sql
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    tmdb_id INTEGER,
    UNIQUE(user_id, name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### 2.3 索引设计

```sql
-- 用户相关索引
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token);

-- 存储配置索引
CREATE INDEX idx_storage_config_user_id ON storage_config(user_id);
CREATE INDEX idx_storage_config_type ON storage_config(storage_type);
CREATE INDEX idx_storage_config_active ON storage_config(is_active);

-- 媒体数据索引
CREATE INDEX idx_media_core_user_id ON media_core(user_id);
CREATE INDEX idx_media_core_kind ON media_core(kind);
CREATE INDEX idx_media_core_title ON media_core(title);
CREATE INDEX idx_media_core_year ON media_core(year);
CREATE INDEX idx_media_core_group_key ON media_core(group_key);
CREATE INDEX idx_media_core_tmdb_id ON media_core(canonical_tmdb_id);

-- 文件资源索引
CREATE INDEX idx_file_asset_user_id ON file_asset(user_id);
CREATE INDEX idx_file_asset_core_id ON file_asset(core_id);
CREATE INDEX idx_file_asset_version_id ON file_asset(version_id);
CREATE INDEX idx_file_asset_episode_id ON file_asset(episode_core_id);
CREATE INDEX idx_file_asset_path ON file_asset(full_path);

-- 外部ID索引
CREATE INDEX idx_external_ids_user_id ON external_ids(user_id);
CREATE INDEX idx_external_ids_core_id ON external_ids(core_id);
CREATE INDEX idx_external_ids_source ON external_ids(source);
CREATE INDEX idx_external_ids_key ON external_ids(key);

-- 其他关联表索引
CREATE INDEX idx_artwork_user_id ON artwork(user_id);
CREATE INDEX idx_artwork_core_id ON artwork(core_id);
CREATE INDEX idx_artwork_type ON artwork(type);

CREATE INDEX idx_genre_user_id ON genre(user_id);
CREATE INDEX idx_genre_name ON genre(name);

CREATE INDEX idx_person_user_id ON person(user_id);
CREATE INDEX idx_person_name ON person(name);
CREATE INDEX idx_person_tmdb_id ON person(tmdb_id);
```

## 3. 功能模块设计

### 3.1 认证授权模块

```mermaid
graph TD
    A[用户请求] --> B{JWT验证}
    B -->|有效| C[解析用户信息]
    B -->|无效| D[返回401错误]
    C --> E[权限检查]
    E -->|有权限| F[访问资源]
    E -->|无权限| G[返回403错误]
    
    H[刷新令牌] --> I[验证刷新令牌]
    I -->|有效| J[生成新访问令牌]
    I -->|无效| K[返回401错误]
```

**核心功能**:
- JWT访问令牌和刷新令牌机制
- 基于角色的权限控制(RBAC)
- 用户数据隔离
- 敏感数据加密存储
- API响应脱敏

### 3.2 存储管理模块

```mermaid
graph TD
    A[存储配置管理] --> B[WebDAV配置]
    A --> C[SMB配置]
    A --> D[本地存储配置]
    A --> E[云盘配置]
    
    F[存储操作] --> G[文件列表]
    F --> H[文件下载]
    F --> I[文件上传]
    F --> J[目录管理]
    
    K[存储监控] --> L[连接状态]
    K --> M[性能指标]
    K --> N[错误统计]
```

**支持的存储类型**:
- **WebDAV**: 支持连接池、重试机制、SSL验证
- **SMB/CIFS**: 支持NTLM认证、Direct TCP
- **本地存储**: 支持符号链接、扫描深度限制
- **云盘存储**: 支持阿里云盘、百度网盘、OneDrive等

### 3.3 媒体管理模块

```mermaid
graph TD
    A[媒体核心管理] --> B[基础信息管理]
    A --> C[版本管理]
    A --> D[元数据管理]
    
    E[媒体类型] --> F[电影]
    E --> G[电视剧]
    E --> H[综艺]
    
    I[文件关联] --> J[视频文件]
    I --> K[字幕文件]
    I --> L[NFO文件]
    I --> M[图片文件]
```

**核心功能**:
- 统一的媒体核心模型，支持多种媒体类型
- 多版本管理，支持不同质量和来源
- 完整的外部ID映射，支持TMDB、IMDb、TVDB等
- 丰富的艺术作品管理（海报、剧照、横幅等）

### 3.4 扫描与刮削模块

```mermaid
graph TD
    A[扫描任务] --> B[文件发现]
    A --> C[文件解析]
    A --> D[元数据匹配]
    
    E[刮削器插件] --> F[TMDB插件]
    E --> G[豆瓣插件]
    E --> H[TVmaze插件]
    
    I[任务队列] --> J[优先级队列]
    I --> K[限流控制]
    I --> L[断路器保护]
    I --> M[重试机制]
```

**核心特性**:
- 异步扫描，支持优先级队列
- 插件化刮削架构，易于扩展
- 智能限流和断路器保护
- 批量处理和错误重试
- 实时任务状态跟踪

## 4. 核心业务流程

### 4.1 媒体扫描流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as API
    participant Q as 任务队列
    participant S as 扫描服务
    participant D as 数据库
    participant P as 刮削插件
    
    U->>A: 创建扫描任务
    A->>D: 保存任务信息
    A->>U: 返回任务ID
    
    A->>Q: 提交扫描任务
    Q->>S: 分发任务
    
    S->>D: 更新任务状态
    S->>S: 扫描文件系统
    S->>D: 保存文件信息
    
    S->>Q: 提交刮削任务
    Q->>P: 分发刮削任务
    
    P->>D: 获取文件信息
    P->>P: 调用外部API
    P->>D: 保存元数据
    
    P->>D: 更新任务状态
    P->>U: 通知完成
```

### 4.2 用户认证流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as API
    participant S as 认证服务
    participant D as 数据库
    
    U->>A: 登录请求
    A->>S: 验证凭据
    S->>D: 查询用户信息
    S->>S: 验证密码
    
    alt 验证成功
        S->>S: 生成JWT令牌
        S->>D: 保存刷新令牌
        S->>U: 返回访问令牌
    else 验证失败
        S->>U: 返回401错误
    end
    
    U->>A: 访问受保护资源
    A->>S: 验证JWT令牌
    S->>S: 解析令牌
    
    alt 令牌有效
        S->>A: 允许访问
        A->>U: 返回资源
    else 令牌过期
        S->>U: 返回401错误
        U->>A: 刷新令牌
        A->>S: 验证刷新令牌
        S->>S: 生成新访问令牌
        S->>U: 返回新令牌
    end
```

### 4.3 存储操作流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as API
    participant S as 存储服务
    participant C as 存储客户端
    participant D as 数据库
    
    U->>A: 列出目录内容
    A->>S: 获取存储配置
    S->>D: 查询配置信息
    
    S->>C: 创建客户端实例
    C->>C: 连接存储系统
    C->>C: 获取目录列表
    C->>S: 返回文件信息
    S->>A: 格式化响应
    A->>U: 返回目录内容
    
    U->>A: 下载文件
    A->>S: 获取文件信息
    S->>C: 创建下载流
    C->>C: 读取文件数据
    C->>A: 返回数据流
    A->>U: 流式传输文件
```

## 5. API接口设计

### 5.1 认证接口

| 接口 | 方法 | 描述 | 请求参数 | 响应数据 |
|------|------|------|----------|----------|
| `/api/auth/register` | POST | 用户注册 | email, password | user_info, access_token |
| `/api/auth/login` | POST | 用户登录 | email, password | access_token, refresh_token |
| `/api/auth/refresh` | POST | 刷新令牌 | refresh_token | access_token |
| `/api/auth/me` | GET | 获取当前用户信息 | Authorization头 | user_info |

### 5.2 存储配置接口

| 接口 | 方法 | 描述 | 请求参数 | 响应数据 |
|------|------|------|----------|----------|
| `/api/storage` | GET | 获取存储配置列表 | - | storage_list |
| `/api/storage` | POST | 创建存储配置 | storage_config | created_config |
| `/api/storage/{id}` | GET | 获取存储配置详情 | storage_id | config_details |
| `/api/storage/{id}` | PUT | 更新存储配置 | updated_config | updated_config |
| `/api/storage/{id}` | DELETE | 删除存储配置 | storage_id | success_status |
| `/api/storage/{id}/test` | GET | 测试存储连接 | storage_id | connection_status |

### 5.3 存储操作接口

| 接口 | 方法 | 描述 | 请求参数 | 响应数据 |
|------|------|------|----------|----------|
| `/api/storage-unified/{id}/list` | GET | 列出目录内容 | path, depth | file_list |
| `/api/storage-unified/{id}/info` | GET | 获取存储信息 | - | storage_info |
| `/api/storage-unified/{id}/file-info` | GET | 获取文件详情 | file_path | file_details |
| `/api/storage-unified/{id}/download` | GET | 下载文件 | file_path | file_stream |
| `/api/storage-unified/{id}/create-directory` | POST | 创建目录 | dir_path | success_status |
| `/api/storage-unified/{id}/delete` | DELETE | 删除文件/目录 | path | success_status |

### 5.4 媒体管理接口

| 接口 | 方法 | 描述 | 请求参数 | 响应数据 |
|------|------|------|----------|----------|
| `/api/media/list` | GET | 获取媒体列表 | page, page_size, query, type | media_list |
| `/api/media/detail` | GET | 获取媒体详情 | media_id | media_details |
| `/api/media/scan/start` | POST | 启动扫描任务 | storage_name, path | job_id |
| `/api/media/scan/status` | GET | 获取扫描状态 | job_id | job_status |
| `/api/media/scan/stop` | POST | 停止扫描任务 | job_id | success_status |

### 5.5 异步扫描接口

| 接口 | 方法 | 描述 | 请求参数 | 响应数据 |
|------|------|------|----------|----------|
| `/api/async-enhanced-scan/start` | POST | 启动异步扫描 | storage_id, scan_path, recursive | task_id |
| `/api/async-enhanced-scan/task/{id}` | GET | 获取任务状态 | task_id | task_status |
| `/api/async-enhanced-scan/tasks` | GET | 获取任务列表 | status, limit | task_list |
| `/api/async-enhanced-scan/metadata-enrich` | POST | 批量元数据丰富 | file_ids, language | enrichment_task |

### 5.6 刮削器接口

| 接口 | 方法 | 描述 | 请求参数 | 响应数据 |
|------|------|------|----------|----------|
| `/api/scraper/plugins` | GET | 获取插件列表 | - | plugin_list |
| `/api/scraper/plugins/{name}/enable` | POST | 启用插件 | plugin_name | success_status |
| `/api/scraper/plugins/{name}/disable` | POST | 禁用插件 | plugin_name | success_status |
| `/api/scraper/search` | POST | 搜索元数据 | title, year, type | search_results |
| `/api/scraper/enrich` | POST | 丰富元数据 | file_id | enrichment_result |

## 6. 技术架构特点

### 6.1 安全架构

**多层安全防护**:
- **传输层**: HTTPS加密传输
- **认证层**: JWT令牌认证
- **授权层**: RBAC权限控制
- **数据层**: 敏感数据加密存储
- **应用层**: 输入验证和SQL注入防护

**用户隔离机制**:
- 所有数据表包含user_id字段
- 数据库查询自动添加用户过滤
- API层强制用户权限验证
- 服务端不依赖客户端用户ID

### 6.2 性能优化

**数据库优化**:
- 合理的索引设计
- 连接池配置
- 查询优化和N+1问题避免
- 分页查询支持

**缓存策略**:
- Redis缓存热点数据
- 插件限流状态缓存
- 用户权限缓存
- 存储连接缓存

**异步处理**:
- 扫描任务异步执行
- 元数据获取队列化
- 批量操作优化
- 并发控制

### 6.3 可扩展性

**插件化架构**:
- 刮削器插件系统
- 存储类型可扩展
- 限流策略可配置
- 任务处理器可插拔

**微服务就绪**:
- 服务层解耦
- 数据库独立
- API版本管理
- 配置外部化

## 7. 部署架构

### 7.1 开发环境

```yaml
# docker-compose.dev.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
      - SQLITE_DATABASE_URL=sqlite:///./mediacmn.db
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
    volumes:
      - ./:/app
      - ./data:/app/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### 7.2 生产环境

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://user:pass@postgres:5432/mediacmn
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=mediacmn
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### 7.3 环境变量配置

```bash
# .env.example
APP_NAME=MediaCMN Server
ENVIRONMENT=development

# 数据库配置
DATABASE_URL=postgresql://user:pass@localhost:5432/mediacmn
SQLITE_DATABASE_URL=sqlite:///./mediacmn.db

# JWT配置
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Redis配置
REDIS_URL=redis://localhost:6379
REDIS_DB=0

# 元数据API配置
TMDB_API_KEY=your-tmdb-api-key
TMDB_LANGUAGE=zh-CN
TMDB_TIMEOUT=30

# 扫描配置
SCAN_DEFAULT_DEPTH=1
SCAN_ENABLE_RECURSIVE=true
SCAN_ENABLE_INCREMENTAL=true

# CORS配置
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
```

## 8. 监控与运维

### 8.1 日志管理

**结构化日志格式**:
```json
{
  "timestamp": "2025-11-15T10:30:00Z",
  "level": "INFO",
  "logger": "media_service",
  "message": "scan_task_completed",
  "extra": {
    "user_id": 1,
    "task_id": "task-123",
    "files_processed": 150,
    "duration_ms": 2500
  }
}
```

**日志级别配置**:
- ERROR: 系统错误和异常
- WARNING: 警告信息和限流触发
- INFO: 业务流程和关键操作
- DEBUG: 详细调试信息

### 8.2 性能监控

**关键指标**:
- API响应时间
- 数据库查询性能
- 任务队列长度
- 存储连接状态
- 刮削成功率

**监控端点**:
- `/api/health/live` - 存活检查
- `/api/health/ready` - 就绪检查
- `/api/metrics` - Prometheus指标

### 8.3 错误处理

**统一错误响应**:
```json
{
  "ok": false,
  "error": "storage_connection_failed",
  "message": "无法连接到WebDAV服务器",
  "details": {
    "storage_name": "mydav",
    "error_code": "CONNECTION_TIMEOUT"
  }
}
```

**错误分类**:
- 客户端错误 (4xx): 参数验证、权限不足
- 服务端错误 (5xx): 数据库连接、外部服务
- 业务错误: 存储连接失败、刮削超时

## 9. 测试策略

### 9.1 单元测试

**测试覆盖率**:
- 模型验证: 100%
- 服务逻辑: 95%
- API路由: 90%
- 工具函数: 100%

**测试框架**:
- pytest - 测试运行器
- pytest-asyncio - 异步测试
- pytest-cov - 覆盖率统计
- faker - 测试数据生成

### 9.2 集成测试

**测试场景**:
- 完整的用户注册登录流程
- 存储配置的CRUD操作
- 媒体扫描和刮削流程
- 文件上传下载功能
- 权限控制验证

### 9.3 性能测试

**测试指标**:
- API响应时间 < 200ms
- 并发用户支持 > 1000
- 数据库查询时间 < 50ms
- 文件传输速度优化

## 10. 未来发展

### 10.1 短期规划 (1-3个月)

- **AI集成**: 智能内容识别和分类
- **多语言支持**: 国际化和本地化
- **移动端优化**: 响应式设计和PWA
- **插件市场**: 第三方插件生态系统

### 10.2 长期愿景 (6-12个月)

- **微服务架构**: 核心功能服务拆分
- **多云部署**: 支持Kubernetes和云原生
- **边缘计算**: CDN和边缘节点支持
- **社区建设**: 开源贡献和开发者生态

---

**文档版本**: v1.0  
**最后更新**: 2025年11月15日  
**维护团队**: MediaCMN开发团队