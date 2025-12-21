
from typing import Dict, List
from datetime import datetime
import logging
import mimetypes
import threading
from pathlib import Path
from sqlmodel import select, col, delete
from sqlalchemy.dialects.postgresql import insert # <-- 关键导入
from models.media_models import FileAsset
from services.storage.storage_client import StorageEntry
from core.db import AsyncSessionLocal  # 确保这里导入的是你的异步工厂

logger = logging.getLogger(__name__)

class SqlFileAssetRepository:
    """异步文件资产仓库"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """线程安全的单例实现"""
        # 第一次检查：如果实例已存在，直接返回（避免每次都加锁，提高性能）
        if not cls._instance:
            # 加锁：确保同一时间只有一个线程能进入下面的逻辑
            with cls._lock:
                # 第二次检查：加锁后再确认一次实例是否存在（防止多线程“抢锁”后重复创建）
                if not cls._instance:
                    # 调用父类的 __new__ 方法，创建当前类的实例
                    cls._instance = super(SqlFileAssetRepository, cls).__new__(cls)
        # 返回唯一实例（无论是否新创建，都是同一个）
        return cls._instance
    
    async def get_all_paths_in_directory(self, user_id: int, storage_id: int, scan_path: str) -> Dict[str, int]:
        """异步获取数据库快照 {full_path: id}"""
        async with AsyncSessionLocal() as session:
            # 确保 scan_path 结尾处理一致性
            base_path = scan_path if scan_path.endswith('/') else f"{scan_path}/"
            
            stmt = select(FileAsset.full_path, FileAsset.id).where(
                (FileAsset.user_id == user_id),
                (FileAsset.storage_id == storage_id)
            )
            
            if scan_path != "/":
                # 使用 startswith 的逻辑优化查询
                stmt = stmt.where(FileAsset.full_path.like(f"{scan_path}%"))
                
            result = await session.exec(stmt)
            rows = result.all()
            return {row.full_path: row.id for row in rows}

    async def find_existing_files_bulk(self, user_id: int, storage_id: int, file_paths: List[str]) -> Dict[str, FileAsset]:
        """批量查找已存在的文件对象"""
        if not file_paths:
            return {}
        async with AsyncSessionLocal() as session:
            stmt = select(FileAsset).where(
                (FileAsset.user_id == user_id),
                (FileAsset.storage_id == storage_id),
                (col(FileAsset.full_path).in_(file_paths))
            )
            result = await session.exec(stmt)
            rows = result.all()
            return {r.full_path: r for r in rows}

    async def bulk_upsert_file_records(self, storage_id: int, entries: List[StorageEntry], user_id: int) -> Dict[str, int]:
        """
        执行 UPSERT 并返回所有处理过的 {path: id} 映射
        """
        if not entries:
            return {}

        path_id_map = {}
        async with AsyncSessionLocal() as session:
            try:
                for entry in entries:
                    # 准备基础数据
                    insert_vals = {
                        "user_id": user_id,
                        "storage_id": storage_id,
                        "full_path": entry.path,
                        "filename": entry.name,
                        "size": entry.size or 0,
                        "etag": entry.etag,
                        "updated_at": datetime.now(),
                        "created_at": datetime.now(),
                        "relative_path": str(Path(entry.path).parent),
                        "mimetype": mimetypes.guess_type(entry.path)[0]
                    }

                    # 构建语句
                    stmt = insert(FileAsset).values(**insert_vals)
                    
                    # 定义冲突时的更新行为
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['full_path', 'storage_id', 'user_id'],
                        set_={
                            "size": insert_vals["size"],
                            "etag": insert_vals["etag"],
                            "updated_at": insert_vals["updated_at"]
                        }
                    ).returning(FileAsset.id, FileAsset.full_path) # 关键：要求返回 ID 和路径

                    result = await session.exec(stmt)
                    row = result.fetchone()
                    if row:
                        path_id_map[row.full_path] = row.id
                
                await session.commit()
                return path_id_map
            except Exception as e:
                logger.error(f"Upsert failed: {e}")
                await session.rollback()
                return {}

    async def delete_files_by_ids(self, file_ids: List[int]) -> int:
        """优化后的批量删除：一条 SQL 搞定"""
        if not file_ids:
            return 0
        async with AsyncSessionLocal() as session:
            try:
                # 直接构造批量删除语句：DELETE FROM file_asset WHERE id IN (...)
                stmt = delete(FileAsset).where(col(FileAsset.id).in_(file_ids))
                result = await session.exec(stmt)
                await session.commit()
                return result.rowcount # 返回受影响的行数
            except Exception as e:
                logger.error(f"批量删除记录失败: {e}")
                await session.rollback()
                return 0

# 2. 导出单例获取函数（供外部注入使用）
file_asset_repo = SqlFileAssetRepository()

async def get_file_asset_repo() -> SqlFileAssetRepository:
    return file_asset_repo  


    # async def bulk_update_file_info(self, file_records: List[FileAsset]) -> int:
    #     """批量更新文件信息"""
    #     if not file_records:
    #         return 0
    #     async with AsyncSessionLocal() as session:
    #         try:
    #             for fr in file_records:
    #                 fr.updated_at = datetime.now()
    #                 # 将对象合并回当前的异步 session 上下文
    #                 await session.merge(fr)
    #             await session.commit()
    #             return len(file_records)
    #         except Exception as e:
    #             logger.error(f"批量更新失败: {e}")
    #             await session.rollback()
    #             return 0

    # async def bulk_create_file_records(self, storage_id: int, entries: List[StorageEntry], user_id: int) -> List[FileAsset]:
    #     """批量创建文件记录"""
    #     if not entries:
    #         return []
        
    #     created_assets: List[FileAsset] = []
    #     async with AsyncSessionLocal() as session:
    #         try:
    #             for entry in entries:
    #                 # 路径处理逻辑
    #                 p = Path(entry.path)
    #                 relative_path = str(p.parent) # 获取父级目录作为相对路径
                    
    #                 media_file = FileAsset(
    #                     user_id=user_id,
    #                     storage_id=storage_id,
    #                     full_path=entry.path,
    #                     filename=entry.name,
    #                     relative_path=relative_path,
    #                     size=entry.size or 0,
    #                     mimetype=mimetypes.guess_type(entry.path)[0],
    #                     etag=entry.etag,
    #                     created_at=datetime.now(),
    #                     updated_at=datetime.now()
    #                 )
    #                 session.add(media_file)
    #                 created_assets.append(media_file)
                
    #             await session.commit()
                
    #             # 刷新以获取数据库生成的 ID
    #             for asset in created_assets:
    #                 await session.refresh(asset)
    #             return created_assets
                
    #         except Exception as e:
    #             logger.exception(f"批量创建数据库记录失败: {e}")
    #             await session.rollback()
    #             return []
