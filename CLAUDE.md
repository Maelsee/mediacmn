# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

MediaCMN 是自托管媒体中心系统，覆盖"存储接入 → 扫描入库 → 元数据刮削 → 多端浏览与播放 → 播放记录/续播"完整链路。前后端分离架构。

- `media-server/`：FastAPI + PostgreSQL + Redis + Dramatiq 后端
- `media-client/`：Flutter 跨平台客户端（移动端/桌面端/Web）
- `docker-compose.yml`：本地开发基础设施（Postgres 5432, Redis queue 10001, Redis cache 10002, danmu-api 9321）
- `docker-compose.prod.yml`：生产部署（API/Worker/Postgres/Redis/Caddy）
- `deploy/`：生产配置模板（`.env.prod.example`, `Caddyfile`）

## 常用命令

### 后端（media-server）

```bash
cd media-server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 启动 API 服务
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 启动 Worker（扫描/刮削/持久化等后台任务）
dramatiq services.task.consumers --processes 2 --threads 1

# 数据库迁移
alembic upgrade head
alembic revision --autogenerate -m "描述"

# 测试
pytest                              # 全部测试
pytest tests/test_service_name.py   # 单个文件
pytest --cov=services tests/        # 覆盖率
```

API 文档：`http://localhost:8000/api/docs`（Swagger UI）

### 前端（media-client）

```bash
cd media-client
flutter pub get

# WSL/远程环境推荐启动方式
flutter run -d web-server --web-port 5200 --web-hostname 0.0.0.0 --disable-dds

# 其他平台
flutter run -d chrome / -d windows / -d android / -d ios

# 代码检查与测试
flutter analyze
flutter test
```

### 本地基础设施

```bash
docker compose -f docker-compose.yml up -d    # 启动
docker compose -f docker-compose.yml down      # 停止
```

## 架构

### 后端分层架构

- `api/` — FastAPI 路由（`routes_*.py`），所有路由注册在 `main.py` 的 `/api/` 下
- `core/` — 基础设施：配置（pydantic-settings）、数据库引擎（asyncpg + psycopg 双模式）、JWT 安全中间件、加密、日志（loguru）
- `models/` — SQLModel 表定义（`*_models.py`），核心在 `media_models.py`
- `schemas/` — Pydantic 请求/响应模型（`*_serialization.py`）
- `services/` — 按领域组织的业务逻辑：
  - `auth/` — 用户认证与刷新令牌
  - `media/` — 媒体服务、元数据丰富、持久化（同步+异步）、sidecar 处理
  - `scan/` — 统一扫描引擎、文件资产仓库
  - `scraper/` — 插件化刮削系统（TMDB、豆瓣），带超时保护
  - `storage/` — 存储抽象（WebDAV/SMB/Local 客户端）
  - `task/` — Dramatiq broker、消费者（6 种队列）、生产者、Redis 状态存储
  - `danmu/` — 弹幕聚合集成
- `tests/` — pytest 测试
- `alembic/` — 数据库迁移

### 任务队列设计

6 个命名队列：`scan` → `metadata` → `persist_batch` → `localize`（链式自动触发），以及 `persist`、`delete`。

扫描进度通过 Redis Hash + Pub/Sub 推送，WebSocket 实时通知客户端。

### 前端架构（feature-based）

- `core/` — API 客户端（JWT 自动附加）、配置、播放历史（本地 + 远程同步）
- `media_library/` — 首页分区、搜索、详情、媒体卡片、手动匹配
- `source_library/` — 存储源管理（WebDAV/SMB/Local 的增删改查与浏览）
- `media_player/` — media_kit 播放器，平台自适应 UI（移动端/桌面端/Web 控制、字幕/音轨/选集面板）
- `profile/` — 登录、注册、用户设置
- 路由：GoRouter 声明式路由，3 个 tab 分支（media/sources/profile）
- 状态管理：flutter_riverpod

### 数据库设计

- `media_core` — 基础实体（电影/剧集/单集）
- `media_version` — 同一标题的多质量版本
- `file_assets` — 物理文件映射，存储抽象
- `artwork` — 海报/缩略图，支持本地化
- `credits` — 演职员信息
- 层级结构：Series → Seasons → Episodes（外键关联）

### 数据流

1. 用户登录获取 JWT → 2. 创建存储配置 → 3. 触发扫描（Dramatiq 异步）→ 4. Worker 发现文件 → 5. 自动触发元数据刮削（TMDB）→ 6. 批量持久化 → 7. 客户端浏览播放，后端记录进度

## 环境配置

后端使用 `media-server/.env`（pydantic-settings），从 `.env.example` 复制。关键变量：

- `DATABASE_URL` — PostgreSQL 连接串
- `REDIS_URL` — 队列 Redis
- `SCRAPER_CACHE_REDIS_URL` — 刮削缓存 Redis
- `JWT_SECRET_KEY` — JWT 签名密钥
- `TMDB_API_KEY` — TMDB API 密钥
- `CORS_ORIGINS` — 允许的跨域来源
- `DANMU_API_BASE_URL` — 弹幕服务地址

## 关键设计模式

- **全异步**：所有后端操作使用 async/await（包括数据库会话）
- **用户隔离**：所有查询按 `user_id` 限定范围
- **插件化刮削**：scraper 插件带超时保护和启动钩子
- **批量处理**：元数据持久化每批 100 条
- **线程局部 GuessIt**：避免并发解析文件名时的竞态
- **中文媒体路径预处理**：媒体解析器针对中文命名习惯做了路径预处理

## 编码规范

- 文档和代码注释使用中文
- 后端命名：路由 `routes_*.py`，模型 `*_models.py`，Schema `*_serialization.py`
- 遵循模块化设计，避免大文件
- 完成功能后更新 `memory-bank/progress.md`
