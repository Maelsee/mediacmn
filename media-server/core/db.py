# """数据库引擎与会话依赖管理。

# 使用 SQLModel + PostgreSQL，通过 Settings 配置数据库 URL。
# 提供 FastAPI 依赖以获取会话对象。
# """
# from __future__ import annotations

# import logging
# from typing import Generator

# from sqlmodel import SQLModel, Session, create_engine, inspect, text

# from .config import get_settings, Settings
# from models.user import User  # noqa: F401
# from models.refresh_token import RefreshToken  # noqa: F401
# from models.storage_models import StorageConfig  # noqa: F401
# from models.media_models import MediaCore  # noqa: F401
# from models.media_models import ExternalID  # noqa: F401
# from models.media_models import Artwork  # noqa: F401
# from models.media_models import Genre, MediaCoreGenre  # noqa: F401
# from models.media_models import Person, Credit  # noqa: F401
# from models.media_models import MovieExt, MediaVersion  # noqa: F401
# from models.media_models import FileAsset  # noqa: F401
# from models.media_models import SeriesExt, SeasonExt, EpisodeExt  # noqa: F401
# from models.media_models import PlaybackHistory  # noqa: F401

# logger = logging.getLogger(__name__)


# settings: Settings = get_settings()

# # 根据环境选择数据库URL
# def get_database_url() -> str:
#     """始终返回 PostgreSQL 数据库URL。"""
#     env = settings.ENVIRONMENT
#     logger.info(f"数据库环境: {env}")
#     logger.info("使用 PostgreSQL 数据库")
#     return settings.DATABASE_URL

# def _engine_kwargs(url: str) -> dict:
#     """根据数据库类型返回适配的 create_engine 关键字参数。

#     - SQLite: 需要设置 check_same_thread=False 以支持多线程（FastAPI 默认多线程）。
#     - 其他数据库: 无需额外参数。
#     """
#     if url.startswith("sqlite"):
#         # 本地开发默认使用 SQLite，支持多线程访问
#         return {"connect_args": {"check_same_thread": False}}
#     if url.startswith("postgresql"):
#         # PostgreSQL：设置连接/连接池参数，避免连接阻塞导致任务卡住
#         # - connect_timeout：连接超时（秒），默认可能较长，这里收敛到 3s
#         # - pool_size / max_overflow：增大连接池容量以适应后台任务与接口并发
#         # - pool_timeout：获取连接超时，避免长时间等待
#         return {
#             "connect_args": {"connect_timeout": 3},
#             "pool_size": 10,
#             "max_overflow": 20,
#             "pool_timeout": 5,
#         }
#     return {}

# database_url = get_database_url()
# engine = create_engine(database_url, pool_pre_ping=True, **_engine_kwargs(database_url))


# def get_session() -> Generator[Session, None, None]:
#     """FastAPI 依赖：提供数据库会话。"""
#     with Session(engine) as session:
#         yield session


# def get_metadata() -> SQLModel.metadata.__class__:
#     """获取 SQLModel 元数据，用于 Alembic autogenerate。"""
#     return SQLModel.metadata


# def init_db() -> None:
#     """初始化数据库（创建所有模型对应的表）。

#     在应用启动时调用，确保在开发环境（尤其是 SQLite）不依赖 Alembic 也能正常运行。
#     生产环境使用 PostgreSQL，开发环境使用 SQLite。
#     """
#     # logger.info("开始初始化数据库...")
    
#     try:
#         # 创建所有表
#         SQLModel.metadata.create_all(engine)
#         # logger.info("数据库表创建完成")
        
#         # 获取数据库方言
#         dialect = engine.dialect.name
#         # logger.info(f"数据库方言: {dialect}")
        
#         if dialect == 'postgresql':
#             # logger.info("执行 PostgreSQL 生产环境优化...")
#             with engine.begin() as conn:
#                 # 结构迁移：将 file_asset.size 列提升为 BIGINT，避免大文件 size 溢出
#                 try:
#                     inspector = inspect(engine)
#                     cols = inspector.get_columns('file_asset')
#                     size_col = next((c for c in cols if c['name'] == 'size'), None)
                    
#                     if size_col and 'INTEGER' in str(size_col['type']).upper():
#                         conn.execute(text("ALTER TABLE file_asset ALTER COLUMN size TYPE BIGINT"))
#                         logger.info("迁移: file_asset.size 列已更新为 BIGINT")
#                 except Exception as e:
#                     logger.warning(f"迁移 file_asset.size 列到 BIGINT 失败: {e}")

#                 # PostgreSQL 性能优化：创建常用索引（如果尚未存在）
#                 indexes_to_create = [
#                     # MediaCore 表索引
#                     "CREATE INDEX IF NOT EXISTS idx_media_core_user_id ON media_core (user_id)",
#                     "CREATE INDEX IF NOT EXISTS idx_media_core_kind ON media_core (kind)",
#                     "CREATE INDEX IF NOT EXISTS idx_media_core_year ON media_core (year)",
#                     "CREATE INDEX IF NOT EXISTS idx_media_core_title ON media_core (title)",
                    
#                     # FileAsset 表索引
#                     "CREATE INDEX IF NOT EXISTS idx_file_asset_user_id ON file_asset (user_id)",
#                     "CREATE INDEX IF NOT EXISTS idx_file_asset_storage_id ON file_asset (storage_id)",
#                     "CREATE INDEX IF NOT EXISTS idx_file_asset_core_id ON file_asset (core_id)",
#                     "CREATE INDEX IF NOT EXISTS idx_file_asset_full_path ON file_asset (full_path)",
                    
#                     # ExternalID 表索引
#                     "CREATE INDEX IF NOT EXISTS idx_external_ids_core_id ON external_ids (core_id)",
#                     "CREATE INDEX IF NOT EXISTS idx_external_ids_source ON external_ids (source)",
#                 ]
                
#                 created_indexes = 0
#                 for index_sql in indexes_to_create:
#                     try:
#                         conn.execute(text(index_sql))
#                         created_indexes += 1
#                     except Exception as e:
#                         logger.warning(f"创建索引失败: {index_sql}, 错误: {e}")
                
#                 # logger.info(f"PostgreSQL 索引创建完成，共创建 {created_indexes} 个索引")
                
#                 # 更新序列起始值（避免ID冲突）
#                 sequences_to_update = [
#                     ("media_core_id_seq", "media_core"),
#                     ("file_asset_id_seq", "file_asset"),
#                     ("users_id_seq", "users"),
#                 ]
                
#                 updated_sequences = 0
#                 for seq_name, table_name in sequences_to_update:
#                     try:
#                         # 检查序列是否存在
#                         seq_exists = conn.execute(
#                             text("""
#                                 SELECT EXISTS (
#                                     SELECT 1 FROM pg_sequences 
#                                     WHERE schemaname = current_schema() 
#                                     AND sequencename = :seq_name
#                                 )
#                             """),
#                             {"seq_name": seq_name}
#                         ).scalar()
                        
#                         if seq_exists:
#                             # 检查表是否有数据
#                             max_id = conn.execute(
#                                 text(f"SELECT COALESCE(MAX(id), 1) FROM {table_name}")
#                             ).scalar()
                            
#                             if max_id > 0:
#                                 conn.execute(
#                                     text(f"SELECT setval('{seq_name}', :max_id)"),
#                                     {"max_id": max_id}
#                                 )
#                                 updated_sequences += 1
#                                 logger.debug(f"序列 {seq_name} 更新为 {max_id}")
                        
#                     except Exception as e:
#                         logger.warning(f"更新序列 {seq_name} 失败: {e}")
                
#                 # logger.info(f"PostgreSQL 序列更新完成，共更新 {updated_sequences} 个序列")  
                        
#         elif dialect == 'sqlite':
#             # logger.info("执行 SQLite 开发环境优化...")
#             with engine.begin() as conn:
#                 # SQLite 特定优化
#                 conn.execute(text("PRAGMA foreign_keys = ON"))
#                 conn.execute(text("PRAGMA journal_mode = WAL"))
#                 conn.execute(text("PRAGMA cache_size = -64000"))
#                 logger.info("SQLite 优化完成")
        
#         # 检查表结构
#         inspector = inspect(engine)
#         tables = inspector.get_table_names()
#         # logger.info(f"数据库初始化完成，共 {len(tables)} 个表")
        
#         # 记录表信息
#         for table_name in sorted(tables):
#             columns = inspector.get_columns(table_name)
#             logger.debug(f"表 {table_name}: {len(columns)} 列")

#         # 轻量结构迁移：为 person 增加 profile_url 列（若缺失）
#         try:
#             person_cols = {c['name'] for c in inspector.get_columns('person')}
#             if 'profile_url' not in person_cols:
#                 with engine.begin() as conn:
#                     try:
#                         conn.execute(text("ALTER TABLE person ADD COLUMN profile_url TEXT"))
#                         logger.info("person.profile_url 列已添加")
#                     except Exception as e:
#                         logger.warning(f"添加 person.profile_url 列失败: {e}")
#         except Exception as e:
#             logger.warning(f"检查/迁移 person.profile_url 列失败: {e}")
                
#     except Exception as e:
#         logger.error(f"数据库初始化失败: {e}")
#         logger.error("请检查数据库连接配置和模型定义")
#         raise
    
#     logger.info("数据库初始化成功完成")

"""数据库引擎与会话依赖管理。

使用 SQLModel + PostgreSQL，通过 Settings 配置数据库 URL。
提供 FastAPI 依赖以获取会话对象。
支持同步和异步操作。
"""
from __future__ import annotations

import logging
from typing import Generator, AsyncGenerator
from contextlib import asynccontextmanager

# from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession  # ✅ 导入SQLModel的AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, create_engine

from .config import get_settings, Settings
from models.user import User  # noqa: F401
from models.refresh_token import RefreshToken  # noqa: F401
from models.storage_models import StorageConfig  # noqa: F401
from models.media_models import MediaCore  # noqa: F401
from models.media_models import ExternalID  # noqa: F401
from models.media_models import Artwork  # noqa: F401
from models.media_models import Genre, MediaCoreGenre  # noqa: F401
from models.media_models import Person, Credit  # noqa: F401
from models.media_models import MovieExt, MediaVersion  # noqa: F401
from models.media_models import FileAsset  # noqa: F401
from models.media_models import SeriesExt, SeasonExt, EpisodeExt  # noqa: F401
from models.media_models import PlaybackHistory  # noqa: F401

logger = logging.getLogger(__name__)

settings: Settings = get_settings()

# 根据环境选择数据库URL
def get_database_url() -> str:
    """始终返回 PostgreSQL 数据库URL。"""
    env = settings.ENVIRONMENT
    logger.info(f"数据库环境: {env}")
    logger.info("使用 PostgreSQL 数据库")
    return settings.DATABASE_URL

def get_async_database_url() -> str:
    """返回异步数据库URL（使用 asyncpg 驱动）。"""
    url = get_database_url()
    # 将 postgresql:// 替换为 postgresql+asyncpg://
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

def _engine_kwargs(url: str, is_async: bool = False) -> dict:
    """根据数据库类型返回适配的 create_engine 关键字参数。"""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    if url.startswith("postgresql"):
        base_kwargs = {
            "connect_args": {"connect_timeout": 3},
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 5,
        }
        # 异步引擎额外配置
        if is_async:
            base_kwargs.update({
                "pool_pre_ping": True,
                "pool_recycle": 3600,  # 1小时回收连接
            })
        return base_kwargs
    return {}

# 同步引擎（用于 Alembic 和初始化）
database_url = get_database_url()
engine = create_engine(database_url, pool_pre_ping=True, **_engine_kwargs(database_url))

# 异步引擎（用于应用运行时）
async_database_url = get_async_database_url()
async_engine = create_async_engine(async_database_url, **_engine_kwargs(async_database_url, is_async=True))

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False  # 提交后保持对象状态
)

def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供同步数据库会话（用于 Alembic 等）。"""
    with Session(engine) as session:
        yield session

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供异步数据库会话。"""
    async with AsyncSessionLocal() as session:
        yield session

@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """提供异步会话的上下文管理器（用于非 FastAPI 环境）。"""
    async with AsyncSessionLocal() as session:
        yield session

def get_metadata() -> SQLModel.metadata.__class__:
    """获取 SQLModel 元数据，用于 Alembic autogenerate。"""
    return SQLModel.metadata

async def init_async_db() -> None:
    """异步初始化数据库（创建所有模型对应的表）。"""
    logger.info("开始异步初始化数据库...")
    
    try:
        # 使用异步引擎创建所有表
        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        
        # 获取数据库方言
        dialect = async_engine.dialect.name
        logger.info(f"数据库方言: {dialect}")
        
        if dialect == 'postgresql':
            logger.info("执行 PostgreSQL 生产环境优化...")
            async with async_engine.begin() as conn:
                # 结构迁移：将 file_asset.size 列提升为 BIGINT
                try:
                    # 使用 run_sync 执行同步检查
                    def check_and_migrate_size(sync_conn):
                        inspector = inspect(sync_conn)
                        cols = inspector.get_columns('file_asset')
                        size_col = next((c for c in cols if c['name'] == 'size'), None)
                        
                        if size_col and 'INTEGER' in str(size_col['type']).upper():
                            sync_conn.execute(text("ALTER TABLE file_asset ALTER COLUMN size TYPE BIGINT"))
                            logger.info("迁移: file_asset.size 列已更新为 BIGINT")
                    
                    await conn.run_sync(check_and_migrate_size)
                except Exception as e:
                    logger.warning(f"迁移 file_asset.size 列到 BIGINT 失败: {e}")

                # PostgreSQL 性能优化：创建常用索引
                indexes_to_create = [
                    "CREATE INDEX IF NOT EXISTS idx_media_core_user_id ON media_core (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_media_core_kind ON media_core (kind)",
                    "CREATE INDEX IF NOT EXISTS idx_media_core_year ON media_core (year)",
                    "CREATE INDEX IF NOT EXISTS idx_media_core_title ON media_core (title)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_user_id ON file_asset (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_storage_id ON file_asset (storage_id)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_core_id ON file_asset (core_id)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_full_path ON file_asset (full_path)",
                    "CREATE INDEX IF NOT EXISTS idx_external_ids_core_id ON external_ids (core_id)",
                    "CREATE INDEX IF NOT EXISTS idx_external_ids_source ON external_ids (source)",
                ]
                
                created_indexes = 0
                for index_sql in indexes_to_create:
                    try:
                        await conn.execute(text(index_sql))
                        created_indexes += 1
                    except Exception as e:
                        logger.warning(f"创建索引失败: {index_sql}, 错误: {e}")
                
                logger.info(f"PostgreSQL 索引创建完成，共创建 {created_indexes} 个索引")
                
                # 更新序列起始值
                sequences_to_update = [
                    ("media_core_id_seq", "media_core"),
                    ("file_asset_id_seq", "file_asset"),
                    ("users_id_seq", "users"),
                ]
                
                updated_sequences = 0
                for seq_name, table_name in sequences_to_update:
                    try:
                        # 检查序列是否存在
                        seq_exists = await conn.execute(
                            text("""
                                SELECT EXISTS (
                                    SELECT 1 FROM pg_sequences 
                                    WHERE schemaname = current_schema() 
                                    AND sequencename = :seq_name
                                )
                            """),
                            {"seq_name": seq_name}
                        )
                        
                        if seq_exists.scalar():
                            # 检查表是否有数据
                            max_id_result = await conn.execute(
                                text(f"SELECT COALESCE(MAX(id), 1) FROM {table_name}")
                            )
                            max_id = max_id_result.scalar()
                            
                            if max_id > 0:
                                await conn.execute(
                                    text(f"SELECT setval('{seq_name}', :max_id)"),
                                    {"max_id": max_id}
                                )
                                updated_sequences += 1
                                logger.debug(f"序列 {seq_name} 更新为 {max_id}")
                        
                    except Exception as e:
                        logger.warning(f"更新序列 {seq_name} 失败: {e}")
                
                logger.info(f"PostgreSQL 序列更新完成，共更新 {updated_sequences} 个序列")
                        
        elif dialect == 'sqlite':
            logger.info("执行 SQLite 开发环境优化...")
            async with async_engine.begin() as conn:
                await conn.execute(text("PRAGMA foreign_keys = ON"))
                await conn.execute(text("PRAGMA journal_mode = WAL"))
                await conn.execute(text("PRAGMA cache_size = -64000"))
                logger.info("SQLite 优化完成")
        
        # 检查表结构
        async with async_engine.begin() as conn:
            def check_tables(sync_conn):
                inspector = inspect(sync_conn)
                tables = inspector.get_table_names()
                logger.info(f"数据库初始化完成，共 {len(tables)} 个表")
                
                # 记录表信息
                for table_name in sorted(tables):
                    columns = inspector.get_columns(table_name)
                    logger.debug(f"表 {table_name}: {len(columns)} 列")
                
                return inspector
            
            inspector = await conn.run_sync(check_tables)

            # 轻量结构迁移：为 person 增加 profile_url 列
            try:
                person_cols = {c['name'] for c in inspector.get_columns('person')}
                if 'profile_url' not in person_cols:
                    await conn.execute(text("ALTER TABLE person ADD COLUMN profile_url TEXT"))
                    logger.info("person.profile_url 列已添加")
            except Exception as e:
                logger.warning(f"添加 person.profile_url 列失败: {e}")
                
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        logger.error("请检查数据库连接配置和模型定义")
        raise
    
    logger.info("异步数据库初始化成功完成")

def init_db() -> None:
    """同步初始化数据库（用于 Alembic 和迁移）。"""
    logger.info("开始同步初始化数据库...")
    
    try:
        # 创建所有表
        SQLModel.metadata.create_all(engine)
        
        # 获取数据库方言
        dialect = engine.dialect.name
        logger.info(f"数据库方言: {dialect}")
        
        if dialect == 'postgresql':
            logger.info("执行 PostgreSQL 生产环境优化...")
            with engine.begin() as conn:
                # 结构迁移：将 file_asset.size 列提升为 BIGINT
                try:
                    inspector = inspect(engine)
                    cols = inspector.get_columns('file_asset')
                    size_col = next((c for c in cols if c['name'] == 'size'), None)
                    
                    if size_col and 'INTEGER' in str(size_col['type']).upper():
                        conn.execute(text("ALTER TABLE file_asset ALTER COLUMN size TYPE BIGINT"))
                        logger.info("迁移: file_asset.size 列已更新为 BIGINT")
                except Exception as e:
                    logger.warning(f"迁移 file_asset.size 列到 BIGINT 失败: {e}")

                # PostgreSQL 性能优化：创建常用索引
                indexes_to_create = [
                    "CREATE INDEX IF NOT EXISTS idx_media_core_user_id ON media_core (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_media_core_kind ON media_core (kind)",
                    "CREATE INDEX IF NOT EXISTS idx_media_core_year ON media_core (year)",
                    "CREATE INDEX IF NOT EXISTS idx_media_core_title ON media_core (title)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_user_id ON file_asset (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_storage_id ON file_asset (storage_id)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_core_id ON file_asset (core_id)",
                    "CREATE INDEX IF NOT EXISTS idx_file_asset_full_path ON file_asset (full_path)",
                    "CREATE INDEX IF NOT EXISTS idx_external_ids_core_id ON external_ids (core_id)",
                    "CREATE INDEX IF NOT EXISTS idx_external_ids_source ON external_ids (source)",
                ]
                
                created_indexes = 0
                for index_sql in indexes_to_create:
                    try:
                        conn.execute(text(index_sql))
                        created_indexes += 1
                    except Exception as e:
                        logger.warning(f"创建索引失败: {index_sql}, 错误: {e}")
                
                logger.info(f"PostgreSQL 索引创建完成，共创建 {created_indexes} 个索引")
                
                # 更新序列起始值
                sequences_to_update = [
                    ("media_core_id_seq", "media_core"),
                    ("file_asset_id_seq", "file_asset"),
                    ("users_id_seq", "users"),
                ]
                
                updated_sequences = 0
                for seq_name, table_name in sequences_to_update:
                    try:
                        # 检查序列是否存在
                        seq_exists = conn.execute(
                            text("""
                                SELECT EXISTS (
                                    SELECT 1 FROM pg_sequences 
                                    WHERE schemaname = current_schema() 
                                    AND sequencename = :seq_name
                                )
                            """),
                            {"seq_name": seq_name}
                        ).scalar()
                        
                        if seq_exists:
                            # 检查表是否有数据
                            max_id = conn.execute(
                                text(f"SELECT COALESCE(MAX(id), 1) FROM {table_name}")
                            ).scalar()
                            
                            if max_id > 0:
                                conn.execute(
                                    text(f"SELECT setval('{seq_name}', :max_id)"),
                                    {"max_id": max_id}
                                )
                                updated_sequences += 1
                                logger.debug(f"序列 {seq_name} 更新为 {max_id}")
                        
                    except Exception as e:
                        logger.warning(f"更新序列 {seq_name} 失败: {e}")
                
                logger.info(f"PostgreSQL 序列更新完成，共更新 {updated_sequences} 个序列")
                        
        elif dialect == 'sqlite':
            logger.info("执行 SQLite 开发环境优化...")
            with engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys = ON"))
                conn.execute(text("PRAGMA journal_mode = WAL"))
                conn.execute(text("PRAGMA cache_size = -64000"))
                logger.info("SQLite 优化完成")
        
        # 检查表结构
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"数据库初始化完成，共 {len(tables)} 个表")
        
        # 记录表信息
        for table_name in sorted(tables):
            columns = inspector.get_columns(table_name)
            logger.debug(f"表 {table_name}: {len(columns)} 列")

        # 轻量结构迁移：为 person 增加 profile_url 列
        try:
            person_cols = {c['name'] for c in inspector.get_columns('person')}
            if 'profile_url' not in person_cols:
                with engine.begin() as conn:
                    try:
                        conn.execute(text("ALTER TABLE person ADD COLUMN profile_url TEXT"))
                        logger.info("person.profile_url 列已添加")
                    except Exception as e:
                        logger.warning(f"添加 person.profile_url 列失败: {e}")
        except Exception as e:
            logger.warning(f"检查/迁移 person.profile_url 列失败: {e}")
                
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        logger.error("请检查数据库连接配置和模型定义")
        raise
    
    logger.info("同步数据库初始化成功完成")

async def close_async_db() -> None:
    """关闭异步数据库连接。"""
    await async_engine.dispose()
    logger.info("异步数据库连接已关闭")

def close_sync_db() -> None:
    """关闭同步数据库连接。"""
    engine.dispose()
    logger.info("同步数据库连接已关闭")
