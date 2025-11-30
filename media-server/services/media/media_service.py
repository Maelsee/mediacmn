from __future__ import annotations

from typing import Optional, Dict, Any, List
from venv import logger

from sqlmodel import Session, select, func
from sqlalchemy import and_, or_

from models.media_models import MediaCore
from models.media_models import MovieExt, MediaVersion
from models.media_models import TVSeriesExt, SeasonExt, EpisodeExt
from models.media_models import FileAsset
from models.media_models import Artwork
from models.media_models import ExternalID
from models.media_models import Genre, MediaCoreGenre
from models.media_models import Person, Credit
from models.storage_models import StorageConfig
from services.media.metadata_persistence_service import MetadataPersistenceService


class MediaService:
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
        st = db.exec(select(StorageConfig).where(StorageConfig.id == storage_id)).first()
        if not st:
            return None
        return {"id": st.id, "name": st.name, "type": st.storage_type}
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
        # 流派card 10条
        genre_rows = db.exec(
            select(Genre)
            # .join(MediaCoreGenre, MediaCoreGenre.genre_id == Genre.id)
            .where(Genre.user_id == user_id)
            .order_by(Genre.name)
            .limit(10)
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
        series_rows = db.exec(
            select(MediaCore, TVSeriesExt)
            .join(TVSeriesExt, TVSeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "tv_series"))
            .order_by(MediaCore.updated_at.desc())
            .limit(10)
        ).all()
        series_cards: List[Dict[str, Any]] = []
        for core, tv_ext in series_rows:
            released = None
            rd = getattr(core, "display_date", None)
            if rd:
                try:
                    released = rd.isoformat()
                except Exception:
                    released = rd
            poster_url2 = getattr(core, "display_poster_path", None) or (getattr(tv_ext, "poster_path", None) if tv_ext else None)
            series_cards.append({
                "id": core.id,
                "name": core.title,
                "cover_url": poster_url2,
                "rating": getattr(core, "display_rating", None) or (getattr(tv_ext, "rating", None) if tv_ext else None),
                "release_date": released,
                "media_type": "tv",
            })

        return {"genres": genre_cards, "movie": movie_cards, "tv": series_cards}

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
        stmt = select(MediaCore).where(and_(MediaCore.user_id == user_id, MediaCore.kind.in_(["movie", "tv_series"])))
        if type_filter:
            if type_filter == "movie":
                stmt = stmt.where(MediaCore.kind == "movie")
            elif type_filter in ("tv", "tv_series"):
                stmt = stmt.where(MediaCore.kind == "tv_series")
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
        tv_exts = {}
        if core_ids:
            m_exts = db.exec(select(MovieExt).where(MovieExt.core_id.in_(core_ids))).all()
            for m in m_exts:
                movie_exts[m.core_id] = m
            
            t_exts = db.exec(select(TVSeriesExt).where(TVSeriesExt.core_id.in_(core_ids))).all()
            for t in t_exts:
                tv_exts[t.core_id] = t

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
            elif core.kind == "tv_series":
                tv_ext = tv_exts.get(core.id)
                if tv_ext:
                    rating = getattr(core, "display_rating", None) or getattr(tv_ext, "rating", None)
                    poster = getattr(core, "display_poster_path", None) or getattr(tv_ext, "poster_path", None)
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
            "tv": db.exec(select(func.count()).where(MediaCore.user_id == user_id, MediaCore.kind == "tv_series")).one(),
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
            
            # Use poster/backdrop logic
            poster = getattr(core, "display_poster_path", None) or (getattr(movie_ext, "poster_path", None) if movie_ext else None)
            backdrop_url = getattr(movie_ext, "backdrop_path", None) if movie_ext else None
            backdrop_url = backdrop_url or poster
            
            return {
                "id": core.id,
                "title": core.title,
                "poster_path": poster,
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
            tv_ext = db.exec(select(TVSeriesExt).where(TVSeriesExt.core_id == core.id)).first()
            
            # Optimized Season/Episode fetching
            # 1. Fetch all seasons
            seasons = db.exec(
                select(MediaCore, SeasonExt)
                .join(SeasonExt, SeasonExt.core_id == MediaCore.id)
                .where(and_(MediaCore.user_id == user_id, SeasonExt.series_core_id == core.id))
                .order_by(SeasonExt.season_number)
            ).all()
            
            season_ids = [s[0].id for s in seasons]
            
            # 2. Fetch all episodes for these seasons
            episodes_data = []
            if season_ids:
                episodes_data = db.exec(
                    select(MediaCore, EpisodeExt)
                    .join(EpisodeExt, EpisodeExt.core_id == MediaCore.id)
                    .where(and_(MediaCore.user_id == user_id, EpisodeExt.season_core_id.in_(season_ids)))
                    .order_by(EpisodeExt.episode_number)
                ).all()
            
            # Group episodes by season
            episodes_map = {} # season_core_id -> list of episode tuples
            episode_core_ids = []
            for e_core, e_ext in episodes_data:
                sid = e_ext.season_core_id
                if sid not in episodes_map:
                    episodes_map[sid] = []
                episodes_map[sid].append((e_core, e_ext))
                episode_core_ids.append(e_core.id)

            # 3. Fetch all assets for these episodes (to avoid N+1 in _get_episode_assets)
            assets_map = {} # episode_core_id -> list of assets
            if episode_core_ids:
                all_assets = db.exec(
                    select(FileAsset).where(and_(FileAsset.user_id == user_id, FileAsset.core_id.in_(episode_core_ids)))
                ).all()
                for a in all_assets:
                    if a.core_id not in assets_map:
                        assets_map[a.core_id] = []
                    assets_map[a.core_id].append(a)

            # Build result
            series_poster = getattr(core, "display_poster_path", None) or (getattr(tv_ext, "poster_path", None) if tv_ext else None)
            
            enriched_seasons = []
            for s_core, s_ext in seasons:
                # Build episodes list
                season_eps = episodes_map.get(s_core.id, [])
                enriched_eps = []
                for e_core, e_ext in season_eps:
                    e_assets_list = assets_map.get(e_core.id, [])
                    # Normalize assets
                    e_assets_dicts = [{
                        "file_id": asset.id,
                        "path": asset.full_path,
                        "size": asset.size,
                        "size_text": self._to_human_size(asset.size),
                        "language": getattr(asset, "language", None),
                        "storage": self._get_storage_info(db, getattr(asset, "storage_id", None)),
                    } for asset in e_assets_list]

                    enriched_eps.append({
                        "id": e_core.id,
                        "episode_number": e_ext.episode_number,
                        "title": e_core.title,
                        "still_path": getattr(e_ext, "still_path", None),
                        "assets": e_assets_dicts
                    })

                r = getattr(s_ext, "runtime", None) or (getattr(tv_ext, "episode_run_time", None) if tv_ext else None)
                ov = getattr(s_ext, "overview", None) or (getattr(tv_ext, "overview", None) if tv_ext else None) or s_core.plot
                rtg = getattr(s_ext, "rating", None) or (getattr(tv_ext, "rating", None) if tv_ext else None)
                enriched_seasons.append({
                    "id": s_core.id,
                    "season_number": s_ext.season_number,
                    "title": s_core.title,
                    "air_date": s_ext.aired_date.isoformat() if s_ext.aired_date else None,
                    "cover": getattr(s_core, "display_poster_path", None) or getattr(s_ext, "poster_path", None),
                    "cast": self._get_cast(db, user_id, s_core.id) or cast,
                    "overview": ov,
                    "rating": rtg,
                    "runtime": r,
                    "runtime_text": self._runtime_text(r),
                    "episodes": enriched_eps,
                })

            return {
                "id": core.id,
                "title": core.title,
                "poster_path": series_poster,
                "backdrop_path": getattr(tv_ext, "backdrop_path", None) if tv_ext else None,
                "rating": getattr(tv_ext, "rating", None) if tv_ext else None,
                "release_date": getattr(tv_ext, "aired_date", None).isoformat() if (tv_ext and getattr(tv_ext, "aired_date", None)) else None,
                "overview": getattr(tv_ext, "overview", None) or core.plot,
                "genres": genres,
                "versions": None,
                "cast": cast,
                "media_type": "tv",
                "runtime": getattr(tv_ext, "episode_run_time", None) if tv_ext else None,
                "runtime_text": self._runtime_text(getattr(tv_ext, "episode_run_time", None) if tv_ext else None),
                "season_count": getattr(tv_ext, "season_count", None) if tv_ext else None,
                "episode_count": getattr(tv_ext, "episode_count", None) if tv_ext else None,
                "seasons": enriched_seasons,
                "directors": None,
                "writers": None,
            }
    
    def _get_genres(self, db: Session, user_id: int, core_id: int) -> List[str]:
        genres = db.exec(
            select(Genre.name)
            .join(MediaCoreGenre, MediaCoreGenre.genre_id == Genre.id)
            .where(
                and_(
                    MediaCoreGenre.core_id == core_id,
                    Genre.user_id == user_id
                )
            )
        ).all()
        return list(genres)

    def _get_cast(self, db: Session, user_id: int, core_id: int) -> List[Dict[str, Any]]:
        """获取演员列表。"""
        # Optimized to select all needed fields in one query
        people = db.exec(
            select(Person.name, Person.tmdb_id, Credit.character, Person.profile_url)
            .join(Credit, Credit.person_id == Person.id)
            .where(and_(
                Person.user_id == user_id,
                Credit.core_id == core_id,
                Credit.role == "cast"
            ))
        ).all()
        return [{"name": name, "character": character, "image_url": purl} for name, tmdb_id, character, purl in people]
    
    def _get_crew(self, db: Session, user_id: int, core_id: int, job: str) -> List[Dict[str, Any]]:
        people = db.exec(
            select(Person.name, Person.tmdb_id, Credit.character, Person.profile_url)
            .join(Credit, Credit.person_id == Person.id)
            .where(and_(
                Person.user_id == user_id,
                Credit.core_id == core_id,
                Credit.job == job
            ))
        ).all()
        return [{"name": name, "character": character, "image_url": purl} for name, tmdb_id, character, purl in people]

    def _get_movie_versions(self, db: Session, user_id: int, core_id: int) -> List[Dict[str, Any]]:
        """获取电影版本信息。"""
        versions = db.exec(
            select(MediaVersion).where(
                and_(
                    MediaVersion.user_id == user_id,
                    MediaVersion.core_id == core_id
                )
            )
        ).all()
        
        # Optimize: bulk fetch assets for all versions
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

    # Removed _get_seasons, _get_episodes, _get_episode_assets as they are now integrated into get_media_detail
    # Removed _get_primary_artwork, _to_artwork_url if unused (kept _to_human_size etc as helpers)

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
