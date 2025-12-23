
from typing import Dict, List,Set
from datetime import datetime
import logging
import mimetypes
import threading
from pathlib import Path
from sqlmodel import select, col, delete,func
from sqlalchemy.dialects.postgresql import insert # <-- 关键导入
from models.media_models import FileAsset
from models.media_models import MediaCore
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

    # async def delete_files_by_ids(self, file_asset_ids: List[int], user_id: int) -> Dict[str, int]:
    #     """
    #     高性能批量智能清理：
    #     1. 批量删除文件记录
    #     2. 批量识别并清理无文件的“孤儿”MediaCore
    #     """
    #     if not file_asset_ids:
    #         return {"deleted_assets": 0, "cleaned_cores": 0}

    #     async with AsyncSessionLocal() as session:
    #         try:
    #             # --- 第一步：获取这些文件关联的 core_id ---
    #             # 预先查出来，因为物理删除 FileAsset 后就拿不到关联关系了
    #             affected_cores_stmt = select(FileAsset.core_id).where(
    #                 FileAsset.id.in_(file_asset_ids),
    #                 FileAsset.user_id == user_id
    #             )
    #             res = await session.exec(affected_cores_stmt)
    #             # 转换为 Set 去重且过滤掉 None
    #             target_core_ids = {c for c in res.scalars().all() if c is not None}

    #             # --- 第二步：物理删除 FileAsset ---
    #             await session.exec(
    #                 delete(FileAsset).where(
    #                     FileAsset.id.in_(file_asset_ids),
    #                     FileAsset.user_id == user_id
    #                 )
    #             )
                
    #             # 必须 flush，确保接下来的计数不包含已删除的文件
    #             await session.flush()

    #             cleaned_cores_count = 0
    #             if target_core_ids:
    #                 # --- 第三步：【性能关键】批量查询剩余文件数 ---
    #                 # 使用 GROUP BY 一次性拿回所有受影响 Core 的当前视频数
    #                 remaining_counts_stmt = (
    #                     select(FileAsset.core_id, func.count(FileAsset.id))
    #                     .where(FileAsset.core_id.in_(list(target_core_ids)))
    #                     .group_by(FileAsset.core_id)
    #                 )
    #                 counts_res = await session.exec(remaining_counts_stmt)
    #                 # 记录还有文件的 core_id
    #                 cores_with_files = {row[0] for row in counts_res.all()}
                    
    #                 # 计算出哪些是“孤儿”：在 target_core_ids 中但不在 cores_with_files 中
    #                 orphan_core_ids = target_core_ids - cores_with_files

    #                 if orphan_core_ids:
    #                     # --- 第四步：【性能关键】批量删除孤儿 Core ---
    #                     # 数据库 CASCADE 会处理后续所有层级（Season -> Episode -> Ext）
    #                     delete_cores_stmt = delete(MediaCore).where(
    #                         MediaCore.id.in_(list(orphan_core_ids)),
    #                         MediaCore.user_id == user_id
    #                     )
    #                     await session.exec(delete_cores_stmt)
    #                     cleaned_cores_count = len(orphan_core_ids)

    #             await session.commit()
    #             return {
    #                 "deleted_assets": len(file_asset_ids),
    #                 "cleaned_cores": cleaned_cores_count
    #             }

    #         except Exception as e:
    #             logger.error(f"智能清理批量操作失败: {e}", exc_info=True)
    #             await session.rollback()
    #             return {"deleted_assets": 0, "cleaned_cores": 0}

    async def delete_files_by_ids(self, file_asset_ids: List[int], user_id: int) -> Dict[str, int]:
        if not file_asset_ids:
            return {"deleted_assets": 0, "cleaned_cores": 0}

        async with AsyncSessionLocal() as session:
            try:
                # 1. 记录受影响的直接 core_id (通常是 Episode 或 Movie)
                stmt = select(FileAsset.core_id).where(FileAsset.id.in_(file_asset_ids), FileAsset.user_id == user_id)
                res = await session.exec(stmt)
                affected_leaf_ids = {c for c in res.scalars().all() if c is not None}

                # 2. 删除文件资源
                await session.exec(delete(FileAsset).where(FileAsset.id.in_(file_asset_ids), FileAsset.user_id == user_id))
                await session.flush()

                cleaned_count = 0
                # 记录所有被删除的 core_id，用于后续向上追溯其父级
                deleted_in_this_run = set()

                if affected_leaf_ids:
                    # 3. 找出并删除没有文件的叶子节点 (Episode/Movie)
                    counts_stmt = select(FileAsset.core_id).where(FileAsset.core_id.in_(list(affected_leaf_ids))).group_by(FileAsset.core_id)
                    cores_with_files = {row for row in (await session.exec(counts_stmt)).all()}
                    orphan_leaf_ids = affected_leaf_ids - cores_with_files

                    if orphan_leaf_ids:
                        # 在删除前获取这些孤儿的 parent_id，供后续递归检查
                        parent_stmt = select(MediaCore.parent_id).where(MediaCore.id.in_(list(orphan_leaf_ids)))
                        parents_to_check = {p for p in (await session.exec(parent_stmt)).scalars().all() if p is not None}
                        
                        # 执行删除
                        await session.exec(delete(MediaCore).where(MediaCore.id.in_(list(orphan_leaf_ids))))
                        cleaned_count += len(orphan_leaf_ids)
                        
                        # 4. 递归向上清理父级 (Season -> Series)
                        while parents_to_check:
                            next_parents = set()
                            for p_id in parents_to_check:
                                # 检查该父级是否还有任何子级 (children 关系)
                                child_count_stmt = select(func.count(MediaCore.id)).where(MediaCore.parent_id == p_id)
                                child_count = (await session.exec(child_count_stmt)).first() or 0
                                
                                if child_count == 0:
                                    # 获取爷爷辈 ID
                                    grandparent_stmt = select(MediaCore.parent_id).where(MediaCore.id == p_id)
                                    gp_id = (await session.exec(grandparent_stmt)).first()
                                    if gp_id: next_parents.add(gp_id)

                                    # 删除空壳父级
                                    await session.exec(delete(MediaCore).where(MediaCore.id == p_id))
                                    cleaned_count += 1
                            
                            parents_to_check = next_parents
                            await session.flush() # 每一层刷新一次，确保计数准确

                await session.commit()
                return {"deleted_assets": len(file_asset_ids), "cleaned_cores": cleaned_count}
            except Exception as e:
                logger.error(f"递归智能清理失败: {e}", exc_info=True)
                await session.rollback()
                raise
                


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
