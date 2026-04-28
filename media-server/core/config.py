"""应用配置与环境变量管理。

使用 pydantic-settings 管理环境变量，提供统一的 Settings 类。
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import List, Optional, Union

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 计算项目根目录并支持通过 ENV_FILE 指定 .env 绝对路径
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = os.environ.get("ENV_FILE", str(BASE_DIR / ".env"))

class Settings(BaseSettings):
    """应用的环境配置。"""

    # 绝对路径加载 .env，支持通过 ENV_FILE 环境变量覆盖
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", case_sensitive=False)

    APP_NAME: str = "MediaCMN Server"
    ENVIRONMENT: str = Field(default="development", description="运行环境：development/production/test")

    # CORS
    # 为兼容 .env 中以逗号分隔的字符串或 JSON 列表，这里使用 Union[str, List[str], None]
    # 通过字段校验器在加载时统一转换为 List[str]
    CORS_ORIGINS: Union[str, List[str], None] = Field(default=None, description="允许的跨域来源")

    # 数据库
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/mediacmn",
        description="PostgreSQL 连接字符串",
    )
    SQLITE_DATABASE_URL: str = Field(
        default="sqlite:///./mediacmn.db",
        description="SQLite 连接字符串（开发环境使用）",
    )

    # JWT 设置
    JWT_SECRET_KEY: str = Field(default="changeme", description="JWT 密钥")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT 算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=3600, description="访问令牌过期时间（分钟）")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="刷新令牌过期时间（天）")
    REFRESH_TOKEN_ROTATION: bool = Field(default=True, description="是否启用刷新令牌轮换")
    MASTER_KEY: str = Field(default="master_key", description="主密钥")

    PLAYURL_MODE: str = Field(default="direct_signed", description="播放URL模式：proxy_token|direct_signed")
    URL_SIGNING_SECRET: Optional[str] = Field(default=None, description="直连签名密钥")
    URL_SIGNING_TTL_SECONDS: int = Field(default=300, description="直连签名有效期（秒）")
    URL_SIGNING_ALG: str = Field(default="HS256", description="签名算法")

    # Redis 配置
    REDIS_URL: str = Field(default="redis://:redis123@localhost:10001", description="Redis 连接字符串")
    REDIS_DB: int = Field(default=0, description="Redis 数据库编号")

    # 刮削详情缓存 Redis 配置（建议与任务队列 Redis 分离）
    SCRAPER_CACHE_REDIS_URL: str = Field(default="redis://:redis123@localhost:10002", description="刮削缓存 Redis 连接字符串")
    SCRAPER_CACHE_REDIS_DB: int = Field(default=0, description="刮削缓存 Redis 数据库编号")

    # 元数据服务 API Key（全局 .env 管理）
    TMDB_API_KEY: Optional[str] = Field(default=None, description="TMDB API Key（全局）")
    TMDB_V4_TOKEN: Optional[str] = Field(default=None, description="TMDB v4 Access Token（Bearer）")
    TMDB_LANGUAGE: str = Field(default="zh-CN", description="TMDB首选语言")
    TMDB_FALLBACK_LANGUAGE: str = Field(default="en-US", description="TMDB备选语言")
    TMDB_TIMEOUT: int = Field(default=30, description="TMDB请求超时时间（秒）")
    TMDB_PROXY: Optional[str] = Field(default=None, description="TMDB代理服务器")
    TMDB_API_BASE_URL: str = Field(default="https://api.themoviedb.org/3", description="TMDB API 基准地址")
    TMDB_IMAGE_BASE_URL: str = Field(default="https://image.tmdb.org/t/p", description="TMDB 图片基准地址")
    TMDB_FORCE_IPV4: bool = Field(default=False, description="TMDB 请求是否强制使用 IPv4")
    TVMAZE_API_KEY: Optional[str] = Field(default=None, description="TVMaze API Key（如需要）")
    # TMDB 网络代理（可选），用于受限网络环境
    # TMDB_HTTP_PROXY: Optional[str] = Field(default=None, description="TMDB HTTP 代理，例如 http://127.0.0.1:7890")
    # TMDB_HTTPS_PROXY: Optional[str] = Field(default=None, description="TMDB HTTPS 代理，例如 http://127.0.0.1:7890")

    # 扫描默认策略（根据确认：Depth 默认 1，启用递归与增量）
    SCAN_DEFAULT_DEPTH: str = Field(default="1", description="默认 PROPFIND Depth")
    # SCAN_ENABLE_RECURSIVE: bool = Field(default=True, description="是否递归扫描目录")
    # SCAN_ENABLE_INCREMENTAL: bool = Field(default=True, description="是否启用增量扫描")
    # SEARCH_SIMPLE_ENABLED: bool = Field(default=True, description="是否启用简单文本搜索")
    
    # 刮削语言回退策略
    # SCRAPER_FALLBACK_MOVIE: bool = Field(default=True, description="电影是否启用语言回退")
    # SCRAPER_FALLBACK_SERIES: bool = Field(default=False, description="剧集是否启用语言回退")
    ENABLE_SCRAPERS: List[str] = Field(default=["tmdb"], description="启用的刮削器插件")
    SCRAPER_OP_TIMEOUT_SECONDS: float = Field(default=10.0, description="刮削器通用操作超时（秒）")
    SCRAPER_PLUGIN_TEST_TIMEOUT_SECONDS: float = Field(default=15.0, description="刮削器插件连接测试超时（秒）")
    SCRAPER_PLUGIN_STARTUP_TIMEOUT_SECONDS: float = Field(default=20.0, description="刮削器插件启动钩子超时（秒）")
    # 侧车本地化（NFO/海报）开关与限制
    SIDE_CAR_LOCALIZATION_ENABLED: bool = Field(default=False, description="是否启用侧车异步本地化")
    SIDE_CAR_LOCALIZATION_ARTWORK_LIMIT: int = Field(default=2, description="侧车阶段写入的艺术作品最大数量")
    TASK_EXECUTOR_COUNT: int = Field(default=1, description="统一任务执行器（侧车文件上传）并发数")

    # 刮削详情缓存（电影/系列/季）
    SCRAPER_DETAIL_CACHE_USE_REDIS: bool = Field(default=True, description="是否使用 Redis 缓存刮削详情")
    SCRAPER_DETAIL_CACHE_TTL_SECONDS: int = Field(default=86400, description="刮削详情缓存 TTL（秒）")
    SCRAPER_DETAIL_CACHE_LOCAL_MAXSIZE: int = Field(default=2048, description="进程内刮削详情缓存最大条目数")
    SCRAPER_DETAIL_CACHE_LOCK_TTL_SECONDS: int = Field(default=30, description="刮削详情分布式锁 TTL（秒）")
    SCRAPER_DETAIL_CACHE_LOCK_WAIT_MS: int = Field(default=1500, description="等待其他进程填充缓存最大时长（毫秒）")
    SCRAPER_DETAIL_CACHE_LOCK_POLL_MS: int = Field(default=50, description="等待缓存轮询间隔（毫秒）")

    # 持久化批量聚合配置
    PERSIST_BATCH_MAX_SIZE: int = Field(default=100, description="持久化批量最大聚合任务数")
    PERSIST_BATCH_MAX_WAIT_MS: int = Field(default=800, description="持久化批量聚合最大等待时间（毫秒）")
    PERSIST_BUCKET_ENABLED: bool = Field(default=True, description="是否启用按类型/源/用户分桶批量提交")


    # DanmuApi 配置
    DANMU_API_BASE_URL: str = Field(
        default="http://127.0.0.1:9321",
        description="DanmuApi 服务地址"
    )
    DANMU_API_TOKEN: str = Field(
        default="112",
        description="DanmuApi 访问令牌"
    )
    DANMU_API_TIMEOUT: int = Field(
        default=30,
        description="DanmuApi 请求超时时间(秒)"
    )

    # 弹幕匹配配置
    DANMU_CONFIDENCE_THRESHOLD: float = Field(
        default=0.7,
        description="自动匹配置信度阈值"
    )
    DANMU_CACHE_TTL: int = Field(
        default=604800,  # 7天
        description="弹幕缓存时间(秒)"
    )
    DANMU_SEARCH_CACHE_TTL: int = Field(
        default=3600,  # 1小时
        description="搜索结果缓存时间(秒)"
    )

    # Redis 缓存配置（如果需要单独的缓存 Redis）
    DANMU_REDIS_URL: str = Field(
        default="redis://:redis123@localhost:10002/1",
        description="弹幕缓存 Redis 地址"
    )
    DANMU_REDIS_ENABLED: bool = Field(
        default=True,
        description="是否启用弹幕缓存"
    )


    # 允许 CORS_ORIGINS 以逗号分隔或 JSON 列表形式配置
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):  # type: ignore[override]
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("[") and s.endswith("]"):
                import json
                try:
                    data = json.loads(s)
                    # 只接受字符串列表
                    return [str(item).strip() for item in data if str(item).strip()]
                except Exception:
                    return [item.strip() for item in s.strip("[]").split(",") if item.strip()]
            return [item.strip() for item in s.split(",") if item.strip()]
        # 已是列表，确保元素为字符串
        try:
            return [str(item).strip() for item in (v or []) if str(item).strip()]
        except Exception:
            return []



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回单例化的 Settings。"""
    return Settings()
    
