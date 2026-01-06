"""FastAPI 应用入口。

此模块初始化应用、加载配置、注册中间件（含 CORS）、
结构化日志和统一异常处理，并挂载 API 路由。
"""
from __future__ import annotations

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.routing import APIRouter
from starlette.middleware.cors import CORSMiddleware
from core.security import JWTAuthMiddleware

from core.config import Settings, get_settings
from core.logging import init_logging, logger
from core.errors import register_exception_handlers
from core.db import init_db
from services.scraper import scraper_manager


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    settings: Settings = get_settings()

    # 初始化结构化日志
    init_logging(settings)
    logger.info("starting_application")
    
    # ---------------------------------------------------------
    # 1. 定义 Lifespan (放在 FastAPI 实例化之前)
    # ---------------------------------------------------------
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- 【启动阶段】 ---
        try:
            # 建立连接池、加载配置、初始化单例
            await scraper_manager.startup()
            logger.info("✅ Scraper Manager 已经在系统启动阶段就绪")
        except Exception as e:
            logger.error(f"❌ Scraper Manager 启动失败: {e}", exc_info=True)

        yield  # --- 【应用运行中】 ---
        # --- 【关闭阶段】 ---
        try:
            await scraper_manager.shutdown()
            logger.info("🛑 Scraper Manager 关闭成功")
        except Exception as e:
            logger.error(f"❌ Scraper Manager 关闭失败: {e}", exc_info=True)

    # ---------------------------------------------------------
    # 2. 实例化 FastAPI 并传入 lifespan 参数
    # ---------------------------------------------------------
    app = FastAPI(
        title=settings.APP_NAME, 
        version="0.1.0",
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # 配置 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 JWT 认证中间件（非强制）
    app.add_middleware(JWTAuthMiddleware)

    # 注册统一异常处理
    register_exception_handlers(app)

    # 挂载 API 路由
    from api.routes_health import router as health_router  # 局部导入避免循环依赖
    from api.routes_auth import router as auth_router
    from api.routes_media import router as media_router
    from api.routes_storage_config import router as storage_config_router
    from api.routes_storage_server import router as storage_server_router
    from api.routes_scan import router as scan_router  # 新的统一扫描路由
    from api.routes_tasks import router as tasks_router
    # from api.routes_scraper import router as scraper_router
    from api.routes_playback import router as playback_router
    # from api.routes_collections import router as collections_router


    api_router = APIRouter()
    api_router.include_router(health_router, prefix="/health", tags=["health"])
    api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
    api_router.include_router(media_router, prefix="/media", tags=["media"])
    # api_router.include_router(collections_router, prefix="/collections", tags=["collections"])
    api_router.include_router(playback_router, prefix="/playback", tags=["playback"])
    api_router.include_router(storage_config_router, prefix="/storage-config", tags=["storage-config"])
    api_router.include_router(storage_server_router, prefix="/storage-server", tags=["storage-server"])
    api_router.include_router(scan_router, prefix="/scan", tags=["scan"])  # 新的统一扫描路由
    api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])  # 任务生产者API
    # api_router.include_router(scraper_router, prefix="/scraper", tags=["scraper"])
    app.include_router(api_router, prefix="/api")

    # 初始化数据库（在开发环境自动创建表，生产环境建议使用 Alembic 迁移）
    try:
        init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error(f"database_init_failed: {e}")

    @app.get("/", tags=["root"])
    def root() -> dict[str, str]:
        """根路径，用于快速连通性检查。"""
        return {"message": "MediaCMN server is running"}
    
    # 添加根路径重定向到API文档
    @app.get("/docs", include_in_schema=False)
    def docs_redirect():
        """重定向到API文档"""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/api/docs")

    return app


app = create_app()
