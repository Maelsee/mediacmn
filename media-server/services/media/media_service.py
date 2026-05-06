from __future__ import annotations

import datetime
from typing import Optional, Dict, Any, List

from core.config import get_settings
import redis.asyncio as redis
import json
from sqlmodel import select, func, and_, or_, case
from sqlmodel.ext.asyncio.session import AsyncSession

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
from services.storage.storage_service import storage_service
from services.media.play_service import PlayService


class MediaService:
    def __init__(self):
        self.CACHE_EXPIRE_SECONDS = 3600
        self._play_service = PlayService(self)
        self._redis = None
        s = get_settings()
        try:
            redis_url = getattr(s, "SCRAPER_CACHE_REDIS_URL", None)
            if redis_url:
                self._redis = redis.from_url(redis_url, db=1, decode_responses=True)
        except Exception as e:
            logger.error(f"MediaService: Redis 初始化失败: {e}", exc_info=True)
            self._redis = None

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
  
    async def _get_storage_info(self, db: AsyncSession, storage_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if not storage_id:
            return None
        cache_key = f"MediaService:storage_sample_info:{storage_id}"
        if self._redis:        
            try:
                cache_data = await self._redis.get(cache_key)
            except Exception as e:
                logger.warning(f"MediaService: 读取存储缓存失败: {e}", exc_info=True)
                cache_data = None
            if cache_data:
                try:
                    return json.loads(cache_data) if cache_data != "null" else None
                except Exception as e:
                    logger.warning(f"MediaService: 解析存储缓存 JSON 失败: {e}", exc_info=True)
        st = (await db.exec(select(StorageConfig).where(StorageConfig.id == storage_id))).first()
        if not st:
            if self._redis:
                try:
                    await self._redis.setex(cache_key, 60, "null")
                except Exception as e:
                    logger.warning(f"MediaService: 写入存储空值缓存失败: {e}", exc_info=True)
            return None
        storage_info = {
            "id": st.id,
            "name": st.name,
            "type": st.storage_type
        }
        if self._redis:
            try:
                await self._redis.setex(cache_key, self.CACHE_EXPIRE_SECONDS, json.dumps(storage_info))
            except Exception as e:
                logger.warning(f"MediaService: 写入存储缓存失败: {e}", exc_info=True)
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
    async def list_media_cards(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> Dict[str, Any]:
        
        # 流派card 10条（修正版：通过中间表关联用户媒体）
        genre_rows = (await db.exec(
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
        )).all()

        genre_cards: List[Dict[str, Any]] = []
        for g in genre_rows:
            genre_cards.append({
                "id": g.id,
                "name": g.name,
            })
        # 电影card 15条
        movie_rows = (await db.exec(
            select(MediaCore, MovieExt)
            .join(MovieExt, MovieExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "movie"))
            .order_by(MediaCore.updated_at.desc())
            .limit(15)
        )).all()
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
        # 剧集card 15条
        tv_rows = (await db.exec(
            select(MediaCore, SeriesExt)
            .join(SeriesExt, SeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "series",MediaCore.subtype == 'TV'))
            .order_by(MediaCore.updated_at.desc())
            .limit(15)
        )).all()
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
        # 动画card 15条
        animation_rows = (await db.exec(
            select(MediaCore, SeriesExt)
            .join(SeriesExt, SeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "series", MediaCore.subtype == 'Animation'))
            .order_by(MediaCore.updated_at.desc()) 
            .limit(15)
        )).all()
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
        # 真人秀card 15条
        reality_rows = (await db.exec(
            select(MediaCore, SeriesExt)
            .join(SeriesExt, SeriesExt.core_id == MediaCore.id, isouter=True)
            .where(and_(MediaCore.user_id == user_id, MediaCore.kind == "series", MediaCore.subtype == 'Reality'))
            .order_by(MediaCore.updated_at.desc())
            .limit(15)
        )).all()
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
    
    async def filter_media_cards(
        self,
        db: AsyncSession,
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

        total = (await db.exec(select(func.count()).select_from(stmt.subquery()))).one()
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
        
        rows = (await db.exec(stmt.offset((page - 1) * page_size).limit(page_size))).all()
        
        # Bulk fetch extensions
        core_ids = [c.id for c in rows]
        movie_exts = {}
        series_exts = {}
        if core_ids:
            m_exts = (await db.exec(select(MovieExt).where(MovieExt.core_id.in_(core_ids)))).all()
            for m in m_exts:
                movie_exts[m.core_id] = m
            
            t_exts = (await db.exec(select(SeriesExt).where(SeriesExt.core_id.in_(core_ids)))).all()
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
            "movie": (await db.exec(select(func.count()).where(MediaCore.user_id == user_id, MediaCore.kind == "movie"))).one(),
            "tv": (await db.exec(select(func.count()).where(MediaCore.user_id == user_id, MediaCore.kind == "series"))).one(),
        }
        return {"page": page, "page_size": page_size, "total": total, "items": items, "type_counts": type_counts}
    
    async def get_media_detail(self, db: AsyncSession, user_id: int, core_id: int) -> Dict[str, Any]:
        core = (await db.exec(select(MediaCore).where(MediaCore.user_id == user_id, MediaCore.id == core_id))).first()
        if not core:
            return {"error": "not_found"}
        
        genres = await self._get_genres(db, user_id, core.id)
        cast = await self._get_cast(db, user_id, core.id)
        
        if core.kind == "movie":
            movie_ext = (await db.exec(select(MovieExt).where(MovieExt.core_id == core.id))).first()
            versions = await self._get_movie_versions(db, user_id, core.id)
            
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
                # "directors": await self._get_crew(db, user_id, core.id, "Director"),
                # "writers": await self._get_crew(db, user_id, core.id, "Writer"),
            }
        else:
            return await self._get_series_detail2(db, user_id, core.id)
   
    async def _get_genres(self, db: AsyncSession, user_id: int, core_id: int) -> List[str]:
        genres = (await db.exec(
            select(Genre.name)
            .join(MediaCoreGenre, MediaCoreGenre.genre_id == Genre.id)
            .where(
                    MediaCoreGenre.core_id == core_id,         
            )
            .distinct()
        )).all()
        return list(genres)

    async def _get_cast(self, db: AsyncSession, user_id: int, core_id: int) -> List[Dict[str, Any]]:
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
        results = (await db.exec(query)).all()
        return [
            {
                "name": name,
                "character": "导演" if person_type == "director" else character,  # 导演固定显示“导演”
                "image_url": profile_url
            }
            for name, character, profile_url, person_type in results
        ]

    async def _get_crew(self, db: AsyncSession, user_id: int, core_id: int, job: str) -> List[Dict[str, Any]]:
        people = (await db.exec(
            select(Person.name, Credit.character, Person.profile_url)
            .join(Credit, Credit.person_id == Person.id)
            .where(and_(
                Credit.user_id == user_id,
                Credit.core_id == core_id,
                Credit.job == job
            ))
        )).all()
        return [{"name": name, "character": character, "image_url": purl} for name, character, purl in people]

    async def _get_movie_versions(self, db: AsyncSession, user_id: int, core_id: int) -> List[Dict[str, Any]]:
        """获取电影版本信息。"""
        # 1. 查询电影专属版本（过滤scope，添加排序）
        versions = await db.exec(
            select(MediaVersion)
            .where(
                and_(
                    MediaVersion.user_id == user_id,
                    MediaVersion.core_id == core_id,
                    MediaVersion.scope == "movie_single"  # 过滤电影版本，排除季/剧集版本
                )
            )
            .order_by(MediaVersion.preferred.desc(), MediaVersion.created_at.desc())  # 首选版本在前，最新版本在前
        )
        versions = versions.all()
        
        # 2. 批量获取版本关联的文件资产
        version_ids = [v.id for v in versions]
        assets_map = {}
        if version_ids:
            assets = (await db.exec(
                select(FileAsset).where(
                    and_(
                        FileAsset.user_id == user_id,
                        FileAsset.version_id.in_(version_ids)
                    )
                )
            )).all()
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
                    "file_id": getattr(asset, "id", None),
                    "path": getattr(asset, "full_path", None),
                    "resolution": getattr(asset, "resolution", None),
                    "frame_rate": getattr(asset, "frame_rate", None),
                    # "type": getattr(asset, "asset_role", None) or self._normalize_asset_type(asset),
                    "size": getattr(asset, "size", None),
                    "size_text": self._to_human_size(getattr(asset, "size", None)),
                    "language": getattr(asset, "language", None),
                    "storage": await self._get_storage_info(db, getattr(asset, "storage_id", None)),
                })
            
            result.append({
                "id": getattr(version, "id", None),
                "quality": getattr(version, "quality", None),
                "assets": asset_list,
            })
        
        return result

    async def get_file_subtitles(
        self,
        db: AsyncSession,
        user_id: int,
        asset: FileAsset,
    ) -> Dict[str, Any]:
        return await self._play_service.get_file_subtitles(db=db, user_id=user_id, asset=asset)

    async def download_subtitle_content(
        self,
        db: AsyncSession,
        user_id: int,
        asset: FileAsset,
        subtitle_path: str,
    ) -> str:
        return await self._play_service.download_subtitle_content(db=db, user_id=user_id, asset=asset, subtitle_path=subtitle_path)

    async def get_file_episode_list(
        self,
        db: AsyncSession,
        user_id: int,
        asset: FileAsset,
    ) -> Dict[str, Any]:
        return await self._play_service.get_file_episode_list(db=db, user_id=user_id, asset=asset)

    async def list_media_files(
        self,
        db: AsyncSession,
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
        
        total = (await db.exec(select(func.count()).select_from(query.subquery()))).one()
        files = (await db.exec(
            query.order_by(MediaCore.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).all()
        
        result = []
        for media_core in files:
            assets = (await db.exec(
                select(FileAsset).where(
                    and_(
                        FileAsset.core_id == media_core.id,
                        FileAsset.user_id == user_id
                    )
                )
            )).all()
            
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
    
    async def get_media_file_detail(self, db: AsyncSession, user_id: int, file_id: int) -> Dict[str, Any]:
        """获取媒体文件详细信息"""
        # 获取媒体核心信息
        media_core = (await db.exec(
            select(MediaCore).where(
                and_(
                    MediaCore.id == file_id,
                    MediaCore.user_id == user_id
                )
            )
        )).first()
        
        if not media_core:
            return {"error": "文件不存在"}
        
        # 获取文件资产
        assets = (await db.exec(
            select(FileAsset).where(
                and_(
                    FileAsset.core_id == file_id,
                    FileAsset.user_id == user_id
                )
            )
        )).all()
        
        # 获取元数据信息
        metadata = {}
        if media_core.kind == "movie":
            movie_ext = (await db.exec(select(MovieExt).where(MovieExt.core_id == file_id))).first()
            if movie_ext:
                metadata.update({
                    "tagline": movie_ext.tagline,
                    "runtime": getattr(movie_ext, "runtime", None),
                })
        
        # 获取外部ID
        external_ids = (await db.exec(select(ExternalID).where(ExternalID.core_id == file_id))).all()
        
        # 获取流派
        genres = (await db.exec(
            select(Genre).join(MediaCoreGenre).where(MediaCoreGenre.core_id == file_id)
        )).all()
        
        # 获取制作人员
        credits = (await db.exec(
            select(Person, Credit).join(Credit).where(Credit.core_id == file_id)
        )).all()
        
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

    async def _get_series_detail2(self, db: AsyncSession, user_id: int, series_core_id: int) -> Dict[str, Any]:
        """获取系列-季-集的详细信息（优化版：批量查询+修复所有已知问题）"""
        # 1. 查询系列核心和扩展信息
        core = (await db.exec(select(MediaCore).where(and_(MediaCore.id == series_core_id, MediaCore.user_id == user_id)))).first()
        if not core:
            logger.warning(f"Series core {series_core_id} not found for user {user_id}")
            return {"error": "series_not_found"}

        genres = await self._get_genres(db, user_id, core.id)
        cast = await self._get_cast(db, user_id, core.id)
        series_ext = (await db.exec(select(SeriesExt).where(SeriesExt.core_id == core.id))).first()

        # 2. 批量查询：所有季（MediaCore + SeasonExt）
        seasons = (await db.exec(
            select(MediaCore, SeasonExt)
            .join(SeasonExt, SeasonExt.core_id == MediaCore.id)
            .where(and_(MediaCore.user_id == user_id, SeasonExt.series_core_id == series_core_id))
            .order_by(SeasonExt.season_number)
        )).all()

        enriched_seasons = []
        if seasons:
            # 补充：批量查询每个季的总集数（修复 episode_count_map 未定义问题）
            season_core_ids = [s_core.id for s_core, s_ext in seasons]
            episode_count_map = {}
            if season_core_ids:
                # 查询每个季下的单集总数（从 EpisodeExt 统计）
                episode_counts = (await db.exec(
                    select(EpisodeExt.season_core_id, func.count(EpisodeExt.id))
                    .where(EpisodeExt.season_core_id.in_(season_core_ids))
                    .group_by(EpisodeExt.season_core_id)
                )).all()
                episode_count_map = {sid: cnt for sid, cnt in episode_counts}

            # 3. 批量查询：所有季的版本（season_group）
            season_versions = (await db.exec(
                select(MediaVersion)
                .where(and_(
                    MediaVersion.user_id == user_id,
                    MediaVersion.core_id.in_(season_core_ids),
                    MediaVersion.scope == "season_group"
                ))
            )).all()
            # 构建映射：季 core_id → 季版本列表
            season_core_to_versions = {sid: [] for sid in season_core_ids}
            for sv in season_versions:
                season_core_to_versions[sv.core_id].append(sv)

            # 4. 批量查询：所有季版本对应的单集版本（episode_child）
            season_version_ids = [sv.id for sv in season_versions]
            episode_versions = []
            if season_version_ids:
                episode_versions = (await db.exec(
                    select(MediaVersion)
                    .where(and_(
                        MediaVersion.user_id == user_id,
                        MediaVersion.parent_version_id.in_(season_version_ids),
                        MediaVersion.scope == "episode_child"
                    ))
                )).all()
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
                episodes_data = (await db.exec(
                    select(MediaCore, EpisodeExt)
                    .join(EpisodeExt, EpisodeExt.core_id == MediaCore.id)
                    .where(and_(MediaCore.user_id == user_id, MediaCore.id.in_(episode_core_ids)))
                )).all()
                episode_core_ext_map = {e_core.id: (e_core, e_ext) for e_core, e_ext in episodes_data}

            # 6. 批量查询：所有单集版本对应的资产（FileAsset）
            ep_version_ids = [ev.id for ev in episode_versions]
            ep_version_to_assets = {}
            storage_id_to_name = {}
            if ep_version_ids:
                # 批量查资产
                all_assets = (await db.exec(
                    select(FileAsset)
                    .where(and_(
                        FileAsset.user_id == user_id,
                        FileAsset.version_id.in_(ep_version_ids),
                        FileAsset.season_version_id.in_(season_version_ids)
                    ))
                )).all()
                for asset in all_assets:
                    if asset.version_id not in ep_version_to_assets:
                        ep_version_to_assets[asset.version_id] = []
                    ep_version_to_assets[asset.version_id].append(asset)
                    # 收集存储 id，用于批量查存储名称
                    if asset.storage_id and asset.storage_id not in storage_id_to_name:
                        storage_id_to_name[asset.storage_id] = ""

                # 批量查存储名称（避免调用 _get_storage_info 时的 N+1）
                if storage_id_to_name:
                    storage_configs = (await db.exec(select(StorageConfig).where(StorageConfig.id.in_(storage_id_to_name.keys())))).all()
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
                    episodes_by_core_id: Dict[int, Dict[str, Any]] = {}

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
                                "storage": await self._get_storage_info(db, asset.storage_id),
                                # "storage_name": storage_id_to_name.get(asset.storage_id, "未知存储")
                            }
                            for asset in current_assets
                        ]

                        # 7.5 组装单集数据
                        episode_entry = {
                            "id": ep_core.id,
                            "episode_number": ep_ext.episode_number,
                            "title": ep_core.title,
                            "still_path": getattr(ep_ext, "still_path", None),
                            "assets": asset_list
                        }

                        existing = episodes_by_core_id.get(ep_core.id)
                        if not existing:
                            episodes_by_core_id[ep_core.id] = episode_entry
                            continue

                        if not existing.get("still_path") and episode_entry.get("still_path"):
                            existing["still_path"] = episode_entry["still_path"]
                        if not existing.get("title") and episode_entry.get("title"):
                            existing["title"] = episode_entry["title"]
                        if existing.get("episode_number") is None and episode_entry.get("episode_number") is not None:
                            existing["episode_number"] = episode_entry["episode_number"]

                        if asset_list:
                            existing_assets = existing.get("assets") or []
                            seen_file_ids = {
                                a.get("file_id")
                                for a in existing_assets
                                if isinstance(a, dict) and a.get("file_id") is not None
                            }
                            for a in asset_list:
                                fid = a.get("file_id") if isinstance(a, dict) else None
                                if fid is None or fid in seen_file_ids:
                                    continue
                                existing_assets.append(a)
                                seen_file_ids.add(fid)
                            existing["assets"] = existing_assets

                    episodes_list = list(episodes_by_core_id.values())
                    episodes_list.sort(key=lambda x: (x.get("episode_number") or 0, x.get("id") or 0))

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
                    "cast": await self._get_cast(db, user_id, s_core.id) or cast,
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
