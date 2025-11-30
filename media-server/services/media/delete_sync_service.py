"""
删除同步服务

"""
import logging
from datetime import datetime
from typing import List, Dict, Set

from sqlmodel import Session, select

from models.media_models import FileAsset, MediaCore, MovieExt, TVSeriesExt, SeasonExt, EpisodeExt, Artwork, ExternalID, MediaCoreGenre, Credit, MediaVersion, PlaybackHistory
from core.db import get_session

logger = logging.getLogger(__name__)


class DeleteSyncService:
    def compute_missing(self, storage_id: int, scan_path: str, encountered_media_paths: List[str]) -> Dict:
        """
        计算扫描到的媒体路径与数据库记录的差异，找出缺失文件
        
        参数:
            storage_id: 存储配置ID
            scan_path: 扫描根路径（信息性字段）
            encountered_media_paths: 本次扫描到的绝对路径集合
        返回:
            {"missing": List[FileAsset], "scan_count": int}
        """
        scan_set: Set[str] = set(encountered_media_paths)
        missing: List[FileAsset] = []
        with next(get_session()) as session:
            q = session.exec(select(FileAsset).where(FileAsset.storage_id == storage_id))
            for fa in q:
                # 按 storage 过滤，不再严格前缀；统一使用绝对路径集合比对
                if fa.full_path not in scan_set:
                    missing.append(fa)
        return {"missing": missing, "scan_count": len(encountered_media_paths)}

    def hard_delete_files(self, files: List[FileAsset], batch_size: int = 100) -> int:
        """
        批量硬删除文件：解除外键并删除记录
        
        参数:
            files: 待删除的文件列表（FileAsset）
            batch_size: 每批次提交数量
        返回:
            实际删除数量
        """
        count = 0
        with next(get_session()) as session:
            for i in range(0, len(files), batch_size):
                batch = files[i:i + batch_size]
                ids = [fa.id for fa in batch if getattr(fa, "id", None)]
                if not ids:
                    continue
                try:
                    with session.no_autoflush:
                        session.exec(
                            PlaybackHistory.__table__.delete().where(PlaybackHistory.file_asset_id.in_(ids))
                        )
                        session.exec(
                            MediaVersion.__table__.update().where(MediaVersion.primary_file_asset_id.in_(ids)).values(primary_file_asset_id=None)
                        )
                        session.exec(
                            FileAsset.__table__.delete().where(FileAsset.id.in_(ids))
                        )
                    session.commit()
                    count += len(ids)
                except Exception as e:
                    logger.warning(f"批量硬删除失败: {e}")
                    try:
                        session.rollback()
                    except Exception:
                        pass
        return count

    def cascade_cleanup_core(self, core_id: int) -> int:
        """
        清理指定核心及其扩展/附属数据（当无活动文件引用时）
        
        参数:
            core_id: MediaCore 主键ID
        返回:
            实际删除的核心数量（0或1）
        """
        removed = 0
        with next(get_session()) as session:
            # 如果仍有文件引用，跳过
            files_left = session.exec(select(FileAsset).where(FileAsset.core_id == core_id, FileAsset.exists == True)).all()
            if files_left:
                return 0
            # 将所有已软删除文件的 core_id 解除引用，以避免外键阻塞
            soft_deleted_files = session.exec(select(FileAsset).where(FileAsset.core_id == core_id, FileAsset.exists == False)).all()
            for f in soft_deleted_files:
                try:
                    f.core_id = None
                    f.version_id = None
                    session.add(f)
                except Exception:
                    pass
            session.flush()
            # 解除对该核心所有 MediaVersion 的引用，避免外键冲突
            version_ids = session.exec(select(MediaVersion.id).where(MediaVersion.core_id == core_id)).all() or []
            if version_ids:
                to_update = session.exec(select(FileAsset).where(FileAsset.version_id.in_(version_ids))).all()
                for fa in to_update:
                    try:
                        fa.version_id = None
                        session.add(fa)
                    except Exception:
                        pass
                session.flush()
            # 删除附属与版本（注意先解除 FileAsset.version_id）
            for model in (Artwork, ExternalID, MediaCoreGenre, Credit):
                session.exec(model.__table__.delete().where(getattr(model, "core_id") == core_id))
            try:
                session.exec(PlaybackHistory.__table__.update().where(PlaybackHistory.version_id.in_(
                    session.exec(select(MediaVersion.id).where(MediaVersion.core_id == core_id)).all()
                )).values(version_id=None))
                session.exec(PlaybackHistory.__table__.update().where(PlaybackHistory.core_id == core_id).values(core_id=None))
                session.exec(PlaybackHistory.__table__.update().where(PlaybackHistory.series_core_id == core_id).values(series_core_id=None))
                session.exec(PlaybackHistory.__table__.update().where(PlaybackHistory.season_core_id == core_id).values(season_core_id=None))
                session.exec(PlaybackHistory.__table__.update().where(PlaybackHistory.episode_core_id == core_id).values(episode_core_id=None))
            except Exception:
                pass
            session.flush()
            session.exec(MediaVersion.__table__.delete().where(MediaVersion.core_id == core_id))
            session.flush()
            # 删除扩展
            core = session.get(MediaCore, core_id)
            if not core:
                return 0
            kind = core.kind
            if kind == "movie":
                session.exec(MovieExt.__table__.delete().where(MovieExt.core_id == core_id))
                session.delete(core)
                removed += 1
            elif kind == "tv_episode":
                session.exec(EpisodeExt.__table__.delete().where(EpisodeExt.core_id == core_id))
                session.delete(core)
                removed += 1
                # 级联季与系列在外部调用中判断
            elif kind == "tv_season":
                session.exec(SeasonExt.__table__.delete().where(SeasonExt.core_id == core_id))
                session.delete(core)
                removed += 1
            elif kind == "tv_series":
                session.exec(TVSeriesExt.__table__.delete().where(TVSeriesExt.core_id == core_id))
                session.delete(core)
                removed += 1
            session.commit()
            return removed

    def detect_moves_by_etag(self, storage_id: int, missing_files: List[FileAsset], encountered_media_paths: List[str]) -> int:
        """
        通过 etag 检测缺失文件是否被移动到新路径，并修正记录
        
        参数:
            storage_id: 存储配置ID
            missing_files: 数据库标记缺失的文件列表
            encountered_media_paths: 本次扫描到的绝对路径集合
        返回:
            修正为移动状态的文件数量
        """
        moved = 0
        encountered_set = set(encountered_media_paths)
        if not missing_files:
            return 0
        with next(get_session()) as session:
            # 构建 etag -> path 映射（新扫描集）
            etag_to_path: Dict[str, str] = {}
            # 查询新路径对应的 FileAsset（同 storage_id 且 exists=True）
            q = session.exec(select(FileAsset).where(FileAsset.storage_id == storage_id, FileAsset.exists == True))
            for fa in q:
                if fa.etag and fa.full_path in encountered_set:
                    etag_to_path[fa.etag] = fa.full_path
            # 遍历缺失文件，按 etag 判断是否移动
            for old in missing_files:
                if not old.etag:
                    continue
                new_path = etag_to_path.get(old.etag)
                if new_path and new_path != old.full_path:
                    db_old = session.get(FileAsset, old.id)
                    if not db_old:
                        continue
                    db_old.full_path = new_path
                    # relative_path 依据新路径重算（简化：保持不变或外层更新）
                    db_old.status = "moved"
                    db_old.exists = True
                    db_old.deleted_at = None
                    session.add(db_old)
                    moved += 1
            session.commit()
        return moved

    def preview_cascade(self, core_id: int) -> Dict:
        """预览对指定核心的级联清理影响，不落库"""
        with next(get_session()) as session:
            core = session.get(MediaCore, core_id)
            if not core:
                return {"core_id": core_id, "exists": False}
            kind = core.kind
            refs = {
                "files": session.exec(select(FileAsset.id).where(FileAsset.core_id == core_id, FileAsset.exists == True)).all(),
                "artworks": session.exec(select(Artwork.id).where(Artwork.core_id == core_id)).all(),
                "external_ids": session.exec(select(ExternalID.id).where(ExternalID.core_id == core_id)).all(),
                "genres": session.exec(select(MediaCoreGenre.id).where(MediaCoreGenre.core_id == core_id)).all(),
                "credits": session.exec(select(Credit.id).where(Credit.core_id == core_id)).all(),
                "versions": session.exec(select(MediaVersion.id).where(MediaVersion.core_id == core_id)).all(),
            }
            ext = {}
            if kind == "movie":
                ext["movie_ext"] = session.exec(select(MovieExt.id).where(MovieExt.core_id == core_id)).all()
            elif kind == "tv_series":
                ext["series_ext"] = session.exec(select(TVSeriesExt.id).where(TVSeriesExt.core_id == core_id)).all()
                # 系列下的季与集
                seasons = session.exec(select(SeasonExt.core_id).where(SeasonExt.series_core_id == core_id)).all()
                episodes = session.exec(select(EpisodeExt.core_id).where(EpisodeExt.series_core_id == core_id)).all()
                ext["season_core_ids"] = seasons
                ext["episode_core_ids"] = episodes
            elif kind == "tv_season":
                ext["season_ext"] = session.exec(select(SeasonExt.id).where(SeasonExt.core_id == core_id)).all()
                episodes = session.exec(select(EpisodeExt.core_id).where(EpisodeExt.season_core_id == core_id)).all()
                ext["episode_core_ids"] = episodes
            elif kind == "tv_episode":
                ext["episode_ext"] = session.exec(select(EpisodeExt.id).where(EpisodeExt.core_id == core_id)).all()
            return {"core_id": core_id, "kind": kind, "refs": refs, "ext": ext}

    def cascade_recursive_cleanup(self, series_core_id: int) -> Dict:
        """递归清理一个系列：清理空集→空季→空系列"""
        removed = {"episodes": 0, "seasons": 0, "series": 0}
        with next(get_session()) as session:
            # 清理该系列下所有无活动文件的集
            episode_cores = session.exec(select(EpisodeExt.core_id).where(EpisodeExt.series_core_id == series_core_id)).all()
            for e_core in episode_cores:
                if not session.exec(select(FileAsset.id).where(FileAsset.core_id == e_core, FileAsset.exists == True)).first():
                    removed["episodes"] += self.cascade_cleanup_core(e_core)
            session.flush()
            # 清理空季
            season_cores = session.exec(select(SeasonExt.core_id).where(SeasonExt.series_core_id == series_core_id)).all()
            for s_core in season_cores:
                # 如果该季没有活动文件且没有任何集
                has_files = session.exec(select(FileAsset.id).where(FileAsset.core_id == s_core, FileAsset.exists == True)).first()
                has_episodes = session.exec(select(EpisodeExt.core_id).where(EpisodeExt.season_core_id == s_core)).first()
                if not has_files and not has_episodes:
                    removed["seasons"] += self.cascade_cleanup_core(s_core)
            session.flush()
            # 如果系列本身没有活动文件、没有季、没有集，清理系列
            has_files = session.exec(select(FileAsset.id).where(FileAsset.core_id == series_core_id, FileAsset.exists == True)).first()
            has_seasons = session.exec(select(SeasonExt.core_id).where(SeasonExt.series_core_id == series_core_id)).first()
            has_episodes = session.exec(select(EpisodeExt.core_id).where(EpisodeExt.series_core_id == series_core_id)).first()
            if not has_files and not has_seasons and not has_episodes:
                removed["series"] += self.cascade_cleanup_core(series_core_id)
            session.commit()
        return removed
