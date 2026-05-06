"""元数据持久化编排服务

MetadataPersistenceService 为对外统一入口，协调各 repo 完成元数据持久化。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

from sqlmodel import Session, select

from models.media_models import MediaCore, FileAsset, MovieExt, SeriesExt
from services.scraper import (
    ScraperMovieDetail,
    ScraperSeriesDetail,
    ScraperSeasonDetail,
    ScraperEpisodeDetail,
    ScraperSearchResult,
)

from .base import _DictWrapper
from . import core_repo
from . import version_repo

logger = logging.getLogger(__name__)


class MetadataPersistenceService:
    """媒体元数据持久化服务"""

    def __init__(self):
        self._metadata_handlers = {
            "movie": core_repo.apply_movie_detail,
            "episode": core_repo.apply_episode_detail,
        }

    def _get_handler(self, metadata_type: str):
        """安全地获取处理函数，如果类型不支持则返回 None"""
        return self._metadata_handlers.get(metadata_type)

    def _get_attr(self, obj, key: str, default=None):
        """统一的属性访问方法，同时支持 dict 和 dataclass 对象"""
        if isinstance(obj, dict):
            return obj.get(key, default)
        else:
            return getattr(obj, key, default)

    def apply_metadata(
        self, session: Session, media_file: FileAsset, metadata, metadata_type: str, path_info: Dict
    ) -> bool:
        """
        一次性幂等地将刮削结果写入领域模型，并更新相关扩展信息。

        事务说明:
            - 本方法内部仅执行 flush，不提交事务；由调用方统一 commit。
        """
        model_map = {
            "movie": ScraperMovieDetail,
            "series": ScraperSeriesDetail,
            "episode": ScraperEpisodeDetail,
            "search_result": ScraperSearchResult
        }
        model_cls = model_map.get(metadata_type)
        if isinstance(metadata, dict):
            if model_cls:
                try:
                    metadata = model_cls.model_validate(metadata)
                except Exception as ve:
                    logger.error(f"元数据校验失败: {ve}")
            else:
                metadata = _DictWrapper(metadata)
                logger.info(f"类型 {metadata_type} 没有关联的模型类，将以 dict 形式继续")

        handler = self._get_handler(metadata_type)
        if not handler:
            logger.warning(f"不支持的元数据类型: {metadata_type}")
            return False

        core = None
        try:
            old_version_id = getattr(media_file, "version_id", None)
            old_season_version_id = getattr(media_file, "season_version_id", None)

            if metadata_type == "series":
                core = handler(session, media_file.user_id, metadata)
            else:
                core = handler(session, media_file, metadata)

            if not core:
                logger.error(f"处理元数据失败，处理函数 {handler.__name__} 返回了 None。文件ID: {media_file.id}, 类型: {metadata_type}")
                return False

            if metadata_type != "series" or not media_file.core_id:
                media_file.core_id = core.id

            core_repo.apply_file_path_info(session, media_file, path_info)

            session.flush()

            version_repo.cleanup_orphan_versions_after_rebind(
                session=session,
                user_id=media_file.user_id,
                old_version_id=old_version_id,
                new_version_id=getattr(media_file, "version_id", None),
                old_season_version_id=old_season_version_id,
                new_season_version_id=getattr(media_file, "season_version_id", None),
            )
            session.flush()
            return True

        except Exception as e:
            logger.error(f"应用元数据时发生未预期的错误: {e}", exc_info=True)
            return False

    def _apply_search_result(
        self, session: Session, media_file: FileAsset, metadata: ScraperSearchResult
    ) -> MediaCore:
        """处理搜索结果类型元数据"""
        core = session.exec(select(MediaCore).where(MediaCore.id == media_file.core_id)).first()
        title_val = getattr(metadata, "title", None) or ""
        mt = getattr(metadata, "media_type", None) or "movie"
        kind_val = "movie" if mt == "movie" else "series"
        year_val = getattr(metadata, "year", None)
        if not core:
            core = MediaCore(
                user_id=media_file.user_id,
                kind=kind_val,
                title=title_val,
                original_title=None,
                year=year_val,
                plot=None,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(core)
            session.flush()
            media_file.core_id = core.id
        else:
            core.kind = kind_val
            core.title = title_val
            core.year = year_val
            core.updated_at = datetime.now()
        try:
            if kind_val == "movie":
                mx = session.exec(select(MovieExt).where(MovieExt.core_id == core.id, MovieExt.user_id == media_file.user_id)).first()
                if not mx:
                    mx = MovieExt(user_id=media_file.user_id, core_id=core.id)
                    session.add(mx)
                mx.poster_path = getattr(metadata, "poster_path", None) or mx.poster_path
            elif kind_val == "series":
                tv = session.exec(select(SeriesExt).where(SeriesExt.core_id == core.id, SeriesExt.user_id == media_file.user_id)).first()
                if not tv:
                    tv = SeriesExt(user_id=media_file.user_id, core_id=core.id)
                    session.add(tv)
                tv.poster_path = getattr(metadata, "poster_path", None) or tv.poster_path
        except Exception:
            pass
        return core
