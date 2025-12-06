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

    app = FastAPI(title=settings.APP_NAME, version="0.1.0")

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
    # from api.routes_rbac import router as rbac_router  # 多租户架构：移除RBAC路由
    # from api.routes_webdav import router as webdav_router
    from api.routes_media import router as media_router
    from api.routes_storage_config import router as storage_config_router
    from api.routes_storage_unified import router as storage_unified_router
    from api.routes_scan_new import router as scan_new_router  # 新的统一扫描路由
    from api.routes_tasks import router as tasks_router
    from api.routes_scraper import router as scraper_router
    from api.routes_playback import router as playback_router
    from api.routes_collections import router as collections_router
    from api.routes_playback import router as playback_router
    # 移除旧架构路由
    # from api.routes_scan_unified import router as scan_unified_router  # 旧统一扫描路由
    # from api.routes_enhanced_scan import router as enhanced_scan_router  # 旧增强扫描路由



    api_router = APIRouter()
    api_router.include_router(health_router, prefix="/health", tags=["health"])
    api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
    # api_router.include_router(rbac_router, prefix="/rbac", tags=["rbac"])  # 多租户架构：移除RBAC路由
    # api_router.include_router(webdav_router, prefix="/webdav", tags=["webdav"])
    api_router.include_router(media_router, prefix="/media", tags=["media"])
    api_router.include_router(collections_router, prefix="/collections", tags=["collections"])
    api_router.include_router(playback_router, prefix="/playback", tags=["playback"])
    api_router.include_router(storage_config_router, prefix="/storage", tags=["storage"])
    api_router.include_router(storage_unified_router, prefix="/storage-unified", tags=["storage-unified"])
    api_router.include_router(scan_new_router, prefix="/scan", tags=["scan"])  # 新的统一扫描路由
    api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])  # 任务生产者API
    api_router.include_router(scraper_router, prefix="/scraper", tags=["scraper"])
    # 移除旧架构路由
    # api_router.include_router(scan_unified_router, prefix="/scan-unified", tags=["scan-unified"])  # 旧统一扫描路由
    # api_router.include_router(enhanced_scan_router, prefix="/enhanced-scan", tags=["enhanced-scan"])  # 旧增强扫描路由
    
    app.include_router(api_router, prefix="/api")

    # 初始化数据库（在开发环境自动创建表，生产环境建议使用 Alembic 迁移）
    try:
        init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error(f"database_init_failed: {e}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await scraper_manager.startup()
            logger.info("scraper_manager_started")
        except Exception as e:
            logger.error(f"scraper_manager_start_failed: {e}")
        try:
            yield
        finally:
            try:
                await scraper_manager.shutdown()
                logger.info("scraper_manager_stopped")
            except Exception as e:
                logger.error(f"scraper_manager_stop_failed: {e}")

    app.router.lifespan_context = lifespan

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
