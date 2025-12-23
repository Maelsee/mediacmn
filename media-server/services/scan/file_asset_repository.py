
from typing import Dict, List,Set
from datetime import datetime
import logging
import mimetypes
import threading
from pathlib import Path
from sqlmodel import select, col, delete,func
from sqlalchemy.dialects.postgresql import insert # <-- 关键导入
from models.media_models import FileAsset
from models.media_models import MediaCore,PlaybackHistory,MovieExt,SeriesExt,SeasonExt,EpisodeExt,MediaVersion,Artwork,ExternalID,MediaCoreGenre,Credit
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

    async def delete_files_by_ids(self, file_asset_ids: List[int], user_id: int) -> Dict[str, int]:
        """
        删除文件资产并清理关联数据
        1. 删除 PlaybackHistory (按文件)
        2. 删除 FileAsset
        3. 检查受影响的 MediaCore (Movie/Episode)
        4. 如果 MediaCore 不再关联任何文件，则删除该 MediaCore 及其关联数据 (Ext, Artwork, etc.)
        5. 向上递归检查父级 (Season -> Series)，如果变为空壳则一并删除
        """
        if not file_asset_ids:
            return {"deleted_assets": 0, "cleaned_cores": 0}

        async with AsyncSessionLocal() as session:
            try:
                # 1. 获取受影响的 core_id (在删除文件前获取)
                stmt = select(FileAsset.core_id).where(FileAsset.id.in_(file_asset_ids), FileAsset.user_id == user_id)
                res = await session.exec(stmt)
                affected_leaf_ids = {c for c in res.all() if c is not None}

                # 2. 删除关联的 PlaybackHistory (通过 file_asset_id)
                await session.exec(delete(PlaybackHistory).where(PlaybackHistory.file_asset_id.in_(file_asset_ids), PlaybackHistory.user_id == user_id))
                
                # 3. 删除文件资源
                await session.exec(delete(FileAsset).where(FileAsset.id.in_(file_asset_ids), FileAsset.user_id == user_id))
                await session.flush()

                cleaned_count = 0

                if affected_leaf_ids:
                    # 4. 找出并删除没有文件的叶子节点 (Episode/Movie)
                    # 检查这些 core_id 是否还有剩余文件
                    counts_stmt = select(FileAsset.core_id).where(FileAsset.core_id.in_(list(affected_leaf_ids))).group_by(FileAsset.core_id)
                    cores_with_files = {row for row in (await session.exec(counts_stmt)).all()}
                    
                    # 孤儿节点：在受影响列表中，但不在有文件列表中
                    orphan_leaf_ids = affected_leaf_ids - cores_with_files

                    if orphan_leaf_ids:
                        # 在删除前获取这些孤儿的 parent_id，供后续递归检查
                        parent_stmt = select(MediaCore.parent_id).where(MediaCore.id.in_(list(orphan_leaf_ids)))
                        parents_to_check = {p for p in (await session.exec(parent_stmt)).all() if p is not None}
                        
                        # 执行删除叶子节点及其关联数据
                        for core_id in orphan_leaf_ids:
                            await self._delete_core_and_related_data(session, core_id, user_id)
                        
                        cleaned_count += len(orphan_leaf_ids)
                        
                        # 5. 递归向上清理父级 (Season -> Series)
                        while parents_to_check:
                            next_parents = set()
                            for p_id in parents_to_check:
                                # 检查该父级是否还有任何子级 (children 关系)
                                child_count_stmt = select(func.count(MediaCore.id)).where(MediaCore.parent_id == p_id)
                                child_count = (await session.exec(child_count_stmt)).first() or 0
                                
                                if child_count == 0:
                                    # 获取爷爷辈 ID (准备下一轮检查)
                                    grandparent_stmt = select(MediaCore.parent_id).where(MediaCore.id == p_id)
                                    gp_id = (await session.exec(grandparent_stmt)).first()
                                    if gp_id: 
                                        next_parents.add(gp_id)

                                    # 删除空壳父级及其关联数据
                                    await self._delete_core_and_related_data(session, p_id, user_id)
                                    cleaned_count += 1
                            
                            parents_to_check = next_parents
                            await session.flush()

                await session.commit()
                return {"deleted_assets": len(file_asset_ids), "cleaned_cores": cleaned_count}
            except Exception as e:
                logger.error(f"递归智能清理失败: {e}", exc_info=True)
                await session.rollback()
                raise

    async def _delete_core_and_related_data(self, session, core_id: int, user_id: int):
        """
        删除 MediaCore 及其所有关联表数据 (模拟 Cascade Delete)
        """
        # 删除关联的 PlaybackHistory (通过 core_id)
        await session.exec(delete(PlaybackHistory).where(PlaybackHistory.core_id == core_id))
        
        # 删除可能直接关联的文件资源 (防止因残留文件导致删除失败)
        await session.exec(delete(FileAsset).where(FileAsset.core_id == core_id))
        
        # 删除扩展表 (MovieExt, SeriesExt, SeasonExt, EpisodeExt)
        await session.exec(delete(MovieExt).where(MovieExt.core_id == core_id))
        await session.exec(delete(SeriesExt).where(SeriesExt.core_id == core_id))
        await session.exec(delete(SeasonExt).where(SeasonExt.core_id == core_id))
        await session.exec(delete(EpisodeExt).where(EpisodeExt.core_id == core_id))
        
        # 删除其他关联表
        await session.exec(delete(MediaVersion).where(MediaVersion.core_id == core_id))
        await session.exec(delete(Artwork).where(Artwork.core_id == core_id))
        await session.exec(delete(ExternalID).where(ExternalID.core_id == core_id))
        await session.exec(delete(MediaCoreGenre).where(MediaCoreGenre.core_id == core_id))
        await session.exec(delete(Credit).where(Credit.core_id == core_id))
        
        # 最后删除 MediaCore
        await session.exec(delete(MediaCore).where(MediaCore.id == core_id))


# 2. 导出单例获取函数（供外部注入使用）
file_asset_repo = SqlFileAssetRepository()

async def get_file_asset_repo() -> SqlFileAssetRepository:
    return file_asset_repo  

