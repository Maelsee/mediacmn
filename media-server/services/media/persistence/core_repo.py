"""MediaCore 与扩展表持久化

提供 _apply_movie_detail、_apply_series_detail、_apply_season_detail、
_apply_episode_detail、_apply_file_path_info、_check_series_type 方法。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlmodel import Session, select, update
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from models.media_models import (
    MediaCore, FileAsset, MovieExt, EpisodeExt, SeasonExt, SeriesExt, Collection,
)
from services.scraper import (
    ScraperMovieDetail,
    ScraperSeriesDetail,
    ScraperSeasonDetail,
    ScraperEpisodeDetail,
)

from .base import _DictWrapper, _get_attr, _parse_dt
from . import artwork_repo
from . import credit_repo
from . import genre_repo
from . import version_repo

logger = logging.getLogger(__name__)


def check_series_type(type: str, genres: List[str]) -> str:
    """判断系列类型(TV/Animation/Reality)"""
    if type:
        if type.lower() in ["reality", "variety", "真人秀"]:
            return "Reality"
        elif type.lower() in ["animation", "动画"]:
            return "Animation"
    if genres:
        for genre in genres:
            if genre.lower() in ["动画", "animation"]:
                return "Animation"
            if genre.lower() in ["真人秀", "reality", "variety"]:
                return "Reality"
    return "TV"


def apply_file_path_info(session: Session, media_file: FileAsset, path_info: Dict) -> None:
    """应用文件路径信息到领域模型"""
    savepoint = session.begin_nested()
    try:
        media_file.resolution = media_file.resolution or path_info.get("screen_size")
        media_file.frame_rate = media_file.frame_rate or path_info.get("frame_rate")
        media_file.mimetype = media_file.mimetype or path_info.get("mimetype")
        media_file.video_codec = media_file.video_codec or path_info.get("video_codec")
        media_file.audio_codec = media_file.audio_codec or path_info.get("audio_codec")
        media_file.container = media_file.container or path_info.get("container")
        media_file.updated_at = datetime.now()
        savepoint.commit()
    except Exception as e:
        logger.error(f"应用文件路径信息时发生错误: {str(e)}", exc_info=True)
        savepoint.rollback()


def apply_movie_detail(
    session: Session, media_file: FileAsset, metadata: ScraperMovieDetail
) -> MediaCore:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理电影核心信息、扩展信息和系列信息。
    """
    savepoint = session.begin_nested()
    try:
        user_id = media_file.user_id
        kind = "movie"

        title = metadata.title
        original_title = getattr(metadata, "original_title", None)
        plot = getattr(metadata, "overview", None)
        display_rating = getattr(metadata, "vote_average", None)
        display_poster_path = getattr(metadata, "poster_path", None)
        display_date, year_val = _parse_dt(getattr(metadata, "release_date", None))
        tmdb_id = str(getattr(metadata, "movie_id", None)) if getattr(metadata, "provider", None) == "tmdb" and getattr(metadata, "movie_id", None) else None

        # --- Upsert MediaCore ---
        stmt_core = insert(MediaCore).values(
            user_id=user_id,
            kind=kind,
            title=title,
            original_title=original_title,
            year=year_val,
            plot=plot,
            display_rating=display_rating,
            display_poster_path=display_poster_path,
            display_date=display_date,
            tmdb_id=tmdb_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).on_conflict_do_update(
            index_elements=["user_id", "kind", "tmdb_id"],
            set_={
                'original_title': original_title,
                'plot': plot,
                'display_rating': display_rating,
                'display_poster_path': display_poster_path,
                'display_date': display_date,
                'year': year_val,
                'title': title,
                'tmdb_id': func.coalesce(MediaCore.tmdb_id, tmdb_id),
                'updated_at': datetime.now()
            }
        ).returning(MediaCore.id)

        result = session.execute(stmt_core)
        core_id = result.scalar_one()
        media_file.core_id = core_id

        # --- Upsert MovieExt ---
        raw_data = getattr(metadata, 'raw_data', None)
        if isinstance(raw_data, _DictWrapper):
            raw_data = raw_data._data

        stmt_ext = insert(MovieExt).values(
            user_id=user_id,
            core_id=core_id,
            tagline=getattr(metadata, "tagline", None),
            title=title,
            rating=float(display_rating) if isinstance(display_rating, (int, float)) else None,
            overview=plot,
            origin_country=list(getattr(metadata, "origin_country", [])),
            release_date=display_date,
            poster_path=display_poster_path,
            backdrop_path=getattr(metadata, "backdrop_path", None),
            imdb_id=getattr(metadata, "imdb_id", None),
            runtime_minutes=getattr(metadata, "runtime", None),
            status=getattr(metadata, "status", None),
            raw_data=json.dumps(raw_data, ensure_ascii=False)
        ).on_conflict_do_update(
            index_elements=['user_id', 'core_id'],
            set_={
                'tagline': getattr(metadata, "tagline", None),
                'title': title,
                'rating': float(display_rating) if isinstance(display_rating, (int, float)) else MovieExt.rating,
                'overview': plot,
                'origin_country': list(getattr(metadata, "origin_country", [])),
                'release_date': display_date,
                'poster_path': display_poster_path,
                'backdrop_path': getattr(metadata, "backdrop_path", None),
                'imdb_id': getattr(metadata, "imdb_id", None),
                'runtime_minutes': getattr(metadata, "runtime", None),
                'status': getattr(metadata, "status", None),
                'raw_data': json.dumps(raw_data, ensure_ascii=False)
            }
        )
        session.execute(stmt_ext)

        # --- 处理 Collection ---
        collection_id = None
        col_data = getattr(metadata, "belongs_to_collection", None)
        if isinstance(col_data, dict) and col_data.get("id"):
            col_id = col_data.get("id")
            stmt_collection = insert(Collection).values(
                id=col_id,
                name=col_data.get("name"),
                poster_path=col_data.get("poster_path"),
                backdrop_path=col_data.get("backdrop_path"),
                overview=col_data.get("overview"),
                updated_at=datetime.now()
            ).on_conflict_do_update(
                index_elements=['id'],
                set_={
                    'name': col_data.get("name"),
                    'poster_path': col_data.get("poster_path"),
                    'backdrop_path': col_data.get("backdrop_path"),
                    'overview': col_data.get("overview"),
                    'updated_at': datetime.now()
                }
            )
            session.execute(stmt_collection)
            collection_id = col_id

        if collection_id:
            session.execute(
                update(MovieExt).where(
                    MovieExt.user_id == user_id,
                    MovieExt.core_id == core_id
                ).values(collection_id=collection_id)
            )

        # --- 调用 Upsert 辅助函数 ---
        artwork_repo.upsert_artworks(session, user_id, core_id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
        credit_repo.upsert_credits(session, user_id, core_id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
        genre_repo.upsert_genres(session, user_id, core_id, getattr(metadata, "genres", []) or [])
        artwork_repo.upsert_external_ids(session, user_id, core_id, getattr(metadata, "external_ids", None))

        # --- 更新媒体版本 ---
        core = session.get(MediaCore, core_id)
        version_id = version_repo.upsert_media_version(session, media_file, core, metadata)
        media_file.version_id = version_id
        media_file.updated_at = datetime.now()

        savepoint.commit()
        return core

    except Exception as e:
        logger.error(f"处理电影元数据失败: {e}", exc_info=True)
        savepoint.rollback()
        raise


def apply_series_detail(
    session: Session, user_id: int, sd: ScraperSeriesDetail
) -> MediaCore:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理剧集核心信息和扩展信息。
    """
    savepoint = session.begin_nested()
    try:
        name_val = getattr(sd, "name", None) or ""
        genres = getattr(sd, "genres", []) or []
        first_air_date, year_val = _parse_dt(getattr(sd, "first_air_date", None))
        last_air_date, _ = _parse_dt(getattr(sd, "last_air_date", None))
        tmdb_id = str(getattr(sd, "series_id", None)) if getattr(sd, "provider", None) == "tmdb" and getattr(sd, "series_id", None) else None
        type_val = getattr(sd, "type", None)
        try:
            type_val = check_series_type(type_val, genres)
        except Exception as e:
            logger.error(f"系类类型判断出错: {e}")
            type_val = "TV"

        # --- Upsert MediaCore (Series) ---
        stmt_core = insert(MediaCore).values(
            user_id=user_id,
            kind="series",
            title=name_val,
            original_title=getattr(sd, "original_name", None),
            year=year_val,
            plot=getattr(sd, "overview", None),
            display_rating=getattr(sd, "vote_average", None),
            display_poster_path=getattr(sd, "poster_path", None),
            display_date=first_air_date,
            subtype=type_val,
            tmdb_id=tmdb_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).on_conflict_do_update(
            index_elements=["user_id", "kind", "tmdb_id"],
            set_={
                'plot': getattr(sd, "overview", None),
                'updated_at': datetime.now()
            }
        ).returning(MediaCore.id)

        result = session.execute(stmt_core)
        series_core_id = result.scalar_one()

        # --- Upsert SeriesExt ---
        raw_data = getattr(sd, 'raw_data', None)
        if isinstance(raw_data, _DictWrapper):
            raw_data = raw_data._data

        stmt_ext = insert(SeriesExt).values(
            user_id=user_id,
            core_id=series_core_id,
            title=name_val,
            overview=getattr(sd, "overview", None),
            season_count=getattr(sd, "number_of_seasons", None),
            episode_count=getattr(sd, "number_of_episodes", None),
            episode_run_time=int(getattr(sd, "episode_run_time", [None])[0]) if isinstance(getattr(sd, "episode_run_time", []), list) and getattr(sd, "episode_run_time", []) else None,
            status=getattr(sd, "status", None),
            rating=getattr(sd, "vote_average", None),
            origin_country=list(getattr(sd, "origin_country", []) or []),
            aired_date=first_air_date,
            last_aired_date=last_air_date,
            poster_path=getattr(sd, "poster_path", None),
            backdrop_path=getattr(sd, "backdrop_path", None),
            series_type=type_val,
            raw_data=json.dumps(raw_data, ensure_ascii=False)
        ).on_conflict_do_update(
            index_elements=['user_id', 'core_id'],
            set_={
                'overview': getattr(sd, "overview", None),
            }
        )
        session.execute(stmt_ext)

        # --- 调用 Upsert 辅助函数 ---
        genre_repo.upsert_genres(session, user_id, series_core_id, genres)
        artwork_repo.upsert_artworks(session, user_id, series_core_id, getattr(sd, "provider", None), getattr(sd, "artworks", None))
        artwork_repo.upsert_external_ids(session, user_id, series_core_id, getattr(sd, "external_ids", None))

        savepoint.commit()

        series_core = session.get(MediaCore, series_core_id)
        if not series_core:
            raise RuntimeError(f"UPSERT 成功但未查询到 series_core（ID: {series_core_id}）")
        return series_core

    except Exception as e:
        savepoint.rollback()
        logger.error(f"处理系列信息时发生错误，已回滚保存点: {str(e)}", exc_info=True)
        raise


def apply_season_detail(
    session: Session, user_id: int, series_core: Optional[MediaCore], se: ScraperSeasonDetail
) -> MediaCore:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理季核心信息和扩展信息。
    """
    savepoint = session.begin_nested()
    try:
        season_num = getattr(se, "season_number", None)
        season_name = getattr(se, "name", None)
        air_date, year_val = _parse_dt(getattr(se, "air_date", None))
        tmdb_id = str(getattr(se, "season_id", None)) if getattr(se, "provider", None) == "tmdb" and getattr(se, "season_id", None) else None

        # --- Upsert MediaCore (Season) ---
        stmt_core = insert(MediaCore).values(
            user_id=user_id,
            kind="season",
            title=f"{series_core.title}-{season_name}",
            year=year_val,
            display_date=air_date,
            display_poster_path=getattr(se, "poster_path", None),
            display_rating=getattr(se, "vote_average", None),
            tmdb_id=tmdb_id,
            parent_id=series_core.id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).on_conflict_do_update(
            index_elements=["user_id", "kind", "tmdb_id"],
            set_={
                'updated_at': datetime.now()
            }
        ).returning(MediaCore.id)

        result = session.execute(stmt_core)
        season_core_id = result.scalar_one()

        # --- Upsert SeasonExt ---
        raw_data = getattr(se, 'raw_data', None)
        if isinstance(raw_data, _DictWrapper):
            raw_data = raw_data._data

        stmt_ext = insert(SeasonExt).values(
            user_id=user_id,
            core_id=season_core_id,
            series_core_id=series_core.id if series_core else None,
            season_number=season_num,
            title=f"{series_core.title}-{season_name}",
            overview=getattr(se, "overview", None),
            episode_count=getattr(se, "episode_count", None),
            rating=getattr(se, "vote_average", None),
            aired_date=air_date,
            poster_path=getattr(se, "poster_path", None),
            raw_data=json.dumps(raw_data, ensure_ascii=False)
        ).on_conflict_do_update(
            index_elements=['user_id', 'series_core_id', 'season_number'],
            set_={
                'title': f"{series_core.title}-{season_name}",
                'overview': getattr(se, "overview", None),
            }
        )
        session.execute(stmt_ext)

        # --- 调用 Upsert 辅助函数 ---
        artwork_repo.upsert_artworks(session, user_id, season_core_id, getattr(se, "provider", None), getattr(se, "artworks", None))
        credit_repo.upsert_credits(session, user_id, season_core_id, getattr(se, "credits", None), getattr(se, "provider", None))
        artwork_repo.upsert_external_ids(session, user_id, season_core_id, getattr(se, "external_ids", None))

        savepoint.commit()
        return session.get(MediaCore, season_core_id)

    except Exception as e:
        savepoint.rollback()
        logger.error(f"处理季信息时发生错误，已回滚保存点: {str(e)}", exc_info=True)
        raise e


def apply_episode_detail(
    session: Session, media_file: FileAsset, metadata: ScraperEpisodeDetail
) -> MediaCore:
    """
    使用数据库级别的 UPSERT 操作来原子化地处理单集核心信息和扩展信息。
    """
    savepoint = session.begin_nested()
    try:
        user_id = media_file.user_id
        title_val = getattr(metadata, "name", None) or ""
        air_date, year_val = _parse_dt(getattr(metadata, "air_date", None))
        tmdb_id = str(getattr(metadata, "episode_id", None)) if getattr(metadata, "provider", None) == "tmdb" and getattr(metadata, "episode_id", None) else None
        still_path_url = getattr(metadata, "still_path", None)

        # 获取或创建 series_core 和 season_core
        series_core = None
        season_core = None
        season_version_id = None
        try:
            if getattr(metadata, "series", None):
                series_core = apply_series_detail(session, user_id, metadata.series)
            if getattr(metadata, "season", None) and series_core:
                season_core = apply_season_detail(session, user_id, series_core, metadata.season)
                season_version_id = version_repo.upsert_season_version(session, media_file, season_core)
        except Exception as e:
            logger.error(f"创建/更新季/系列信息失败: {e}", exc_info=True)
            return None

        # --- Upsert MediaCore (Episode) ---
        stmt_core = insert(MediaCore).values(
            user_id=user_id,
            kind="episode",
            title=title_val,
            plot=getattr(metadata, "overview", None),
            display_rating=getattr(metadata, "vote_average", None),
            display_poster_path=still_path_url,
            display_date=air_date,
            year=year_val,
            tmdb_id=tmdb_id,
            parent_id=season_core.id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).on_conflict_do_update(
            index_elements=["user_id", "kind", "tmdb_id"],
            set_={
                'updated_at': datetime.now()
            }
        ).returning(MediaCore.id)

        result = session.execute(stmt_core)
        episode_core_id = result.scalar_one()
        logger.debug(f"旧ID：{media_file.core_id} 新核心ID: {episode_core_id}")
        media_file.core_id = episode_core_id

        # --- Upsert EpisodeExt ---
        stmt_ext = insert(EpisodeExt).values(
            user_id=user_id,
            core_id=episode_core_id,
            series_core_id=series_core.id if series_core else EpisodeExt.series_core_id,
            season_core_id=season_core.id if season_core else EpisodeExt.season_core_id,
            season_number=getattr(metadata, "season_number", 1),
            episode_number=getattr(metadata, "episode_number", 1),
            title=title_val,
            overview=getattr(metadata, "overview", None),
            runtime=getattr(metadata, "runtime", None),
            rating=getattr(metadata, "vote_average", None),
            vote_count=getattr(metadata, "vote_count", None),
            still_path=still_path_url,
            episode_type=getattr(metadata, "episode_type", None),
            aired_date=air_date
        ).on_conflict_do_update(
            index_elements=['user_id', 'series_core_id', 'season_number', 'episode_number'],
            set_={
                'core_id': episode_core_id,
                'season_core_id': season_core.id if season_core else EpisodeExt.season_core_id,
                'title': title_val,
                'overview': getattr(metadata, "overview", None),
                'runtime': getattr(metadata, "runtime", None),
                'rating': getattr(metadata, "vote_average", None),
                'vote_count': getattr(metadata, "vote_count", None),
                'still_path': still_path_url,
                'episode_type': getattr(metadata, "episode_type", None),
                'aired_date': air_date
            }
        )
        session.execute(stmt_ext)

        # --- 调用 Upsert 辅助函数 ---
        credit_repo.upsert_credits(session, user_id, episode_core_id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
        artwork_repo.upsert_external_ids(session, user_id, episode_core_id, getattr(metadata, "external_ids", None))

        # --- 更新媒体版本 ---
        episode_core = session.get(MediaCore, episode_core_id)
        version_id = version_repo.upsert_media_version(session, media_file, episode_core, metadata, season_version_id)
        media_file.version_id = version_id
        media_file.season_version_id = season_version_id
        media_file.updated_at = datetime.now()

        savepoint.commit()
        return episode_core

    except Exception as e:
        savepoint.rollback()
        logger.error(f"处理季信息时发生错误，已回滚保存点: {str(e)}", exc_info=True)
        raise e


