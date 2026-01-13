# MediaCMN（FastAPI 后端）远程服务器 Docker 部署文档

本文档面向 Linux 服务器（Ubuntu/Debian/CentOS 均可），使用 Docker Compose 部署 `media-server`（FastAPI API）+ PostgreSQL + Redis（任务队列）+ Redis（刮削缓存）+ Caddy（HTTPS 反向代理）。

## 1. 部署架构

- `mediacmn_caddy`：对外暴露 80/443，自动签发/续期证书（Let’s Encrypt），反向代理到 API
- `mediacmn_api`：FastAPI（Uvicorn），启动前自动执行 `alembic upgrade head`
- `mediacmn_worker`：Dramatiq 消费者，处理 `scan/metadata/persist/delete/localize` 队列
- `mediacmn_postgres`：业务数据库
- `mediacmn_redis_queue`：Dramatiq Broker（队列/重试/死信）
- `mediacmn_redis_cache`：刮削详情缓存（LRU）

## 2. 服务器准备

### 2.1 安装 Docker 与 Compose

确保服务器已安装：
- Docker Engine
- Docker Compose v2（`docker compose` 子命令）

### 2.2 域名与端口

- 将域名（例如 `api.example.com`）A 记录指向服务器公网 IP
- 放行端口：80、443（如果你把 80 映射到自定义端口，例如 6063，则还需要放行 6063）
- 不要对公网暴露 PostgreSQL/Redis 端口（本编排默认不暴露）

## 3. 配置文件

本仓库已提供生产编排与模板：

- [docker-compose.prod.yml](file:///home/meal/mediacmn/docker-compose.prod.yml)
- [deploy/Caddyfile](file:///home/meal/mediacmn/deploy/Caddyfile)
- [deploy/.env.prod.example](file:///home/meal/mediacmn/deploy/.env.prod.example)

你需要在服务器上创建 `deploy/.env.prod`（包含真实密码与密钥），推荐做法：

```bash
cp deploy/.env.prod.example deploy/.env.prod
```

然后编辑 `deploy/.env.prod` 至少完成以下项：
- `DOMAIN`：你的域名（建议填写 `api.example.com`）
- `POSTGRES_PASSWORD`：强密码
- `DATABASE_URL`：包含正确的 Postgres 密码，并指向 `postgres` 容器
- `REDIS_PASSWORD`、`REDIS_CACHE_PASSWORD`：强密码
- `REDIS_URL`、`SCRAPER_CACHE_REDIS_URL`：包含正确的 Redis 密码，并分别指向 `redis_queue`/`redis_cache`
- `JWT_SECRET_KEY`、`MASTER_KEY`、`URL_SIGNING_SECRET`：强随机值（长度 ≥ 32）
- `CORS_ORIGINS`：生产建议填写前端域名列表（JSON 数组）

## 4. 启动部署

在服务器上进入项目目录（包含 `docker-compose.prod.yml` 的目录），执行：

```bash
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d --build
```

> **注意：** 所有的 `docker compose` 命令（包括 `ps`, `logs`, `stop` 等）都必须携带 `--env-file deploy/.env.prod` 参数，否则会因为找不到必填的环境变量（如 `POSTGRES_PASSWORD`）而报错。

### 4.1 简化命令（可选）
如果你觉得每次都要输入 `--env-file` 太麻烦，可以在项目根目录创建一个 `.env` 软链接指向生产配置：

```bash
ln -s deploy/.env.prod .env
```

创建后，你就可以直接运行简化命令，Docker 会自动加载 `.env`：
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
```

## 5. 测试与验证

部署完成后，请按照以下步骤验证系统是否正常运行。

### 5.1 检查容器状态
确认所有容器的状态为 `Up` 且健康检查为 `healthy`（**记得带上 --env-file**）：

```bash
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml ps
```

预期输出中 `STATUS` 栏应包含 `(healthy)` 字样。

### 5.2 验证 API 连通性
在服务器本地或通过公网（如果已开放端口）测试 API 健康检查接口：

```bash
# 测试存活探针
curl http://localhost:6069/api/health/live

# 测试就绪探针（包含数据库和 Redis 连接检查）
curl http://localhost:6069/api/health/ready
```

预期返回：`{"status":"ok"}` 或类似成功响应。

### 5.3 检查服务日志
如果某个服务未正常启动，查看其日志：

```bash
# 查看 API 日志
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml logs -f api

# 查看 Worker 日志（确认任务队列正常）
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml logs -f worker
```

### 5.4 验证数据库连接
进入 API 容器并尝试连接数据库：

```bash
docker exec -it mediacmn_api python -c "import os; from sqlmodel import create_engine; engine = create_engine(os.getenv('DATABASE_URL')); conn = engine.connect(); print('DB Connected!'); conn.close()"
```

### 5.5 验证 Redis 队列
进入 Worker 容器确认 Dramatiq 能够连接 Redis：

```bash
docker exec -it mediacmn_worker dramatiq-admin stats
```

## 6. 数据迁移（从本地到服务器）

### 5.1 本地备份
在本地开发目录执行以下命令，将数据导出为 SQL 文件：
```bash
docker exec -t media_postgres pg_dump -U postgres -d mediacmn > mediacmn_backup.sql
```

### 5.2 上传到服务器
使用 `scp` 或其他工具将备份文件上传：
```bash
scp mediacmn_backup.sql root@your_server_ip:/root/mediacmn/
```

### 5.3 服务器恢复数据
在服务器端，建议先清空已有数据库再导入。**注意：所有 docker compose 命令必须带上 --env-file 参数。**

```bash
# 1. 启动并确保数据库容器运行
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d postgres

# 2. 删除并重建数据库
docker exec -it mediacmn_postgres psql -U postgres -c "DROP DATABASE IF EXISTS mediacmn;"
docker exec -it mediacmn_postgres psql -U postgres -c "CREATE DATABASE mediacmn;"

# 3. 导入 SQL 数据
cat mediacmn_backup.sql | docker exec -i mediacmn_postgres psql -U postgres -d mediacmn

# 4. 启动/重启所有服务
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d
```

## 6. 自动化备份（建议）

```bash
git pull
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f --tail=200 api
```

## 7. 常见问题

### 7.1 证书签发失败

- 确认域名解析到服务器公网 IP
- 确认 80/443 端口已放行且未被其他服务占用
- 查看 Caddy 日志：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 caddy
```

### 7.2 数据库迁移失败

API 启动前会执行 `alembic upgrade head`，若失败：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 api
```

修复后重新启动：

```bash
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d --build api
```

### 7.3 API 容器启动后立即退出

常见原因与排查顺序：

1. 查看 API 日志（优先看报错堆栈）：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 api
```

2. 常见错误：
   - `alembic` 配置/迁移文件缺失：如果镜像内没有 `alembic.ini` 或 `alembic/` 目录，迁移会被跳过；若你需要强制迁移，请确保仓库包含迁移文件并重新构建镜像。
   - `DATABASE_URL` 错误：用户名/密码不一致或数据库名不对，表现为连接失败。
   - `REDIS_URL`/`SCRAPER_CACHE_REDIS_URL` 错误：密码或主机名不正确，表现为就绪探针失败或启动阶段连接异常。

3. 单独重启 API：

```bash
docker compose --env-file deploy/.env.prod -f docker-compose.prod.yml up -d --build api
```

### 7.4 Docker Hub 镜像拉取超时 (DeadlineExceeded)

如果在构建镜像时遇到 `failed to resolve source metadata for docker.io/library/python:3.12-slim` 或 `i/o timeout`，通常是因为国内服务器访问 Docker Hub 不稳定。

**解决方法 1：配置 Docker 镜像加速器（推荐）**

在服务器上编辑（或创建） `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

然后重启 Docker 服务：

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

**解决方法 2：直接在 Dockerfile 中使用镜像源**

临时修改 `media-server/Dockerfile` 第一行（本项目推荐使用 `docker.1ms.run`）：

```dockerfile
# FROM python:3.12-slim
FROM docker.1ms.run/library/python:3.12-slim
```

### 7.5 需要挂载本地媒体目录（可选）

如果后端使用“本地存储（local）”扫描宿主机目录，需要把宿主机路径挂到 `api` 与 `worker` 容器，并保证只读/读写权限符合预期。示例（自行按服务器路径调整）：

在 `docker-compose.prod.yml` 的 `api` 与 `worker` 下追加：

```yaml
    volumes:
      - /srv/media:/data/media:ro
```

然后在应用侧配置 `LocalStorageConfig.base_path=/data/media`。


由于国内未备案域名在 80/443 端口会被拦截，本方案已调整为使用 **6069** 端口：
- HTTP 入口：`http://maelsea.site:6069/`
- API 文档：`http://maelsea.site:6069/api/docs`
- 注意：此模式下不提供自动 HTTPS。

健康检查：
- API：`http://<DOMAIN>:6069/api/health/live`
- 就绪：`http://<DOMAIN>:6069/api/health/ready`
- 文档：`http://<DOMAIN>:6069/api/docs`