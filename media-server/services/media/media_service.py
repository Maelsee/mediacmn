from __future__ import annotations

import datetime
from typing import Optional, Dict, Any, List

from core.config import get_settings
import redis
import json
from sqlmodel import Session, select, func, and_, or_, case

import logging
logger = logging.getLogger(__name__)

from models.media_models import MediaCore
from models.media_models import MovieExt, MediaVersion
from models.media_models import SeriesExt, SeasonExt, EpisodeExt
from models.media_models import FileAsset
from models.media_models import Artwork
from models.media_models import ExternalID
from models.media_models import Genre, MediaCoreGenre
from models.media_models import Person, Credit
from models.storage_models import StorageConfig
from services.media.metadata_persistence_service import MetadataPersistenceService


class MediaService:
    def __init__(self):
        # 初始化Redis连接
        # self.redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        self.CACHE_EXPIRE_SECONDS = 3600
        s = get_settings()
        try:
            self._redis = redis.from_url(s.REDIS_URL, db=3, decode_responses=True)
            # 测试连接
            self._redis.ping()
        except redis.ConnectionError as e:
            logger.error(f"MediaService: 媒体服务中Redis连接失败: {e}")
            # 根据业务需求处理，如抛出异常或使用备用方案

    def _runtime_text(self, minutes: Optional[int]) -> Optional[str]:
        if minutes is None:
            return None
        try:
            m = int(minutes)
        except Exception:
            return None
        if m <= 0:
            return None
        h = m // 60
        mm = m % 60
        if h > 0:
            return f"{h}小时 {mm} 分钟" if mm else f"{h}小时"
        return f"{mm} 分钟"
    def _to_human_size(self, size: Optional[int]) -> Optional[str]:
        if size is None:
            return None
        units = ["B", "KB", "MB", "GB", "TB"]
        s = float(size)
        i = 0
        while s >= 1024 and i < len(units) - 1:
            s /= 1024
            i += 1
        return f"{s:.2f} {units[i]}"

    def _choose_primary_asset(self, assets: List[FileAsset]) -> Optional[FileAsset]:
        if not assets:
            return None
        for a in assets:
            t = getattr(a, "asset_role", None) or self._normalize_asset_type(a)
            if t == "video":
                return a
        return assets[0]


    
    def _get_storage_info(self, db: Session, storage_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if not storage_id:
            return None

        # 1. 查Redis缓存
        cache_key = f"MediaService:storage_sample_info:{storage_id}"
        cache_data = self._redis.get(cache_key)
        if cache_data:
            return json.loads(cache_data) if cache_data != "null" else None

        # 2. 查库
        st = db.exec(select(StorageConfig).where(StorageConfig.id == storage_id)).first()
        if not st:
            # 缓存空值，防止穿透
            self._redis.setex(cache_key, 60, "null")
            return None

        # 3. 组装结果
        storage_info = {
            "id": st.id,
            "name": st.name,
            "type": st.storage_type
        }

        # 4. 存入Redis
        self._redis.setex(cache_key, self.CACHE_EXPIRE_SECONDS, json.dumps(storage_info))

        return storage_info

    def _normalize_asset_type(self, asset: FileAsset) -> str:
        p = getattr(asset, "full_path", None) or ""
        fn = getattr(asset, "filename", None) or ""
        mt = getattr(asset, "mimetype", None) or ""
        lowp = p.lower()
        lowfn = fn.lower()
        if lowp.endswith(".m3u8") or lowfn.endswith(".m3u8"):
            return "hls_master"
        if mt.startswith("video/"):
            return "video"
        if mt.startswith("audio/"):
            return "audio"
        if mt.startswith("image/"):
            return "image"
        exts_video = {"mp4","mkv","mov","avi","wmv","flv","webm","m4v"}
        exts_audio = {"mp3","flac","wav","aac","ogg","wma","m4a"}
        exts_sub = {"srt","ass","ssa","vtt","sub"}
        exts_img = {"jpg","jpeg","png","gif","bmp","webp","tiff","svg"}
        ext = lowfn.split(".")[-1] if "." in lowfn else ""
        if ext in exts_video:
            return "video"
        if ext in exts_audio:
            return "audio"
        if ext in exts_sub:
            return "subtitle"
        if ext in exts_img:
            return "image"
        if ext == "nfo":
            return "nfo"
        return "file"
    # 首页卡片
    def list_media_cards(
        self,
        db: Session,
        user_id: int,
    ) -> Dict[str, Any]:
        
        # 流派card 10条（修正版：通过中间表关联用户媒体）
        genre_rows = db.exec(
            select(Genre)  # 最终要获取的是Genre表数据
            .distinct()  # 去重：避免同一流派被多个媒体关联而重复出现
            # 第一步：关联中间表MediaCoreGenre（Genre ↔ MediaCoreGenre）
            .join(MediaCoreGenre, MediaCoreGenre.genre_id == Genre.id, isouter=False)  # 内连接：只保留有媒体关联的流派
            # 第二步：关联用户媒体表MediaCore（MediaCoreGenre ↔ MediaCore）
            # .join(MediaCore, MediaCore.id == MediaCoreGenre.media_core_id, isouter=False)  # 内连接：只保留用户有所有权的媒体
            # 关键：通过MediaCore.user_id过滤当前用户（Genre无user_id，转由关联的MediaCore过滤）
            .where(MediaCoreGenre.user_id == user_id)
            .order_by(Genre.name)  # 按流派名称排序
            .limit(10)  # 限制10条结果
        ).all()

        genre_cards: List[Dict[str, Any]] = []
        for g in genre_rows:
            genre_cards.append({
                "id": g.id,
                "name": g.name,
            })
        # 电影card 10条
        movie_rows = db.exec(
            select(MediaCore, MovieExt)
            .join(MovieExt, MovieExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "movie"))
            .order_by(MediaCore.updated_at.desc())
            .limit(10)
        ).all()
        movie_cards: List[Dict[str, Any]] = []
        for core, mx in movie_rows:
            released = None
            rd = getattr(core, "display_date", None) or (getattr(mx, "release_date", None) if mx else None)
            if rd:
                try:
                    released = rd.isoformat()
                except Exception:
                    released = rd
            poster_url = getattr(core, "display_poster_path", None) or (getattr(mx, "poster_path", None) if mx else None)
            movie_cards.append({
                "id": core.id,
                "name": core.title,
                "cover_url": poster_url,
                "rating": getattr(core, "display_rating", None) or (getattr(mx, "rating", None) if mx else None),
                "release_date": released,
                "media_type": "movie",
            })
        # 剧集card 10条
        tv_rows = db.exec(
            select(MediaCore, SeriesExt)
            .join(SeriesExt, SeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "series",MediaCore.subtype == 'TV'))
            .order_by(MediaCore.updated_at.desc())
            .limit(10)
        ).all()
        tv_cards: List[Dict[str, Any]] = []
        for core, series_ext in tv_rows:
            released = None
            rd = getattr(core, "display_date", None)
            if rd:
                try:
                    released = rd.isoformat()
                except Exception:
                    released = rd
            poster_url2 = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
            tv_cards.append({
                "id": core.id,
                "name": core.title,
                "cover_url": poster_url2,
                "rating": getattr(core, "display_rating", None) or (getattr(series_ext, "rating", None) if series_ext else None),
                "release_date": released,
                "media_type": "tv",
            })
        # 动画card 10条
        animation_rows = db.exec(
            select(MediaCore, SeriesExt)
            .join(SeriesExt, SeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "series", MediaCore.subtype == 'Animation'))
            .order_by(MediaCore.updated_at.desc()) 
            .limit(10)
        ).all()
        animation_cards: List[Dict[str, Any]] = []
        for core, series_ext in animation_rows:
            released = None
            rd = getattr(core, "display_date", None)
            if rd:
                try:
                    released = rd.isoformat()
                except Exception:
                    released = rd
            poster_url2 = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
            animation_cards.append({
                "id": core.id,
                "name": core.title,
                "cover_url": poster_url2,
                "rating": getattr(core, "display_rating", None) or (getattr(series_ext, "rating", None) if series_ext else None),
                "release_date": released,
                "media_type": "animation",
            })
        # 真人秀card 10条
        reality_rows = db.exec(
            select(MediaCore, SeriesExt)
            .join(SeriesExt, SeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "series", MediaCore.subtype == 'Reality'))
            .order_by(MediaCore.updated_at.desc())
            .limit(10)
        ).all()
        reality_cards: List[Dict[str, Any]] = []
        for core, series_ext in reality_rows:
            released = None
            rd = getattr(core, "display_date", None)
            if rd:
                try:
                    released = rd.isoformat()
                except Exception:
                    released = rd
            poster_url2 = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
            reality_cards.append({
                "id": core.id,
                "name": core.title,
                "cover_url": poster_url2,
                "rating": getattr(core, "display_rating", None) or (getattr(series_ext, "rating", None) if series_ext else None),
                "release_date": released,
                "media_type": "reality",
            })
        return {"genres": genre_cards, "movie": movie_cards, "tv": tv_cards, "animation": animation_cards, "reality": reality_cards}
    
    def filter_media_cards(
        self,
        db: Session,
        user_id: int,
        page: int = 1,
        page_size: int = 24,
        q: Optional[str] = None,
        type_filter: Optional[str] = None,
        genres: Optional[List[str]] = None,
        year: Optional[int] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        countries: Optional[List[str]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 仅筛选电影与系列，排除季与集
        stmt = select(MediaCore).where(and_(MediaCore.user_id == user_id, MediaCore.kind.in_(["movie", "series"])))
        if type_filter:
            if type_filter == "movie":
                stmt = stmt.where(MediaCore.kind == "movie")
            elif type_filter in ("tv", "series"):
                stmt = stmt.where(MediaCore.kind == "series", MediaCore.subtype == 'TV')
            elif type_filter == "animation":
                stmt = stmt.where(MediaCore.kind == "series", MediaCore.subtype == 'Animation')
            elif type_filter == "reality":
                stmt = stmt.where(MediaCore.kind == "series", MediaCore.subtype == 'Reality')
        if q:
            like_q = f"%{q}%"
            stmt = stmt.where(or_(MediaCore.title.ilike(like_q), MediaCore.original_title.ilike(like_q)))
        if year is not None:
            stmt = stmt.where(MediaCore.year == year)
        else:
            if year_start is not None:
                stmt = stmt.where(MediaCore.year >= year_start)
            if year_end is not None:
                stmt = stmt.where(MediaCore.year <= year_end)
        if genres:
            stmt = stmt.join(MediaCoreGenre, MediaCoreGenre.core_id == MediaCore.id).join(Genre, Genre.id == MediaCoreGenre.genre_id).where(Genre.name.in_(genres))
        try:
            if countries:
                stmt = stmt.where(getattr(MediaCore, "countries").op("?|")(countries))
        except Exception:
            pass

        total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
        # 排序：updated|released|added|rating
        if sort == "released":
            # 使用显示缓存：电影用 MovieExt.release_date，系列用 SeasonExt 首季 aired_date。已在 display_date 缓存。
            stmt = stmt.order_by(MediaCore.display_date.desc())
        elif sort == "added":
            stmt = stmt.order_by(MediaCore.created_at.desc())
        elif sort == "rating":
            # 显示评分缓存
            stmt = stmt.order_by(MediaCore.display_rating.desc())
        else:
            # 默认最新更新
            stmt = stmt.order_by(MediaCore.updated_at.desc())
        
        # Optimize: Join with Ext tables to avoid N+1
        # However, since we need conditional join based on kind, it's tricky in one query unless we use outer joins for both.
        # Given pagination is small (24), we can just fetch extensions in bulk or keep as is if performance is acceptable.
        # But let's try to optimize slightly by fetching all cores then bulk fetching exts.
        
        rows = db.exec(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        
        # Bulk fetch extensions
        core_ids = [c.id for c in rows]
        movie_exts = {}
        series_exts = {}
        if core_ids:
            m_exts = db.exec(select(MovieExt).where(MovieExt.core_id.in_(core_ids))).all()
            for m in m_exts:
                movie_exts[m.core_id] = m
            
            t_exts = db.exec(select(SeriesExt).where(SeriesExt.core_id.in_(core_ids))).all()
            for t in t_exts:
                series_exts[t.core_id] = t

        items: List[Dict[str, Any]] = []
        for core in rows:
            rating = None
            released = None
            poster = None
            if core.kind == "movie":
                mx = movie_exts.get(core.id)
                if mx:
                    rating = getattr(core, "display_rating", None) or getattr(mx, "rating", None)
                    poster = getattr(core, "display_poster_path", None) or getattr(mx, "poster_path", None)
                    rd = getattr(core, "display_date", None) or getattr(mx, "release_date", None)
                    if rd:
                        try:
                            released = rd.isoformat()
                        except Exception:
                            released = rd
            elif core.kind == "series":
                series_ext = series_exts.get(core.id)
                if series_ext:
                    rating = getattr(core, "display_rating", None) or getattr(series_ext, "rating", None)
                    poster = getattr(core, "display_poster_path", None) or getattr(series_ext, "poster_path", None)
                rd = getattr(core, "display_date", None)
                if rd:
                    try:
                        released = rd.isoformat()
                    except Exception:
                        released = rd
            items.append({
                "id": core.id,
                "name": core.title,
                "rating": rating,
                "release_date": released,
                "cover_url": poster,
                "media_type": "movie" if core.kind == "movie" else "tv",
            })
        type_counts = {
            "movie": db.exec(select(func.count()).where(MediaCore.user_id == user_id, MediaCore.kind == "movie")).one(),
            "tv": db.exec(select(func.count()).where(MediaCore.user_id == user_id, MediaCore.kind == "series")).one(),
        }
        return {"page": page, "page_size": page_size, "total": total, "items": items, "type_counts": type_counts}
    
    def get_media_detail(self, db: Session, user_id: int, core_id: int) -> Dict[str, Any]:
        core = db.exec(select(MediaCore).where(MediaCore.user_id == user_id, MediaCore.id == core_id)).first()
        if not core:
            return {"error": "not_found"}
        
        # Common data
        genres = self._get_genres(db, user_id, core.id)
        cast = self._get_cast(db, user_id, core.id)
        
        if core.kind == "movie":
            movie_ext = db.exec(select(MovieExt).where(MovieExt.core_id == core.id)).first()
            versions = self._get_movie_versions(db, user_id, core.id)
            
            # Use poster/backdrop logic from movie_ext
            poster_url = getattr(movie_ext, "poster_path", None) if movie_ext else None
            backdrop_url = getattr(movie_ext, "backdrop_path", None) if movie_ext else None
            backdrop_url = backdrop_url or poster_url
            
            return {
                "id": core.id,
                "title": core.title,
                "poster_path": poster_url,
                "backdrop_path": backdrop_url,
                "rating": movie_ext.rating if movie_ext and hasattr(movie_ext, "rating") else None,
                "release_date": movie_ext.release_date.isoformat() if (movie_ext and getattr(movie_ext, "release_date", None)) else None,
                "overview": core.plot,
                "genres": genres,
                "versions": versions,
                "cast": cast,
                "media_type": "movie",
                "runtime": getattr(movie_ext, "runtime_minutes", None) if movie_ext else None,
                "runtime_text": self._runtime_text(getattr(movie_ext, "runtime_minutes", None) if movie_ext else None),
                "directors": self._get_crew(db, user_id, core.id, "Director"),
                "writers": self._get_crew(db, user_id, core.id, "Writer"),
            }
        else:
            # series_detail = self._get_series_detail(db, user_id, core.id)
            # return series_detail
            return self._get_series_detail2(db, user_id, core.id)

            # series_ext = db.exec(select(SeriesExt).where(SeriesExt.core_id == core.id)).first()
            
            # # Optimized Season/Episode fetching
            # # 1. Fetch all seasons
            # seasons = db.exec(
            #     select(MediaCore, SeasonExt)
            #     .join(SeasonExt, SeasonExt.core_id == MediaCore.id)
            #     .where(and_(MediaCore.user_id == user_id, SeasonExt.series_core_id == core.id))
            #     .order_by(SeasonExt.season_number)
            # ).all()
            
            # season_ids = [s[0].id for s in seasons]
            
            # # 2. Fetch all episodes for these seasons
            # episodes_data = []
            # if season_ids:
            #     episodes_data = db.exec(
            #         select(MediaCore, EpisodeExt)
            #         .join(EpisodeExt, EpisodeExt.core_id == MediaCore.id)
            #         .where(and_(MediaCore.user_id == user_id, EpisodeExt.season_core_id.in_(season_ids)))
            #         .order_by(EpisodeExt.episode_number)
            #     ).all()
            
            # # Group episodes by season
            # episodes_map = {} # season_core_id -> list of episode tuples
            # episode_core_ids = []
            # for e_core, e_ext in episodes_data:
            #     sid = e_ext.season_core_id
            #     if sid not in episodes_map:
            #         episodes_map[sid] = []
            #     episodes_map[sid].append((e_core, e_ext))
            #     episode_core_ids.append(e_core.id)

            # # 3. Fetch all assets for these episodes (to avoid N+1 in _get_episode_assets)
            # assets_map = {} # episode_core_id -> list of assets
            # if episode_core_ids:
            #     all_assets = db.exec(
            #         select(FileAsset).where(and_(FileAsset.user_id == user_id, FileAsset.core_id.in_(episode_core_ids)))
            #     ).all()
            #     for a in all_assets:
            #         if a.core_id not in assets_map:
            #             assets_map[a.core_id] = []
            #         assets_map[a.core_id].append(a)

            # # Build result
            # series_poster = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
            
            # enriched_seasons = []
            # for s_core, s_ext in seasons:
            #     # Build episodes list
            #     season_eps = episodes_map.get(s_core.id, [])
            #     enriched_eps = []
            #     for e_core, e_ext in season_eps:
            #         e_assets_list = assets_map.get(e_core.id, [])
            #         # Normalize assets
            #         e_assets_dicts = [{
            #             "file_id": asset.id,
            #             "path": asset.full_path,
            #             "size": asset.size,
            #             "size_text": self._to_human_size(asset.size),
            #             "language": getattr(asset, "language", None),
            #             "storage": self._get_storage_info(db, getattr(asset, "storage_id", None)),
            #         } for asset in e_assets_list]

            #         enriched_eps.append({
            #             "id": e_core.id,
            #             "episode_number": e_ext.episode_number,
            #             "title": e_core.title,
            #             "still_path": getattr(e_ext, "still_path", None),
            #             "assets": e_assets_dicts
            #         })

            #     r = getattr(s_ext, "runtime", None) or (getattr(series_ext, "episode_run_time", None) if series_ext else None)
            #     ov = getattr(s_ext, "overview", None) or (getattr(series_ext, "overview", None) if series_ext else None) or s_core.plot
            #     rtg = getattr(s_ext, "rating", None) or (getattr(series_ext, "rating", None) if series_ext else None)
            #     enriched_seasons.append({
            #         "id": s_core.id,
            #         "season_number": s_ext.season_number,
            #         "title": s_core.title,
            #         "air_date": s_ext.aired_date.isoformat() if s_ext.aired_date else None,
            #         "cover": getattr(s_core, "display_poster_path", None) or getattr(s_ext, "poster_path", None),
            #         "cast": self._get_cast(db, user_id, s_core.id) or cast,
            #         "overview": ov,
            #         "rating": rtg,
            #         "runtime": r,
            #         "runtime_text": self._runtime_text(r),
            #         "episodes": enriched_eps,
            #     })

            # return {
            #     "id": core.id,
            #     "title": core.title,
            #     "poster_path": series_poster,
            #     "backdrop_path": getattr(series_ext, "backdrop_path", None) if series_ext else None,
            #     "rating": getattr(series_ext, "rating", None) if series_ext else None,
            #     "release_date": getattr(series_ext, "aired_date", None).isoformat() if (series_ext and getattr(series_ext, "aired_date", None)) else None,
            #     "overview": getattr(series_ext, "overview", None) or core.plot,
            #     "genres": genres,
            #     "versions": None,
            #     "cast": cast,
            #     "media_type": "tv",
            #     "runtime": getattr(series_ext, "episode_run_time", None) if series_ext else None,
            #     "runtime_text": self._runtime_text(getattr(series_ext, "episode_run_time", None) if series_ext else None),
            #     "season_count": getattr(series_ext, "season_count", None) if series_ext else None,
            #     "episode_count": getattr(series_ext, "episode_count", None) if series_ext else None,
            #     "seasons": enriched_seasons,
            #     "directors": None,
            #     "writers": None,
            # }
    
    def _get_genres(self, db: Session, user_id: int, core_id: int) -> List[str]:
        genres = db.exec(
            select(Genre.name)
            .join(MediaCoreGenre, MediaCoreGenre.genre_id == Genre.id)
            .where(
                    MediaCoreGenre.core_id == core_id,         
            )
            .distinct()
        ).all()
        return list(genres)

    # def _get_cast(self, db: Session, user_id: int, core_id: int) -> List[Dict[str, Any]]:
    #     """获取演员列表。"""
    #     # Optimized to select all needed fields in one query
    #     actor = db.exec(
    #         select(Person.name, Credit.character, Person.profile_url)
    #         .join(Credit, Credit.person_id == Person.id)
    #         .where(and_(
    #             Credit.user_id == user_id,
    #             Credit.core_id == core_id,
    #             Credit.role == "cast"
    #         ))
    #     ).all()
        

    #     return [{"name": name, "character": character, "image_url": purl} for name, character, purl in actor]
    

    # def _get_cast(self, db: Session, user_id: int, core_id: int) -> List[Dict[str, Any]]:
    #     """获取演职员列表：导演在前，演员/客串在后（单查询优化版）"""
    #     # 单查询合并两类数据：导演（crew+director/客串（cast+guest）
    #     # 用func.IF添加类型标识，用于排序和character赋值
    #     query = select(
    #         Person.name,
    #         Credit.character,
    #         Person.profile_url,
    #         # 类型标识：满足导演条件则为"director"，否则为"performer"
    #         func.IF(
    #             and_(Credit.role == "crew", Credit.job == "director"),  # 注：此处job="director"可能是笔误，建议确认是否为"导演"
    #             "director", 
    #             "performer"
    #         ).label("person_type")
    #     ).join(
    #         Credit, Credit.person_id == Person.id
    #     ).where(
    #         and_(
    #             Credit.user_id == user_id,
    #             Credit.core_id == core_id,
    #             # 合并条件：导演 OR 演员/客串
    #             or_(
    #                 and_(Credit.role == "crew", Credit.job == "director"),  # 导演条件
    #                 Credit.role.in_(["cast", "guest"])  # 演员（cast）+ 客串（guest）条件
    #             )
    #         )
    #     ).order_by(
    #         # 按类型标识升序："director"（导演）在前，"performer"（演员/客串）在后
    #         func.IF(
    #             and_(Credit.role == "crew", Credit.job == "director"),
    #             "director", 
    #             "performer"
    #         ),
    #         Credit.order.asc(),
    #     )

    #     # 执行单次查询
    #     results = db.exec(query).all()

    #     # 处理结果：根据类型标识赋值character
    #     return [
    #         {
    #             "name": name,
    #             # 导演固定显示"导演"，演员/客串用原始character
    #             "character": "导演" if person_type == "director" else character,
    #             "image_url": profile_url
    #         }
    #         for name, character, profile_url, person_type in results
    #     ]

    def _get_cast(self, db: Session, user_id: int, core_id: int) -> List[Dict[str, Any]]:
        """获取演职员列表：导演在前，演员/客串在后（单查询优化版）"""
        # 1. 定义条件：判断是否为“导演”（crew角色 + job=director）
        is_director = and_(Credit.role == "crew", Credit.job == "director")
        
        # 2. 单查询合并数据：用case()替代func.IF()
        query = select(
            Person.name,
            Credit.character,
            Person.profile_url,
            # 条件判断：是导演则为"director"，否则为"performer"（替代原func.IF）
            case(
                (is_director, "director"),  # 条件1：满足则返回"director"
                else_="performer"           # 其他情况返回"performer"
            ).label("person_type")
        ).join(
            Credit, Credit.person_id == Person.id
        ).where(
            and_(
                Credit.user_id == user_id,
                Credit.core_id == core_id,
                # 合并条件：导演（crew+director） OR 演员/客串（cast/guest）
                or_(
                    is_director,  # 复用上面定义的“导演条件”，避免重复代码
                    Credit.role.in_(["cast", "guest"])
                )
            )
        ).order_by(
            # 排序：导演在前（"director"），演员/客串在后（"performer"）（替代原func.IF）
            case(
                (is_director, "director"),
                else_="performer"
            ),
            Credit.order.asc()  # 原排序逻辑保留
        )

        # 执行查询并处理结果（原逻辑不变）
        results = db.exec(query).all()
        return [
            {
                "name": name,
                "character": "导演" if person_type == "director" else character,  # 导演固定显示“导演”
                "image_url": profile_url
            }
            for name, character, profile_url, person_type in results
        ]

    def _get_crew(self, db: Session, user_id: int, core_id: int, job: str) -> List[Dict[str, Any]]:
        people = db.exec(
            select(Person.name, Credit.character, Person.profile_url)
            .join(Credit, Credit.person_id == Person.id)
            .where(and_(
                Credit.user_id == user_id,
                Credit.core_id == core_id,
                Credit.job == job
            ))
        ).all()
        return [{"name": name, "character": character, "image_url": purl} for name, character, purl in people]

    def _get_movie_versions(self, db: Session, user_id: int, core_id: int) -> List[Dict[str, Any]]:
        """获取电影版本信息。"""
        # 1. 查询电影专属版本（过滤scope，添加排序）
        versions = db.exec(
            select(MediaVersion)
            .where(
                and_(
                    MediaVersion.user_id == user_id,
                    MediaVersion.core_id == core_id,
                    MediaVersion.scope == "movie_single"  # 过滤电影版本，排除季/剧集版本
                )
            )
            .order_by(MediaVersion.preferred.desc(), MediaVersion.created_at.desc())  # 首选版本在前，最新版本在前
        ).all()
        
        # 2. 批量获取版本关联的文件资产
        version_ids = [v.id for v in versions]
        assets_map = {}
        if version_ids:
            assets = db.exec(
                select(FileAsset).where(
                    and_(
                        FileAsset.user_id == user_id,
                        FileAsset.version_id.in_(version_ids)
                    )
                )
            ).all()
            # 构建版本ID到文件资产的映射
            for asset in assets:
                vid = asset.version_id
                if vid not in assets_map:
                    assets_map[vid] = []
                assets_map[vid].append(asset)
        
        
        result = []
        for version in versions:
            asset_list = []
            for asset in assets_map.get(version.id, []):
                asset_list.append({
                    "file_id": asset.id,
                    "path": asset.full_path,
                    # "type": getattr(asset, "asset_role", None) or self._normalize_asset_type(asset),
                    "size": asset.size,
                    "size_text": self._to_human_size(asset.size),
                    "language": getattr(asset, "language", None),
                    "storage": self._get_storage_info(db, getattr(asset, "storage_id", None)),
                })
            
            result.append({
                "id": version.id,
                "quality": version.quality,
                "assets": asset_list,
            })
        
        return result

    def list_media_files(
        self, 
        db: Session, 
        user_id: int,
        page: int = 1,
        page_size: int = 50,
        storage_id: Optional[int] = None,
        path: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取媒体文件列表"""
        # 构建查询条件
        conditions = [MediaCore.user_id == user_id]
        
        if storage_id:
            conditions.append(FileAsset.storage_id == storage_id)
        if path:
            conditions.append(FileAsset.full_path.like(f"%{path}%"))
        if media_type:
            conditions.append(MediaCore.media_type == media_type)
        
        # 基础查询
        query = select(MediaCore).where(and_(*conditions))
        
        # 关联文件资产
        if storage_id or path:
            query = query.join(FileAsset, FileAsset.core_id == MediaCore.id)
        
        # 计算总数
        total = db.exec(select(func.count()).select_from(query.subquery())).one()
        
        # 分页查询
        files = db.exec(
            query.order_by(MediaCore.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        
        # 获取文件资产信息
        result = []
        for media_core in files:
            assets = db.exec(
                select(FileAsset).where(
                    and_(
                        FileAsset.core_id == media_core.id,
                        FileAsset.user_id == user_id
                    )
                )
            ).all()
            
            result.append({
                "id": media_core.id,
                "title": media_core.title,
                "media_type": media_core.kind,
                "year": media_core.year,
                "rating": None,
                "created_at": media_core.created_at.isoformat() if media_core.created_at else None,
                "updated_at": media_core.updated_at.isoformat() if media_core.updated_at else None,
                "assets": [{
                    "id": asset.id,
                    "path": asset.full_path,
                    "playurl": getattr(asset, "playurl", None),
                    "type": getattr(asset, "asset_role", None) or self._normalize_asset_type(asset),
                    "size": asset.size,
                    "storage_id": asset.storage_id,
                    "language": getattr(asset, "language", None),
                } for asset in assets]
            })
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "files": result
        }
    
    def get_media_file_detail(self, db: Session, user_id: int, file_id: int) -> Dict[str, Any]:
        """获取媒体文件详细信息"""
        # 获取媒体核心信息
        media_core = db.exec(
            select(MediaCore).where(
                and_(
                    MediaCore.id == file_id,
                    MediaCore.user_id == user_id
                )
            )
        ).first()
        
        if not media_core:
            return {"error": "文件不存在"}
        
        # 获取文件资产
        assets = db.exec(
            select(FileAsset).where(
                and_(
                    FileAsset.core_id == file_id,
                    FileAsset.user_id == user_id
                )
            )
        ).all()
        
        # 获取元数据信息
        metadata = {}
        if media_core.kind == "movie":
            movie_ext = db.exec(select(MovieExt).where(MovieExt.core_id == file_id)).first()
            if movie_ext:
                metadata.update({
                    "tagline": movie_ext.tagline,
                    "runtime": getattr(movie_ext, "runtime", None),
                })
        
        # 获取外部ID
        external_ids = db.exec(select(ExternalID).where(ExternalID.core_id == file_id)).all()
        
        # 获取流派
        genres = db.exec(
            select(Genre).join(MediaCoreGenre).where(MediaCoreGenre.core_id == file_id)
        ).all()
        
        # 获取制作人员
        credits = db.exec(
            select(Person, Credit).join(Credit).where(Credit.core_id == file_id)
        ).all()
        
        return {
            "id": media_core.id,
            "title": media_core.title,
            "original_title": media_core.original_title,
            "media_type": media_core.kind,
            "year": media_core.year,
            "rating": None,
            "overview": media_core.plot,
            "created_at": media_core.created_at.isoformat() if media_core.created_at else None,
            "updated_at": media_core.updated_at.isoformat() if media_core.updated_at else None,
            "assets": [{
                "id": asset.id,
                "path": asset.full_path if hasattr(asset, "full_path") else getattr(asset, "path", None),
                "playurl": getattr(asset, "playurl", None),
                "type": getattr(asset, "asset_role", None) or self._normalize_asset_type(asset),
                "size": asset.size,
                "storage_id": asset.storage_id,
                "language": getattr(asset, "language", None),
                "checksum": getattr(asset, "checksum", None),
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            } for asset in assets],
            "metadata": metadata,
            "external_ids": [{
                "source": ext_id.source,
                "key": ext_id.key,
            } for ext_id in external_ids],
            "genres": [genre.name for genre in genres],
            "credits": [{
                "person": {
                    "id": person.id,
                    "name": person.name,
                },
                "role": credit.role,
                "order": credit.order,
            } for person, credit in credits]
        }

    def _get_series_detail(self, db: Session, user_id: int, series_core_id: int, cast: Optional[List[Dict]] = None, genres: Optional[List[str]] = None) -> Dict[str, Any]:
        """获取系列-季-集的详细信息（仅在季下嵌套版本，集元数据不变）"""
        # 1. 查询系列核心和扩展信息
        core = db.exec(select(MediaCore).where(and_(MediaCore.id == series_core_id, MediaCore.user_id == user_id))).first()
        if not core:
            return {}
        series_ext = db.exec(select(SeriesExt).where(SeriesExt.core_id == core.id)).first()

        # 2. 第一步：查询core_id系列下所有季扩展（基础季数据，季核心）
        seasons = db.exec(
            select(SeasonExt)
            .where(SeasonExt.series_core_id == series_core_id) 
            .order_by(SeasonExt.season_number)
        ).all()

        # 3. 第二步：批量查询季核心对应的季版本（scope=season_group）
        season_core_ids = [s[0].id for s in seasons]
        season_versions = db.exec(
            select(MediaVersion)
            .where(
                and_(
                    MediaVersion.user_id == user_id,
                    MediaVersion.core_id.in_(season_core_ids),
                    MediaVersion.scope == "season_group"  # 过滤季版本
                )
            )
            .order_by(MediaVersion.preferred.desc(), MediaVersion.created_at.desc())  # 首选版本在前
        ).all()
        # 构建：季核心ID → 季版本列表
        season_core_to_versions: Dict[int, List[MediaVersion]] = {sid: [] for sid in season_core_ids}
        season_version_ids = []
        for sv in season_versions:
            season_core_to_versions[sv.core_id].append(sv)
            season_version_ids.append(sv.id)

        # 4. 第三步：批量查询季版本对应的单集子版本（scope=episode_child，parent_version_id=季版本ID）
        episode_versions = []
        if season_version_ids:
            episode_versions = db.exec(
                select(MediaVersion)
                .where(
                    and_(
                        MediaVersion.user_id == user_id,
                        MediaVersion.parent_version_id.in_(season_version_ids),
                        MediaVersion.scope == "episode_child"  # 过滤单集子版本
                    )
                )
            ).all()

    
        # 构建：季版本ID → 单集子版本列表 + 收集单集核心ID和版本关联
        season_version_to_ep_versions: Dict[int, List[MediaVersion]] = {svid: [] for svid in season_version_ids}
        ep_version_to_core: Dict[int, int] = {}  # 单集子版本ID → 单集核心ID
        episode_core_ids = []
        for ev in episode_versions:
            season_version_to_ep_versions[ev.parent_version_id].append(ev)
            ep_version_to_core[ev.id] = ev.core_id
            episode_core_ids.append(ev.core_id)

        # 5. 第四步：批量查询单集核心+单集扩展（集元数据，保持原有逻辑）
        episode_core_ext_map: Dict[int, tuple[MediaCore, EpisodeExt]] = {}
        if episode_core_ids:
            episode_data = db.exec(
                select(MediaCore, EpisodeExt)
                .join(EpisodeExt, EpisodeExt.core_id == MediaCore.id)
                .where(and_(MediaCore.user_id == user_id, MediaCore.id.in_(episode_core_ids)))
            ).all()
            episode_core_ext_map = {e_core.id: (e_core, e_ext) for e_core, e_ext in episode_data}

        # 6. 第五步：批量查询单集子版本关联的文件资产（FileAsset.version_id=子版本ID）
        asset_map: Dict[int, List[FileAsset]] = {}  # 单集子版本ID → 文件资产列表
        storage_map: Dict[int, str] = {}  # 存储ID → 存储名称（批量查询）
        if episode_versions:
            ep_version_ids = [ev.id for ev in episode_versions]
            # 批量查询文件资产
            all_assets = db.exec(
                select(FileAsset)
                .where(and_(FileAsset.user_id == user_id, FileAsset.version_id.in_(ep_version_ids)))
            ).all()
            for a in all_assets:
                if a.version_id not in asset_map:
                    asset_map[a.version_id] = []
                asset_map[a.version_id].append(a)
                # 收集存储ID用于批量查询
                if a.storage_id and a.storage_id not in storage_map:
                    storage_map[a.storage_id] = ""

            # 批量查询存储名称（优化：避免N+1）
            if storage_map:
                storage_configs = db.exec(select(StorageConfig).where(StorageConfig.id.in_(storage_map.keys()))).all()
                for st in storage_configs:
                    storage_map[st.id] = st.name

        # 7. 构建最终结果：保留原有结构，仅在季下新增version数组
        series_poster = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
        enriched_seasons = []

        for s_core, s_ext in seasons:
            # 原有季核心数据（保持不变）
            r = getattr(s_ext, "runtime", None) or (getattr(series_ext, "episode_run_time", None) if series_ext else None)
            ov = getattr(s_ext, "overview", None) or (getattr(series_ext, "overview", None) if series_ext else None) or s_core.plot
            rtg = getattr(s_ext, "rating", None) or (getattr(series_ext, "rating", None) if series_ext else None)
            season_cast = self._get_cast(db, user_id, s_core.id) or cast

            # 构建季版本列表（核心新增部分）
            season_versions_list = season_core_to_versions.get(s_core.id, [])
            enriched_versions = []
            for season_version in season_versions_list:
                # 获取该季版本下的单集子版本
                ep_versions_list = season_version_to_ep_versions.get(season_version.id, [])
                # 构建该版本下的集列表
                enriched_eps = []
                for ep_version in ep_versions_list:
                    # 获取单集核心+扩展元数据
                    ep_core_id = ep_version_to_core.get(ep_version.id)
                    ep_core_ext = episode_core_ext_map.get(ep_core_id)
                    if not ep_core_ext:
                        continue
                    e_core, e_ext = ep_core_ext

                    # 构建集的资产列表
                    e_assets_list = asset_map.get(ep_version.id, [])
                    e_assets_dicts = [{
                        "file_id": asset.id,
                        "path": asset.full_path,
                        "size": asset.size,
                        "size_text": self._to_human_size(asset.size),
                        "storage": asset.storage_id,
                        # 可选：补充存储名称（如果需要）
                        "storage_name": storage_map.get(asset.storage_id, None)
                    } for asset in e_assets_list]

                    # 集元数据保持与原结构一致
                    enriched_eps.append({
                        "id": e_core.id,
                        "episode_number": e_ext.episode_number,
                        "title": e_core.title,
                        "still_path": getattr(e_ext, "still_path", None),
                        "assets": e_assets_dicts
                    })

                # 按集数排序
                enriched_eps.sort(key=lambda x: x["episode_number"])
                # 季版本属性（按需求定义）
                # 解析dirpath：从版本标签或文件路径中提取（此处使用季版本的tags和存储信息示例）
                dirpath = self._get_season_version_dirpath(season_version)
                storage_name = storage_map.get(next(iter(storage_map.keys()), None), "未知存储") if storage_map else "未知存储"

                enriched_versions.append({
                    "id": season_version.id,
                    "version_tags": season_version.tags,
                    "dirpath": dirpath,
                    "storage_name": storage_name,
                    "episode_count": len(enriched_eps),
                    "episodes": enriched_eps
                })

            # 组装季数据（原有字段 + 新增version数组）
            enriched_seasons.append({
                "id": s_core.id,
                "season_number": s_ext.season_number,
                "title": s_core.title,
                "air_date": s_ext.aired_date.isoformat() if s_ext.aired_date else None,
                "cover": getattr(s_core, "display_poster_path", None) or getattr(s_ext, "poster_path", None),
                "cast": season_cast,
                "overview": ov,
                "rating": rtg,
                "runtime": r,
                "runtime_text": self._runtime_text(r),
                # 核心新增：季版本列表
                "version": enriched_versions,
                # 原有episodes字段保留（若前端不需要，可删除；此处保留兼容）
                "episodes": []
            })

        # 最终返回结构（与原结构一致，仅seasons下新增version字段）
        release_date = getattr(series_ext, "aired_date", None).isoformat() if (series_ext and getattr(series_ext, "aired_date", None)) else None
        result = {
            "id": core.id,
            "title": core.title,
            "poster_path": series_poster,
            "backdrop_path": getattr(series_ext, "backdrop_path", None) if series_ext else None,
            "rating": getattr(series_ext, "rating", None) if series_ext else None,
            "release_date": release_date,
            "overview": getattr(series_ext, "overview", None) or core.plot,
            "genres": genres or [],
            "versions": None,
            "cast": cast or [],
            "media_type": "tv",
            "runtime": getattr(series_ext, "episode_run_time", None) if series_ext else None,
            "runtime_text": self._runtime_text(getattr(series_ext, "episode_run_time", None) if series_ext else None),
            "season_count": getattr(series_ext, "season_count", None) if series_ext else None,
            "episode_count": getattr(series_ext, "episode_count", None) if series_ext else None,
            "seasons": enriched_seasons,
            "directors": None,
            "writers": None
        }

        return result
   
    def _get_series_detail1(self, db: Session, user_id: int, series_core_id: int) -> Dict[str, Any]:
        """获取系列-季-集的详细信息（仅在季下嵌套版本，集元数据不变）"""
        # 1. 查询系列核心和扩展信息
        core = db.exec(select(MediaCore).where(and_(MediaCore.id == series_core_id, MediaCore.user_id == user_id))).first()
        
        
        if not core:
            return {}
        
        genres = self._get_genres(db, user_id, core.id)
        cast = self._get_cast(db, user_id, core.id)

        series_ext = db.exec(select(SeriesExt).where(SeriesExt.core_id == core.id)).first()

        # 2. 第一步：查询core_id系列下所有季扩展（基础季数据，季核心）
        seasons = db.exec(
            select(SeasonExt)
            .where(SeasonExt.series_core_id == series_core_id) 
            .order_by(SeasonExt.season_number)
        ).all()
        enriched_seasons = []

        for season in seasons:
            season_versions_list = []
            season_core_id = season.core_id
            season_versions = db.exec(
                select(MediaVersion)
                .where(MediaVersion.core_id == season_core_id,MediaVersion.scope == "season_group",MediaVersion.user_id == user_id  )
            ).all()
            
            for season_version in season_versions:
                episodes_list=[]
                episodes_ext=db.exec(
                    select(EpisodeExt)
                    .join(MediaVersion,EpisodeExt.core_id == MediaVersion.core_id)
                    .where(EpisodeExt.season_core_id == season_core_id,EpisodeExt.user_id == user_id ,MediaVersion.parent_version_id == season_version.id)
                    .order_by(EpisodeExt.episode_number)
                ).all()

                for episode_item in episodes_ext:
                    assert_list=[]
                    assets = db.exec(
                        select(FileAsset)
                        .join(MediaVersion,FileAsset.core_id == MediaVersion.core_id)
                        .where(FileAsset.core_id == episode_item.core_id,FileAsset.season_version_id == season_version.id)
                        .order_by(MediaVersion.preferred.desc(),MediaVersion.created_at.desc())
                    ).all()
                    if assets:
                        assert_list.append({
                            "file_id": asset.id,
                            "path": asset.full_path,
                            "size": asset.size,
                            "size_text": self._to_human_size(asset.size),
                            "language": getattr(asset, "language", None),
                            "storage": self._get_storage_info(db, getattr(asset, "storage_id", None)),
                        } for asset in assets)
                   

                    episodes_list.append({
                        "id": episode_item.core_id,
                        "episode_number": episode_item.episode_number,
                        "title": episode_item.title,
                        "still_path": getattr(episode_item, "still_path", None),
                        "assets": assert_list
                    })


                
                season_versions_list.append({
                    "id": season_version.id,
                    "version_tags": season_version.tags,
                    "season_version_path": getattr(season_version, "season_version_path", None),
                    "storage_name": getattr(season_version, "storage_name", None),
                    "episode_count": len(episodes_list),# 版本中的集数
                    "episodes": episodes_list
                })
                

            enriched_seasons.append({
                "id": season.core_id,
                "season_number": season.season_number,
                "title": season.title,
                "air_date": season.first_aired.isoformat() if season.first_aired else None,
                "cover": getattr(season, "poster_path", None),
                "overview": season.overview,
                "rating": season.rating,
                "episode_count": len(season.episodes),# 刮削到的集总数量，具体数量在版本中
                "versions": season_versions_list,
            })

        series_poster = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
        result = {
            "id": core.id,
            "title": core.title,
            "poster_path": series_poster,
            "backdrop_path": getattr(series_ext, "backdrop_path", None) if series_ext else None,
            "rating": getattr(series_ext, "rating", None) if series_ext else None,
            "release_date": getattr(series_ext, "aired_date", None).isoformat() if (series_ext and getattr(series_ext, "aired_date", None)) else None,
            "overview": getattr(series_ext, "overview", None) or core.plot,
            "genres": genres,
            "versions": None,
            "cast": cast,
            "media_type": "tv",
            "runtime": getattr(series_ext, "episode_run_time", None) if series_ext else None,
            "runtime_text": self._runtime_text(getattr(series_ext, "episode_run_time", None) if series_ext else None),
            "season_count": getattr(series_ext, "season_count", None) if series_ext else None,
            "episode_count": getattr(series_ext, "episode_count", None) if series_ext else None,
            "seasons": enriched_seasons,
            "directors": None,
            "writers": None,
        }

        return result


    def _get_series_detail2(self, db: Session, user_id: int, series_core_id: int) -> Dict[str, Any]:
        """获取系列-季-集的详细信息（优化版：批量查询+修复所有已知问题）"""
        # 1. 查询系列核心和扩展信息
        core = db.exec(select(MediaCore).where(and_(MediaCore.id == series_core_id, MediaCore.user_id == user_id))).first()
        if not core:
            logger.warning(f"Series core {series_core_id} not found for user {user_id}")
            return {"error": "series_not_found"}

        genres = self._get_genres(db, user_id, core.id)
        cast = self._get_cast(db, user_id, core.id)
        series_ext = db.exec(select(SeriesExt).where(SeriesExt.core_id == core.id)).first()

        # 2. 批量查询：所有季（MediaCore + SeasonExt）
        seasons = db.exec(
            select(MediaCore, SeasonExt)
            .join(SeasonExt, SeasonExt.core_id == MediaCore.id)
            .where(and_(MediaCore.user_id == user_id, SeasonExt.series_core_id == series_core_id))
            .order_by(SeasonExt.season_number)
        ).all()

        enriched_seasons = []
        if seasons:
            # 补充：批量查询每个季的总集数（修复 episode_count_map 未定义问题）
            season_core_ids = [s_core.id for s_core, s_ext in seasons]
            episode_count_map = {}
            if season_core_ids:
                # 查询每个季下的单集总数（从 EpisodeExt 统计）
                episode_counts = db.exec(
                    select(EpisodeExt.season_core_id, func.count(EpisodeExt.id))
                    .where(EpisodeExt.season_core_id.in_(season_core_ids))
                    .group_by(EpisodeExt.season_core_id)
                ).all()
                episode_count_map = {sid: cnt for sid, cnt in episode_counts}

            # 3. 批量查询：所有季的版本（season_group）
            season_versions = db.exec(
                select(MediaVersion)
                .where(and_(
                    MediaVersion.user_id == user_id,
                    MediaVersion.core_id.in_(season_core_ids),
                    MediaVersion.scope == "season_group"
                ))
            ).all()
            # 构建映射：季 core_id → 季版本列表
            season_core_to_versions = {sid: [] for sid in season_core_ids}
            for sv in season_versions:
                season_core_to_versions[sv.core_id].append(sv)

            # 4. 批量查询：所有季版本对应的单集版本（episode_child）
            season_version_ids = [sv.id for sv in season_versions]
            episode_versions = []
            if season_version_ids:
                episode_versions = db.exec(
                    select(MediaVersion)
                    .where(and_(
                        MediaVersion.user_id == user_id,
                        MediaVersion.parent_version_id.in_(season_version_ids),
                        MediaVersion.scope == "episode_child"
                    ))
                ).all()
            # 构建映射：季版本 id → 单集版本列表；单集版本 id → 单集 core_id
            season_version_to_ep_versions = {svid: [] for svid in season_version_ids}
            ep_version_to_core_id = {}
            for ev in episode_versions:
                season_version_to_ep_versions[ev.parent_version_id].append(ev)
                ep_version_to_core_id[ev.id] = ev.core_id

            # 5. 批量查询：所有单集（MediaCore + EpisodeExt）
            episode_core_ids = list(ep_version_to_core_id.values())
            episode_core_ext_map = {}
            if episode_core_ids:
                episodes_data = db.exec(
                    select(MediaCore, EpisodeExt)
                    .join(EpisodeExt, EpisodeExt.core_id == MediaCore.id)
                    .where(and_(MediaCore.user_id == user_id, MediaCore.id.in_(episode_core_ids)))
                ).all()
                episode_core_ext_map = {e_core.id: (e_core, e_ext) for e_core, e_ext in episodes_data}

            # 6. 批量查询：所有单集版本对应的资产（FileAsset）
            ep_version_ids = [ev.id for ev in episode_versions]
            ep_version_to_assets = {}
            storage_id_to_name = {}
            if ep_version_ids:
                # 批量查资产
                all_assets = db.exec(
                    select(FileAsset)
                    .where(and_(
                        FileAsset.user_id == user_id,
                        FileAsset.version_id.in_(ep_version_ids),  # 资产关联单集版本
                        FileAsset.season_version_id.in_(season_version_ids)  # 双重校验：关联季版本
                    ))
                ).all()
                for asset in all_assets:
                    if asset.version_id not in ep_version_to_assets:
                        ep_version_to_assets[asset.version_id] = []
                    ep_version_to_assets[asset.version_id].append(asset)
                    # 收集存储 id，用于批量查存储名称
                    if asset.storage_id and asset.storage_id not in storage_id_to_name:
                        storage_id_to_name[asset.storage_id] = ""

                # 批量查存储名称（避免调用 _get_storage_info 时的 N+1）
                if storage_id_to_name:
                    storage_configs = db.exec(select(StorageConfig).where(StorageConfig.id.in_(storage_id_to_name.keys()))).all()
                    for st in storage_configs:
                        storage_id_to_name[st.id] = st.name

            # 7. 组装季数据（循环内无查询，仅用映射表）
            enriched_seasons = []
            for s_core, s_ext in seasons:
                # 7.1 获取当前季的版本列表
                current_season_versions = season_core_to_versions.get(s_core.id, [])
                season_versions_list = []

                for season_version in current_season_versions:
                    # 7.2 获取当前季版本下的单集版本列表
                    current_ep_versions = season_version_to_ep_versions.get(season_version.id, [])
                    episodes_list = []

                    for ep_version in current_ep_versions:
                        # 7.3 获取单集核心+扩展信息
                        ep_core_id = ep_version_to_core_id.get(ep_version.id)
                        ep_core_ext = episode_core_ext_map.get(ep_core_id)
                        if not ep_core_ext:
                            continue
                        ep_core, ep_ext = ep_core_ext

                        # 7.4 获取单集资产列表
                        current_assets = ep_version_to_assets.get(ep_version.id, [])
                        asset_list = [
                            {
                                "file_id": asset.id,
                                "path": asset.full_path,
                                "size": asset.size,
                                "size_text": self._to_human_size(asset.size),
                                "language": getattr(asset, "language", None),
                                "storage": self._get_storage_info(db, asset.storage_id),
                                # "storage_name": storage_id_to_name.get(asset.storage_id, "未知存储")
                            }
                            for asset in current_assets
                        ]

                        # 7.5 组装单集数据
                        episodes_list.append({
                            "id": ep_core.id,
                            "episode_number": ep_ext.episode_number,
                            "title": ep_core.title,
                            "still_path": getattr(ep_ext, "still_path", None),
                            "assets": asset_list
                        })
                        # ========== 核心修复：按 episode_number 升序排序 ==========
                        episodes_list.sort(key=lambda x: x["episode_number"])
                        # ======================================================

                    # 7.6 组装季版本数据（含存储名称）- 修复 sample_asset·                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              · 索引错误
                    storage_name = "未知存储"
                    if current_ep_versions:
                        first_ep_version_id = current_ep_versions[0].id
                        first_assets = ep_version_to_assets.get(first_ep_version_id, [])
                        if first_assets:
                            sample_asset = first_assets[0]
                            storage_name = storage_id_to_name.get(sample_asset.storage_id, "未知存储")

                    season_versions_list.append({
                        "id": season_version.id,
                        "version_tags": season_version.tags,
                        "season_version_path": getattr(season_version, "season_version_path", None),
                        "storage_name": storage_name,
                        "episode_count": len(episodes_list),
                        "episodes": episodes_list
                    })

                # 7.7 组装季数据（含总集数）- 修复 episode_count_map 未定义
                total_episode_count = episode_count_map.get(s_core.id, 0)
               
                r=getattr(s_ext, "runtime", None) or (getattr(series_ext, "episode_run_time", None) if series_ext else None)
                enriched_seasons.append({
                    "id": s_core.id,
                    "season_number": s_ext.season_number,
                    "title": s_ext.title or series_ext.title,
                    "air_date": s_ext.aired_date.isoformat() if s_ext.aired_date else None,
                    "cover": getattr(s_core, "display_poster_path", None) or getattr(s_ext, "poster_path", None),
                    "overview": s_ext.overview or series_ext.overview,
                    "rating": s_ext.rating or getattr(series_ext, "rating", None),
                    "episode_count": s_ext.episode_count or total_episode_count,
                    "cast": self._get_cast(db, user_id, s_core.id) or cast,
                    "runtime": r,
                    "runtime_text": self._runtime_text(r),
                    "versions": season_versions_list,  # 若需求是单数 "version"，可改为 "version": season_versions_list
                })

        # 8. 组装最终结果（补充异常处理）
        series_poster = getattr(core, "display_poster_path", None) or (getattr(series_ext, "poster_path", None) if series_ext else None)
        release_date = None
        if series_ext and hasattr(series_ext, "aired_date") and series_ext.aired_date:
            try:
                release_date = series_ext.aired_date.isoformat()
            except Exception as e:
                logger.warning(f"Failed to format series air date: {e}")
                release_date = str(series_ext.aired_date)

        # 计算总集数（从各季的 episode_count 求和）
        total_episode_count = sum([s["episode_count"] for s in enriched_seasons]) if enriched_seasons else 0
        # 计算季数
        season_count = len(enriched_seasons) if enriched_seasons else getattr(series_ext, "season_count", 0)

        result = {
            "id": core.id,
            "title": core.title,
            "poster_path": series_poster,
            "backdrop_path": getattr(series_ext, "backdrop_path", None) if series_ext else None,
            "rating": getattr(series_ext, "rating", None) if series_ext else None,
            "release_date": release_date,
            # "overview": getattr(series_ext, "overview", None) or core.plot,
            "genres": genres,
            # "versions": None,
            # "cast": cast,
            "media_type": "series",
            
            "season_count": getattr(series_ext, "season_count", 0) or season_count,
            "episode_count": getattr(series_ext, "episode_count", 0) or total_episode_count,
            "seasons": enriched_seasons,
            # "directors": None,
            # "writers": None,
        }

        return result


# "season":[
#     {
#         "id": 1,
#         "season_number": 1,
#         "title": "第一季",
#         .....
#         "version": [
#             {
#                 "id": 1,
#                 "version_tags": 1251262,
#                 "season_version_path": "第一季第1版",
#                 "storage_name": "2023-09-01",
#                 "episode_count": 60,
#                 "episodes": [
#                     {
#                         "id": 93,
#                         "episode_number": 1,
#                         "title": "李善德被做局接运荔枝死差",
#                         "still_path": "https://image.tmdb.org/t/p/w500/cYkgj88MbQy4FDuIikWDd9t9z19.jpg",
#                         "assets": [
#                             {
#                                 "file_id": asset.id,
#                                 "path": asset.full_path,
#                                 "size": asset.size,
#                                 "size_text": self._to_human_size(asset.size),
#                                 "storage": asset.storage_id,
#                             }
#                         ]
#                     },
#                     {
#                         ....
#                     },
#                 ]
#             },
#             {
#                 "id": 2,
#                 "version_tags": 155651262,
#                 "season_version_path": "第一季第2版",
#                 "storage_name": "2023-09-01",
#                 "episode_count": 2,
#                 "episodes": [
#                     {
#                         "id": 93,
#                         "episode_number": 1,
#                         "title": "李善德被做局接运荔枝死差",
#                         "still_path": "https://image.tmdb.org/t/p/w500/cYkgj88MbQy4FDuIikWDd9t9z19.jpg",
#                         "assets": [
#                             {
#                                 "file_id": asset.id,
#                                 "path": asset.full_path,
#                                 "size": asset.size,
#                                 "size_text": self._to_human_size(asset.size),
#                                 "storage": asset.storage_id,
#                             }
#                         ]
#                     },
#                     {
#                         ....
#                     },
#                 ]
#             },

#         ]
       
        
#     }
# ]