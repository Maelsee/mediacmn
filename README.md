# MediaCMN

## 项目概览（中文）

MediaCMN 是一个自托管的媒体中心管理系统，覆盖从“媒体源接入 → 扫描入库 → 元数据刮削 → 多端浏览与播放 → 播放记录/续播”的完整链路。

项目采用前后端分离：

- `media-server`：提供 REST API、鉴权、存储配置、扫描/刮削任务调度与数据持久化。
- `media-client`：Flutter 跨平台客户端，负责登录、媒体浏览、播放器、续播等交互体验。

适用场景：你有一套（或多套）媒体存储（WebDAV/本地/SMB 等），希望将媒体统一扫描入库后，在手机/桌面/Web 上统一浏览与播放，并保留播放进度与最近观看。

### 核心能力

- 多端客户端：Flutter 同时覆盖移动端/桌面端/Web（按实际构建目标选择）。
- 标准化后端 API：基于 FastAPI，内置 OpenAPI/Swagger 文档。
- 任务化处理：扫描、刮削、入库等重任务通过队列/Worker 异步执行，避免阻塞 API。
- 可部署：本地开发用 compose 启动基础设施；生产使用 compose + 反向代理容器化部署。

## Overview (English)

MediaCMN is a self-hosted media center management system that covers the full pipeline: “storage onboarding → library scanning → metadata enrichment → multi-platform browsing & playback → watch history and resume”.

The project is frontend-backend separated:

- `media-server`: REST API, auth, storage configuration, scan/enrich task scheduling, and persistence.
- `media-client`: Flutter cross-platform client for login, browsing, playback, and resume experience.

Target use case: you have one or multiple media storages (WebDAV/local/SMB, etc.), and you want to scan and organize them into a unified library, then browse/play on mobile/desktop/web with watch progress and recent history.

### Key Features

- Cross-platform client: Flutter for mobile/desktop/web (depending on your build target).
- API-first backend: FastAPI with OpenAPI/Swagger built-in.
- Background jobs: scanning/enrichment/persistence run asynchronously via workers.
- Deployable: docker compose for local infra and production deployment.

## 目录结构 / Repository Layout

- `media-server/`：后端（FastAPI + PostgreSQL + Redis + Dramatiq） / Backend (FastAPI + PostgreSQL + Redis + Dramatiq)
- `media-client/`：前端（Flutter） / Frontend (Flutter)
- `docker-compose.yml`：本地开发用基础设施（Postgres/Redis） / Local dev infrastructure
- `docker-compose.prod.yml`：生产部署编排（API/Worker/Postgres/Redis/Caddy） / Production compose
- `deploy/`：生产环境配置模板（`deploy/.env.prod.example`、`deploy/Caddyfile`） / Production config templates

## 架构说明 / Architecture

中文：

- API：`media-server/main.py` 提供 `/api/*` 路由与文档入口（`/api/docs`、`/api/redoc`、`/api/openapi.json`）。
- Worker：`dramatiq services.task.consumers` 消费队列任务（扫描、刮削、持久化等）。
- 数据库：PostgreSQL 保存媒体库结构、资源映射、播放记录等。
- Redis：作为队列 Broker 与缓存（按环境变量区分队列 Redis 与刮削缓存 Redis）。
- 反向代理：生产环境通过 Caddy 对外暴露 API 端口并转发到 `api:8000`。

English:

- API: `media-server/main.py` exposes `/api/*` routes and docs (`/api/docs`, `/api/redoc`, `/api/openapi.json`).
- Workers: `dramatiq services.task.consumers` consumes background jobs (scan/enrich/persist, etc.).
- Database: PostgreSQL stores library data, file mappings, and playback history.
- Redis: broker and cache (separated via env vars for queue vs scraper cache).
- Reverse proxy: in production, Caddy exposes the public port and forwards to `api:8000`.

## 快速开始（本地开发） / Quick Start (Local Development)

### 1) 启动基础设施（PostgreSQL/Redis） / Start infrastructure

在项目根目录 / In project root:

```bash
docker compose -f docker-compose.yml up -d
```

默认端口 / Default ports:

- PostgreSQL：`localhost:5432`
- Redis queue：`localhost:10001`（需要密码 / requires password）
- Redis cache：`localhost:10002`（需要密码 / requires password）

### 2) 启动后端（media-server） / Run backend

```bash
cd media-server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API base：`http://localhost:8000`

Docs:

- Swagger UI：`http://localhost:8000/api/docs`
- Redoc：`http://localhost:8000/api/redoc`
- OpenAPI JSON：`http://localhost:8000/api/openapi.json`

### 3) 配置后端环境变量（开发） / Backend env (dev)

中文：后端使用 `media-server/.env` 管理环境变量（文件通常不入库）。以 `media-server/.env.example` 为模板复制。

English: the backend reads environment variables from `media-server/.env` (usually not committed). Copy from `media-server/.env.example`.

```bash
cd media-server
cp .env.example .env
```

根据本仓库 `docker-compose.yml` 的默认配置，常见关键项示例（按需调整）：

```bash
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/mediacmn

REDIS_URL=redis://:redis123@localhost:10001
SCRAPER_CACHE_REDIS_URL=redis://:redis123@localhost:10002

JWT_SECRET_KEY=please_change_me
```

### 4) 启动 Worker（可选，但扫描/刮削需要） / Run workers (optional)

```bash
cd media-server
source venv/bin/activate
dramatiq services.task.consumers --processes 2 --threads 1
```

### 5) 启动前端（media-client） / Run frontend

```bash
cd media-client
flutter pub get
flutter run -d web-server --web-port 5200 --web-hostname 0.0.0.0 --disable-dds
```

Web dev URL：`http://localhost:5200`

## 生产部署（Docker Compose） / Production Deployment

中文：生产部署使用根目录 `docker-compose.prod.yml`，并通过 `deploy/.env.prod` 提供环境变量。

English: production uses `docker-compose.prod.yml`, with env vars provided by `deploy/.env.prod`.

### 1) 准备生产配置 / Prepare env

```bash
cp deploy/.env.prod.example deploy/.env.prod
```



### 2) 启动 / Start

```bash
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d --build
```


## 测试与质量检查 / Testing & Quality

前端 / Frontend (in `media-client/`):

```bash
flutter analyze
flutter test
```

后端 / Backend (in `media-server/`, with venv activated):

```bash
cd media-server
source venv/bin/activate
pytest
```

## 常见工作流 / Typical Flow

中文：

1. 登录/注册获取 Token
2. 通过 API 创建存储配置（WebDAV/SMB/Local 等）
3. 触发扫描/刮削任务（Worker 异步执行）
4. 客户端浏览媒体库并播放，后端记录播放进度

English:

1. Login/register to obtain tokens
2. Create storage configuration via API (WebDAV/SMB/Local, etc.)
3. Trigger scan/enrichment jobs (executed asynchronously by workers)
4. Browse and play in the client, with server-side playback progress tracking

## 前端 APP 截图

图 1：媒体库页面（最近观看 + 按类型分区展示）

![媒体库页面](docs/screenshots/app_library.jpg)

图 2：详情页面（海报背景 + 剧集信息 + 剧情简介 + 演职员）

![详情页面](docs/screenshots/app_detail.jpg)

图 3：播放器页面（横屏播放，支持进度拖动、手势操作、字幕/音轨/选集）

![播放器页面](docs/screenshots/app_player.jpg)

图 4：播放器设置页面（连续播放/单集循环/不循环，画面比例与画面大小调节）

![播放器设置页面](docs/screenshots/app_player_settings.jpg)
