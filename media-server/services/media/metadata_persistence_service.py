import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlmodel import select

from models.media_models import (
    MediaCore, ExternalID, FileAsset, Artwork, Genre, MediaCoreGenre,
    Person, Credit, MovieExt, EpisodeExt, SeasonExt, TVSeriesExt, Collection
)
from services.scraper import (
    ScraperMovieDetail,
    ScraperSeriesDetail,
    ScraperSeasonDetail,
    ScraperEpisodeDetail,
    ScraperSearchResult,
)

logger = logging.getLogger(__name__)


class _DictWrapper:
    """包装器，使 dict 可以通过 getattr 访问，并递归处理嵌套结构"""
    def __init__(self, data: Dict):
        self._data = data if isinstance(data, dict) else {}
    
    def __getattr__(self, name: str):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        value = self._data.get(name)
        return self._wrap_value(value)
    
    def __getitem__(self, index: int):
        """支持列表索引访问"""
        if isinstance(self._data, list):
            return self._wrap_value(self._data[index])
        raise TypeError(f"'{type(self).__name__}' object is not subscriptable")
    
    def _wrap_value(self, value):
        """递归包装嵌套的 dict 和 list"""
        if isinstance(value, dict):
            return _DictWrapper(value)
        elif isinstance(value, list):
            return [self._wrap_value(item) for item in value]
        else:
            return value


class MetadataPersistenceService:
    """
    媒体元数据持久化服务
    """
    def _get_attr(self, obj, key: str, default=None):
        """
        统一的属性访问方法，同时支持 dict 和 dataclass 对象
        
        参数:
            obj: dict 或 dataclass 对象
            key: 属性/键名
            default: 默认值
        返回:
            属性值或默认值
        """
        if isinstance(obj, dict):
            return obj.get(key, default)
        else:
            return getattr(obj, key, default)
    
    def _parse_dt(self, v):
        """
        将日期值解析为 datetime 对象
        
        参数:
            v: 支持 datetime 或 YYYY-MM-DD 字符串
        返回:
            datetime 或 None（解析失败返回 None）
        """
        try:
            from datetime import datetime as _dt
            if isinstance(v, _dt):
                return v
            if isinstance(v, str) and v:
                return _dt.strptime(v[:10], "%Y-%m-%d")
        except Exception:
            return None
        return None
    def _upsert_artworks(self, session, user_id: int, core_id: int, provider: Optional[str], artworks) -> None:
        try:
            if artworks:
                for a in artworks:
                    # 支持 dict 和 dataclass：先尝试 dict.get，再用 getattr
                    a_type = self._get_attr(a, "type")
                    # 处理 Enum 类型：如果是 Enum，取其 value；如果已是字符串，直接使用
                    if hasattr(a_type, "value"):
                        _t = a_type.value
                    else:
                        _t = a_type
                    _t = "still" if _t == "thumb" else _t
                    by_type = session.exec(select(Artwork).filter(
                        Artwork.user_id == user_id,
                        Artwork.core_id == core_id,
                        Artwork.type == _t
                    )).first()
                    if by_type:
                        try:
                            if not getattr(by_type, "remote_url", None):
                                by_type.remote_url = self._get_attr(a, "url")
                        except Exception:
                            by_type.remote_url = self._get_attr(a, "url")
                        by_type.provider = provider
                        by_type.language = self._get_attr(a, "language") or getattr(by_type, "language", None)
                        by_type.preferred = getattr(by_type, "preferred", False)
                        # by_type.exists_remote = True
                    else:
                        session.add(Artwork(user_id=user_id, core_id=core_id, type=_t, remote_url=self._get_attr(a, "url"), local_path=None, provider=provider, language=self._get_attr(a, "language"), preferred=False, exists_local=False))
        except Exception:
            pass
    def _upsert_credits(self, session, user_id: int, core_id: int, credits, provider: Optional[str]) -> None:
        try:
            if credits:
                for c in credits:
                    name = self._get_attr(c, "name")
                    provider_id = self._get_attr(c, "provider_id")

                    if not name:
                        continue
                    person = session.exec(select(Person).filter(Person.provider_id == provider_id, Person.name == name,Person.provider == provider)).first()
                    if not person:
                        purl = self._get_attr(c, "image_url")
                        person = Person(provider=provider, provider_id=provider_id, name=name, profile_url=purl)
                        session.add(person)
                        session.flush()
                    else:
                        try:
                            if not getattr(person, "profile_url", None) and self._get_attr(c, "image_url"):
                                person.profile_url = self._get_attr(c, "image_url")
                        except Exception:
                            pass
                    # 处理 Enum 类型：如果是 Enum，取其 value；如果已是字符串，直接使用
                    c_type = self._get_attr(c, "type")
                    if hasattr(c_type, "value"):
                        role_type = c_type.value
                    else:
                        role_type = c_type
                    role = "cast" if role_type == "actor" else "crew"
                    character = self._get_attr(c, "role") if role == "cast" else None
                    job = role_type 
                    existing = session.exec(select(Credit).filter(
                        Credit.user_id == user_id,
                        Credit.core_id == core_id,
                        Credit.person_id == person.id,
                        Credit.role == role,
                        Credit.job == job
                    )).first()
                    if not existing:
                        session.add(Credit(user_id=user_id, core_id=core_id, person_id=person.id, role=role, character=character, job=job))
        except Exception:
            pass
    def _upsert_genres(self, session, user_id: int, core_id: int, genres) -> None:
        try:
            for genre_name in genres or []:
                if not genre_name:
                    continue
                genre = session.exec(select(Genre).filter(Genre.user_id == user_id, Genre.name == genre_name)).first()
                if not genre:
                    genre = Genre(user_id=user_id, name=genre_name)
                    session.add(genre)
                    session.flush()
                existing_link = session.exec(select(MediaCoreGenre).filter(MediaCoreGenre.user_id == user_id, MediaCoreGenre.core_id == core_id, MediaCoreGenre.genre_id == genre.id)).first()
                if not existing_link:
                    session.add(MediaCoreGenre(user_id=user_id, core_id=core_id, genre_id=genre.id))
        except Exception:
            pass
    def _apply_series_detail(self, session, user_id: int, sd: ScraperSeriesDetail) -> MediaCore:
        name_val = getattr(sd, "name", None) or getattr(sd, "original_name", None) or ""
        year_val = None
        try:
            dt = self._parse_dt(getattr(sd, "first_air_date", None))
            year_val = dt.year if dt else None
        except Exception:
            year_val = None
        series_core = session.exec(select(MediaCore).filter(
            MediaCore.user_id == user_id,
            MediaCore.kind == "tv_series",
            MediaCore.title == name_val
        )).first()
        if not series_core:
            series_core = MediaCore(
                user_id=user_id,
                kind="tv_series",
                title=name_val,
                original_title=getattr(sd, "original_name", None),
                year=year_val,
                plot=getattr(sd, "overview", None),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(series_core)
            session.flush()
        else:
            series_core.kind = "tv_series"
            series_core.title = name_val
            series_core.original_title = getattr(sd, "original_name", None)
            series_core.year = year_val
            series_core.plot = getattr(sd, "overview", None)
            series_core.updated_at = datetime.now()
        try:
            if getattr(sd, "provider", None) and getattr(sd, "series_id", None):
                existing = session.exec(select(ExternalID).filter(
                    ExternalID.user_id == user_id,
                    ExternalID.core_id == series_core.id,
                    ExternalID.source == sd.provider,
                    ExternalID.key == str(sd.series_id)
                )).first()
                if not existing:
                    session.add(ExternalID(user_id=user_id, core_id=series_core.id, source=sd.provider, key=str(sd.series_id)))
                    session.flush()
                series_core.canonical_source = series_core.canonical_source or sd.provider
                series_core.canonical_external_key = series_core.canonical_external_key or str(sd.series_id)
                try:
                    if sd.provider == "tmdb":
                        sid = int(str(sd.series_id)) if str(sd.series_id).isdigit() else None
                        if sid is not None:
                            series_core.canonical_tmdb_id = series_core.canonical_tmdb_id or sid
                except Exception:
                    pass
        except Exception:
            pass
        tv_ext = session.exec(select(TVSeriesExt).filter(TVSeriesExt.core_id == series_core.id, TVSeriesExt.user_id == user_id)).first()
        if not tv_ext:
            tv_ext = TVSeriesExt(user_id=user_id, core_id=series_core.id)
            session.add(tv_ext)
        try:
            tv_ext.overview = getattr(sd, "overview", None) or tv_ext.overview
            tv_ext.season_count = getattr(sd, "number_of_seasons", None)
            tv_ext.episode_count = getattr(sd, "number_of_episodes", None)
            rt = getattr(sd, "episode_run_time", None)
            if isinstance(rt, list) and len(rt) > 0:
                tv_ext.episode_run_time = int(rt[0]) if isinstance(rt[0], (int, float)) else None
            tv_ext.status = getattr(sd, "status", None)
            tv_ext.rating = getattr(sd, "vote_average", None)
            try:
                fd = getattr(sd, "first_air_date", None)
                ld = getattr(sd, "last_air_date", None)
                tv_ext.aired_date = self._parse_dt(fd) if fd else tv_ext.aired_date
                tv_ext.last_aired_date = self._parse_dt(ld) if ld else tv_ext.last_aired_date
            except Exception:
                pass
            tv_ext.poster_path = getattr(sd, "poster_path", None) or tv_ext.poster_path
            tv_ext.backdrop_path = getattr(sd, "backdrop_path", None) or tv_ext.backdrop_path
            if getattr(sd, "raw_data", None):
                tv_ext.raw_data = json.dumps(sd.raw_data, ensure_ascii=False)
        except Exception:
            pass
        try:
            if getattr(tv_ext, "poster_path", None):
                art_p = session.exec(select(Artwork).filter(Artwork.user_id == user_id, Artwork.core_id == series_core.id, Artwork.type == "poster")).first()
                if not art_p:
                    session.add(Artwork(user_id=user_id, core_id=series_core.id, type="poster", remote_url=tv_ext.poster_path, provider=getattr(sd, "provider", None), preferred=True, exists_remote=True))
                else:
                    art_p.remote_url = art_p.remote_url or tv_ext.poster_path
                    art_p.provider = getattr(sd, "provider", None) or getattr(art_p, "provider", None)
                    art_p.preferred = True
                    art_p.exists_remote = True
            if getattr(tv_ext, "backdrop_path", None):
                art_b = session.exec(select(Artwork).filter(Artwork.user_id == user_id, Artwork.core_id == series_core.id, Artwork.type == "backdrop")).first()
                if not art_b:
                    session.add(Artwork(user_id=user_id, core_id=series_core.id, type="backdrop", remote_url=tv_ext.backdrop_path, provider=getattr(sd, "provider", None), preferred=True, exists_remote=True))
                else:
                    art_b.remote_url = art_b.remote_url or tv_ext.backdrop_path
                    art_b.provider = getattr(sd, "provider", None) or getattr(art_b, "provider", None)
                    art_b.preferred = True
                    art_b.exists_remote = True
        except Exception:
            pass
        try:
            self._upsert_genres(session, user_id, series_core.id, getattr(sd, "genres", []) or [])
        except Exception:
            pass
        try:
            self._upsert_artworks(session, user_id, series_core.id, getattr(sd, "provider", None), getattr(sd, "artworks", None))
        except Exception:
            pass
        try:
            self._upsert_credits(session, user_id, series_core.id, getattr(sd, "credits", None), getattr(sd, "provider", None))
        except Exception:
            pass
        return series_core
    def _apply_season_detail(self, session, user_id: int, series_core: Optional[MediaCore], se: ScraperSeasonDetail) -> MediaCore:
        season_num = getattr(se, "season_number", None) or 1
        existing_se = None
        try:
            if series_core:
                existing_se = session.exec(select(SeasonExt).filter(SeasonExt.user_id == user_id, SeasonExt.series_core_id == series_core.id, SeasonExt.season_number == season_num)).first()
        except Exception:
            existing_se = None
        season_core = None
        if existing_se:
            season_core = session.exec(select(MediaCore).filter(MediaCore.id == existing_se.core_id)).first()
        if not season_core:
            season_core = session.exec(select(MediaCore).filter(
                MediaCore.user_id == user_id,
                MediaCore.kind == "tv_season",
                MediaCore.title == f"Season {season_num}"
            )).first()
        if not season_core:
            season_core = MediaCore(user_id=user_id, kind="tv_season", title=f"Season {season_num}", created_at=datetime.now(), updated_at=datetime.now())
            session.add(season_core)
            session.flush()
        se_ext = session.exec(select(SeasonExt).filter(SeasonExt.core_id == season_core.id, SeasonExt.user_id == user_id)).first()
        if not se_ext:
            se_ext = SeasonExt(user_id=user_id, core_id=season_core.id, series_core_id=series_core.id if series_core else None, season_number=season_num)
            session.add(se_ext)
        try:
            se_ext.overview = getattr(se, "overview", None) or se_ext.overview
            se_ext.episode_count = getattr(se, "episode_count", None)
            se_ext.rating = getattr(se, "vote_average", None)
            ad = getattr(se, "air_date", None)
            se_ext.aired_date = self._parse_dt(ad) if ad else se_ext.aired_date
            se_ext.poster_path = getattr(se, "poster_path", None) or se_ext.poster_path
            if getattr(se, "raw_data", None):
                se_ext.raw_data = json.dumps(se.raw_data, ensure_ascii=False)
        except Exception:
            pass
        try:
            if getattr(se_ext, "poster_path", None):
                art_p = session.exec(select(Artwork).filter(Artwork.user_id == user_id, Artwork.core_id == season_core.id, Artwork.type == "poster")).first()
                if not art_p:
                    session.add(Artwork(user_id=user_id, core_id=season_core.id, type="poster", remote_url=se_ext.poster_path, provider=getattr(se, "provider", None), preferred=True, exists_remote=True))
                else:
                    art_p.remote_url = art_p.remote_url or se_ext.poster_path
                    art_p.provider = getattr(se, "provider", None) or getattr(art_p, "provider", None)
                    art_p.preferred = True
                    art_p.exists_remote = True
        except Exception:
            pass
        try:
            if getattr(se, "provider", None) and getattr(se, "season_id", None):
                existing = session.exec(select(ExternalID).filter(
                    ExternalID.user_id == user_id,
                    ExternalID.core_id == season_core.id,
                    ExternalID.source == se.provider,
                    ExternalID.key == str(se.season_id)
                )).first()
                if not existing:
                    session.add(ExternalID(user_id=user_id, core_id=season_core.id, source=se.provider, key=str(se.season_id)))
        except Exception:
            pass
        try:
            self._upsert_artworks(session, user_id, season_core.id, getattr(se, "provider", None), getattr(se, "artworks", None))
        except Exception:
            pass
        try:
            self._upsert_credits(session, user_id, season_core.id, getattr(se, "credits", None), getattr(se, "provider", None))
        except Exception:
            pass
        return season_core
    # 播放链接相关逻辑已移除，直连生成在 routes_media 中实现
    def apply_metadata(self, session, media_file: FileAsset, metadata,metadata_type: str) -> None:
        """
        一次性幂等地将刮削结果写入领域模型，并更新相关扩展信息

        事务说明:
            - 本方法内部仅执行 flush，不提交事务；由调用方统一 commit
        参数:
            session: SQLModel 会话
            media_file: 当前媒体文件记录（用于定位/创建 MediaCore）
            metadata: 新契约对象或 dict，支持 ScraperMovieDetail/ScraperSeriesDetail/ScraperEpisodeDetail/ScraperSearchResult 或其对应的 dict 形式
        行为:
            - 创建/更新 MediaCore 与 ExternalID
            - 电视剧分层映射: TVSeriesExt/SeasonExt/EpisodeExt        
            - 通用映射: Artwork/Genre/MediaCoreGenre/Person/Credit
            - 电影扩展与合集: MovieExt/Collection
        """
        # 如果 metadata 是 dict，包装为可通过 getattr 访问的对象
        if isinstance(metadata, dict):
            metadata = _DictWrapper(metadata)
        
        core = session.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id)).first()
        # logger.info(f"开始应用元数据：文件ID={media_file.id}, 当前核心ID={getattr(media_file, 'core_id', None)}, 元数据类型={type(metadata)}")
        # if isinstance(metadata, ScraperMovieDetail):
        # if hasattr(metadata, "movie_id"):
        if metadata_type == "movie":
            # logger.info(f"应用电影元数据：文件ID={media_file.id}, 元数据={metadata}")
            core = self._apply_movie_detail(session, media_file, metadata)

        # elif isinstance(metadata, ScraperEpisodeDetail):
        elif metadata_type == "episode":
            core = self._apply_episode_detail(session, media_file, metadata)

        # elif isinstance(metadata, ScraperSeriesDetail):
        elif metadata_type == "series":
            core = self._apply_series_detail(session, media_file.user_id, metadata)
            try:
                if not getattr(media_file, "core_id", None):
                    media_file.core_id = core.id
            except Exception:
                media_file.core_id = getattr(core, "id", None)
        
        # elif isinstance(metadata, ScraperSearchResult):
        elif metadata_type == "search_result":
            core = self._apply_search_result(session, media_file, metadata)

        else:
            return
        
        # 更新mediacore缓存
        self._refresh_display_cache_for_core(session, core, media_file.user_id)
        session.flush()

    def _apply_movie_detail(self, session, media_file: FileAsset, metadata: ScraperMovieDetail) -> MediaCore:
        # 添加或更新媒体核心元数据
        core = session.exec(select(MediaCore).where(MediaCore.id == media_file.core_id)).first()
        year_val = None
        try:
            dt = self._parse_dt(getattr(metadata, "release_date", None))
            year_val = dt.year if dt else None
        except Exception:
            year_val = None
        if not core:
            core = MediaCore(
                user_id=media_file.user_id,
                kind="movie",
                title=metadata.title,
                original_title=getattr(metadata, "original_title", None),
                year=year_val,
                plot=getattr(metadata, "overview", None),
                display_rating=getattr(metadata, "vote_average", None),
                display_poster_path=getattr(metadata, "poster_path", None),
                display_date=self._parse_dt(getattr(metadata, "release_date", None)),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(core)
            session.flush()
            media_file.core_id = core.id
        else:
            core.kind = "movie"
            core.title = metadata.title
            core.original_title = getattr(metadata, "original_title", None)
            core.year = year_val
            core.plot = getattr(metadata, "overview", None)
            core.display_rating = getattr(metadata, "vote_average", None)
            core.display_poster_path = getattr(metadata, "poster_path", None)
            core.display_date = self._parse_dt(getattr(metadata, "release_date", None))
            core.updated_at = datetime.now()
        
        # 改元信息提供商ID
        if getattr(metadata, "provider", None) and getattr(metadata, "movie_id", None):
            existing = session.exec(select(ExternalID).where(
                ExternalID.user_id == media_file.user_id,
                ExternalID.core_id == core.id,
                ExternalID.source == metadata.provider,
                ExternalID.key == str(metadata.movie_id)
            )).first()
            if not existing:
                session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=metadata.provider, key=str(metadata.movie_id)))
                session.flush()
            core.canonical_source = core.canonical_source or metadata.provider
            core.canonical_external_key = core.canonical_external_key or str(metadata.movie_id)
            try:
                if metadata.provider == "tmdb":
                    mid = int(str(metadata.movie_id)) if str(metadata.movie_id).isdigit() else None
                    if mid is not None:
                        core.canonical_tmdb_id = core.canonical_tmdb_id or mid
            except Exception:
                pass

        # 外部平台信息列表（tmdb，imdb）
        try:
            for eid in getattr(metadata, "external_ids", []) or []:
                if not eid or not getattr(eid, "provider", None) or not getattr(eid, "external_id", None):
                    continue
                existing = session.exec(select(ExternalID).where(
                    ExternalID.user_id == media_file.user_id,
                    ExternalID.core_id == core.id,
                    ExternalID.source == eid.provider,
                    ExternalID.key == str(eid.external_id)
                )).first()
                if not existing:
                    session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=eid.provider, key=str(eid.external_id)))
        except Exception:
            pass
        # 电影详细信息
        movie_ext = session.exec(select(MovieExt).where(MovieExt.user_id == media_file.user_id, MovieExt.core_id == core.id)).first()
        if not movie_ext:
            movie_ext = MovieExt(user_id=media_file.user_id, core_id=core.id)
            session.add(movie_ext)
            session.flush()
        try:
            movie_ext.tagline = getattr(metadata, "tagline", None)
            rv = getattr(metadata, "vote_average", None)
            movie_ext.rating = float(rv) if isinstance(rv, (int, float)) else movie_ext.rating
            movie_ext.overview = getattr(metadata, "overview", None) or movie_ext.overview
        except Exception:
            pass
        try:
            rd = getattr(metadata, "release_date", None)
            movie_ext.release_date = self._parse_dt(rd) if rd else movie_ext.release_date
        except Exception:
            pass
        try:
            movie_ext.poster_path = getattr(metadata, "poster_path", None) or movie_ext.poster_path
            movie_ext.backdrop_path = getattr(metadata, "backdrop_path", None) or movie_ext.backdrop_path
            movie_ext.imdb_id = getattr(metadata, "imdb_id", None) or movie_ext.imdb_id
            movie_ext.runtime_minutes = getattr(metadata, "runtime", None)
            if getattr(metadata, "raw_data", None):
                movie_ext.raw_data = json.dumps(metadata.raw_data, ensure_ascii=False)
        except Exception:
            pass
        try:
            col = getattr(metadata, "belongs_to_collection", None)
            if isinstance(col, dict) and col.get("id"):
                collection = session.exec(select(Collection).filter(Collection.id == col.get("id"))).first()
                if not collection:
                    collection = Collection(
                        id=col.get("id"),
                        name=col.get("name"),
                        poster_path=col.get("poster_path"),
                        backdrop_path=col.get("backdrop_path"),
                        overview=col.get("overview"),
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(collection)
                else:
                    collection.name = col.get("name")
                    collection.poster_path = col.get("poster_path")
                    collection.backdrop_path = col.get("backdrop_path")
                    collection.overview = col.get("overview")
                    collection.updated_at = datetime.now()
                movie_ext.collection_id = collection.id
        except Exception:
            pass
        # 图片海报等统一处理
        try:
            self._upsert_artworks(session, media_file.user_id, core.id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
        except Exception:
            pass

        # 直接根据 metadata 的 poster/backdrop 写入 Artwork，避免需要二次查询
        try:
            ppath = getattr(metadata, "poster_path", None)
            bpath = getattr(metadata, "backdrop_path", None)
            prov = getattr(metadata, "provider", None)
            if ppath:
                art_p = session.exec(select(Artwork).filter(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "poster",preferred=True)).first()
                if not art_p:
                    session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="poster", remote_url=ppath, provider=prov, preferred=True))
                else:
                    art_p.remote_url = art_p.remote_url or ppath
                    art_p.provider = prov or getattr(art_p, "provider", None)
                    art_p.preferred = True
                #     art_p.exists_remote = True
            if bpath:
                art_b = session.exec(select(Artwork).filter(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "backdrop",preferred=True)).first()
                if not art_b:
                    session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="backdrop", remote_url=bpath, provider=prov, preferred=True))
                else:
                    art_b.remote_url = art_b.remote_url or bpath
                    art_b.provider = prov or getattr(art_b, "provider", None)
                    art_b.preferred = True
        except Exception:
            pass
        # 演职人员信息
        try:
            self._upsert_credits(session, media_file.user_id, core.id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
        except Exception:
            pass
        # 类型信息
        try:
            self._upsert_genres(session, media_file.user_id, core.id, getattr(metadata, "genres", []) or [])
        except Exception:
            pass
        return core

    def _refresh_display_cache_for_core(self, session, core: MediaCore, user_id: int) -> None:
        try:
            if core.kind == 'movie':
                mx = session.exec(select(MovieExt).filter(MovieExt.core_id == core.id, MovieExt.user_id == user_id)).first()
                if mx:
                    core.display_rating = getattr(mx, 'rating', None)
                    core.display_poster_path = getattr(mx, 'poster_path', None)
                    core.display_date = getattr(mx, 'release_date', None)
            elif core.kind == 'tv_series':
                tv = session.exec(select(TVSeriesExt).filter(TVSeriesExt.core_id == core.id, TVSeriesExt.user_id == user_id)).first()
                if tv:
                    core.display_rating = getattr(tv, 'rating', None)
                    core.display_poster_path = getattr(tv, 'poster_path', None)
                se_first = session.exec(select(SeasonExt).filter(SeasonExt.series_core_id == core.id).order_by(SeasonExt.season_number)).first()
                if se_first and getattr(se_first, 'aired_date', None):
                    core.display_date = se_first.aired_date
                    try:
                        core.year = se_first.aired_date.year
                    except Exception:
                        pass
                if tv and getattr(tv, 'rating', None) is not None and core.display_rating is None:
                    core.display_rating = tv.rating
            elif core.kind == 'tv_season':
                se = session.exec(select(SeasonExt).filter(SeasonExt.core_id == core.id, SeasonExt.user_id == user_id)).first()
                if se:
                    try:
                        if se.series_core_id:
                            series = session.exec(select(MediaCore).filter(MediaCore.id == se.series_core_id)).first()
                            if series:
                                core.title = f"{series.title} 第{se.season_number}季"
                    except Exception:
                        pass
                    core.display_rating = getattr(se, 'rating', None)
                    core.display_poster_path = getattr(se, 'poster_path', None)
                    core.display_date = getattr(se, 'aired_date', None)
            elif core.kind == 'tv_episode':
                ep = session.exec(select(EpisodeExt).filter(EpisodeExt.core_id == core.id, EpisodeExt.user_id == user_id)).first()
                if ep:
                    core.title = ep.title or core.title
                    core.display_rating = getattr(ep, 'rating', None)
                    core.display_poster_path = None
                    core.display_date = getattr(ep, 'aired_date', None)
        except Exception:
            pass

    def _apply_episode_detail(self, session, media_file: FileAsset, metadata: ScraperEpisodeDetail) -> MediaCore:
        core = session.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id)).first()
        series_core = None
        season_core = None
        try:
            if getattr(metadata, "series", None):
                series_core = self._apply_series_detail(session, media_file.user_id, metadata.series)
            if getattr(metadata, "season", None):
                season_core = self._apply_season_detail(session, media_file.user_id, series_core, metadata.season)
        except Exception:
            pass
        if not core:
            title_val = getattr(metadata, "name", None) or ""
            core = MediaCore(
                user_id=media_file.user_id,
                kind="tv_episode",
                title=title_val,
                original_title=None,
                year=None,
                plot=getattr(metadata, "overview", None),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(core)
            session.flush()
            media_file.core_id = core.id
        else:
            core.kind = "tv_episode"
            core.title = getattr(metadata, "name", None) or core.title
            core.plot = getattr(metadata, "overview", None) or core.plot
            core.updated_at = datetime.now()
        ep_ext = session.exec(select(EpisodeExt).filter(EpisodeExt.core_id == core.id, EpisodeExt.user_id == media_file.user_id)).first()
        if not ep_ext:
            ep_ext = EpisodeExt(user_id=media_file.user_id, core_id=core.id, series_core_id=series_core.id if series_core else None, season_core_id=season_core.id if season_core else None, episode_number=getattr(metadata, "episode_number", None) or 1, season_number=getattr(metadata, "season_number", None) or 1)
            session.add(ep_ext)
        try:
            ep_ext.title = getattr(metadata, "name", None) or ep_ext.title
            ep_ext.overview = getattr(metadata, "overview", None) or ep_ext.overview
            ep_ext.runtime = getattr(metadata, "runtime", None)
            ep_ext.rating = getattr(metadata, "vote_average", None)
            ep_ext.vote_count = getattr(metadata, "vote_count", None)
            ep_ext.still_path = getattr(metadata, "still_path", None)
            ad = getattr(metadata, "air_date", None)
            ep_ext.aired_date = self._parse_dt(ad) if ad else ep_ext.aired_date
        except Exception:
            pass
        try:
            if getattr(ep_ext, "still_path", None):
                art_s = session.exec(select(Artwork).filter(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "still")).first()
                if not art_s:
                    session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="still", remote_url=ep_ext.still_path, provider=getattr(metadata, "provider", None), preferred=True, exists_remote=True))
                else:
                    art_s.remote_url = art_s.remote_url or ep_ext.still_path
                    art_s.provider = getattr(metadata, "provider", None) or getattr(art_s, "provider", None)
                    art_s.preferred = True
                    art_s.exists_remote = True
        except Exception:
            pass
        try:
            if getattr(metadata, "provider", None) and getattr(metadata, "episode_id", None):
                existing = session.exec(select(ExternalID).filter(
                    ExternalID.user_id == media_file.user_id,
                    ExternalID.core_id == core.id,
                    ExternalID.source == metadata.provider,
                    ExternalID.key == str(metadata.episode_id)
                )).first()
                if not existing:
                    session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=metadata.provider, key=str(metadata.episode_id)))
        except Exception:
            pass
        try:
            self._upsert_artworks(session, media_file.user_id, core.id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
        except Exception:
            pass
        try:
            self._upsert_credits(session, media_file.user_id, core.id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
        except Exception:
            pass
        return core

    def _apply_search_result(self, session, media_file: FileAsset, metadata: ScraperSearchResult) -> MediaCore:
        core = session.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id)).first()
        title_val = getattr(metadata, "title", None) or ""
        mt = getattr(metadata, "media_type", None) or "movie"
        kind_val = "movie" if mt == "movie" else ("tv_series" if mt == "tv_series" else "movie")
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
            prov = getattr(metadata, "provider", None)
            pid = getattr(metadata, "id", None)
            if prov and pid:
                existing = session.exec(select(ExternalID).filter(
                    ExternalID.user_id == media_file.user_id,
                    ExternalID.core_id == core.id,
                    ExternalID.source == prov,
                    ExternalID.key == str(pid)
                )).first()
                if not existing:
                    session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=prov, key=str(pid)))
                    session.flush()
                core.canonical_source = core.canonical_source or prov
                core.canonical_external_key = core.canonical_external_key or str(pid)
                if prov == "tmdb" and str(pid).isdigit():
                    core.canonical_tmdb_id = core.canonical_tmdb_id or int(str(pid))
        except Exception:
            pass
        try:
            if kind_val == "movie":
                mx = session.exec(select(MovieExt).filter(MovieExt.core_id == core.id, MovieExt.user_id == media_file.user_id)).first()
                if not mx:
                    mx = MovieExt(user_id=media_file.user_id, core_id=core.id)
                    session.add(mx)
                mx.poster_path = getattr(metadata, "poster_path", None) or mx.poster_path
            elif kind_val == "tv_series":
                tv = session.exec(select(TVSeriesExt).filter(TVSeriesExt.core_id == core.id, TVSeriesExt.user_id == media_file.user_id)).first()
                if not tv:
                    tv = TVSeriesExt(user_id=media_file.user_id, core_id=core.id)
                    session.add(tv)
                tv.poster_path = getattr(metadata, "poster_path", None) or tv.poster_path
        except Exception:
            pass
        return core


    # 更新所有MediaCore的显示缓存（批量）
    def backfill_display_cache(self, session, user_id: Optional[int] = None) -> None:
        try:
            cores = []
            cores.extend(session.exec(select(MediaCore).filter(MediaCore.kind == 'tv_series')).all() or [])
            cores.extend(session.exec(select(MediaCore).filter(MediaCore.kind == 'tv_season')).all() or [])
            for c in cores:
                if user_id and c.user_id != user_id:
                    continue
                self._refresh_display_cache_for_core(session, c, c.user_id)
        except Exception:
            pass
        session.flush()

    def backfill_canonical_and_plot(self, session, user_id: Optional[int] = None) -> None:
        try:
            series_list = session.exec(
                select(MediaCore).filter(MediaCore.kind == 'tv_series')
            ).all()
            for sc in series_list:
                if user_id and sc.user_id != user_id:
                    continue
                tv = session.exec(select(TVSeriesExt).filter(TVSeriesExt.core_id == sc.id, TVSeriesExt.user_id == sc.user_id)).first()
                if tv:
                    if not sc.plot and tv.overview:
                        sc.plot = tv.overview
                    tmdb_id = None
                    try:
                        if tv.raw_data:
                            import json as _json
                            data = _json.loads(tv.raw_data)
                            tmdb_id = str(data.get('id')) if isinstance(data.get('id'), (int, str)) else None
                    except Exception:
                        tmdb_id = None
                    if tmdb_id and not sc.canonical_external_key:
                        sc.canonical_tmdb_id = int(tmdb_id) if tmdb_id.isdigit() else sc.canonical_tmdb_id
                        sc.canonical_source = sc.canonical_source or 'tmdb'
                        sc.canonical_external_key = sc.canonical_external_key or tmdb_id
                        existing = session.exec(select(ExternalID).filter(
                            ExternalID.user_id == sc.user_id,
                            ExternalID.core_id == sc.id,
                            ExternalID.source == 'tmdb',
                            ExternalID.key == tmdb_id
                        )).first()
                        if not existing:
                            session.add(ExternalID(user_id=sc.user_id, core_id=sc.id, source='tmdb', key=tmdb_id))

            seasons = session.exec(select(MediaCore).filter(MediaCore.kind == 'tv_season')).all()
            for scc in seasons:
                if user_id and scc.user_id != user_id:
                    continue
                se = session.exec(select(SeasonExt).filter(SeasonExt.core_id == scc.id, SeasonExt.user_id == scc.user_id)).first()
                if se:
                    if not scc.plot and se.overview:
                        scc.plot = se.overview
                    if se.series_core_id:
                        series_core = session.exec(select(MediaCore).filter(MediaCore.id == se.series_core_id)).first()
                        if series_core and series_core.canonical_external_key:
                            scc.canonical_tmdb_id = scc.canonical_tmdb_id or series_core.canonical_tmdb_id
                            scc.canonical_source = scc.canonical_source or series_core.canonical_source
                            scc.canonical_external_key = scc.canonical_external_key or series_core.canonical_external_key
        except Exception:
            pass
        session.flush()


    def bind_version(self, session, media_file: FileAsset, parse_out) -> None:
        """
        绑定媒体版本并选择首选版本
        
        参数:
            session: SQLModel 会话
            media_file: 媒体文件记录（用于设置 primary_file_asset_id）
            parse_out: 文件解析结果（用于提取质量/来源等标签）
        行为:
            - 创建/更新 MediaVersion（scope: movie_single/season_group/series_group）
            - 根据质量与覆盖度选择 preferred 版本
        """
        core = session.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id)).first()
        if not core:
            return
        scope = None
        if core.kind == "movie":
            scope = "movie_single"
        elif core.kind in ("tv_season",):
            scope = "season_group"
        elif core.kind in ("tv_series",):
            scope = "series_group"
        else:
            return
        quality = None
        source = None
        edition = None
        if parse_out and getattr(parse_out, 'resolution_tags', None):
            if len(parse_out.resolution_tags) > 0:
                quality = parse_out.resolution_tags[0]
        qt = set(parse_out.quality_tags or []) if parse_out else set()
        for s in ["web", "bluray", "dvd", "hdtv"]:
            for pat in list(qt):
                if s in pat.lower():
                    source = s
                    break
            if source:
                break
        variant_fingerprint = "|".join([v for v in [quality or "", source or "", edition or ""]])
        from models.media_models import MediaVersion, EpisodeExt, SeasonExt
        mv = session.exec(select(MediaVersion).filter(
            MediaVersion.user_id == media_file.user_id,
            MediaVersion.core_id == core.id,
            MediaVersion.scope == scope,
            MediaVersion.variant_fingerprint == variant_fingerprint
        )).first()
        if not mv:
            mv = MediaVersion(
                user_id=media_file.user_id,
                core_id=core.id,
                tags="",
                quality=quality,
                source=source,
                edition=edition,
                scope=scope,
                variant_fingerprint=variant_fingerprint,
                preferred=False,
                primary_file_asset_id=media_file.id if scope == "movie_single" else None
            )
            session.add(mv)
            session.flush()
        media_file.version_id = mv.id
        try:
            if scope == "movie_single":
                versions = session.exec(select(MediaVersion).filter(
                    MediaVersion.user_id == media_file.user_id,
                    MediaVersion.core_id == core.id,
                    MediaVersion.scope == "movie_single"
                )).all()
                if versions:
                    best = None
                    best_key = (999, 999)
                    for v in versions:
                        key = (self._quality_rank(v.quality), self._source_rank(v.source))
                        if key < best_key:
                            best_key = key
                            best = v
                    for v in versions:
                        v.preferred = (v.id == best.id)
                    session.flush()
            elif scope == "season_group":
                versions = session.exec(select(MediaVersion).filter(
                    MediaVersion.user_id == media_file.user_id,
                    MediaVersion.core_id == core.id,
                    MediaVersion.scope == "season_group"
                )).all()
                if versions:
                    total_eps = len(session.exec(select(EpisodeExt).filter(EpisodeExt.season_core_id == core.id, EpisodeExt.user_id == media_file.user_id)).all())
                    if total_eps == 0:
                        se = session.exec(select(SeasonExt).filter(SeasonExt.core_id == core.id, SeasonExt.user_id == media_file.user_id)).first()
                        total_eps = se.episode_count or 0 if se else 0
                    best = None
                    best_key = (-1, 999)
                    for v in versions:
                        cov = session.exec(select(FileAsset).join(EpisodeExt, FileAsset.episode_core_id == EpisodeExt.core_id).filter(
                            FileAsset.user_id == media_file.user_id,
                            FileAsset.version_id == v.id,
                            EpisodeExt.season_core_id == core.id
                        )).count()
                        key = (cov, self._quality_rank(v.quality))
                        if key > best_key:
                            best_key = key
                            best = v
                    for v in versions:
                        v.preferred = (best is not None and v.id == best.id)
                    session.flush()
            elif scope == "series_group":
                versions = session.exec(select(MediaVersion).filter(
                    MediaVersion.user_id == media_file.user_id,
                    MediaVersion.core_id == core.id,
                    MediaVersion.scope == "series_group"
                )).all()
                if versions:
                    best = None
                    best_key = (-1, 999)
                    for v in versions:
                        cov = session.exec(select(FileAsset).join(EpisodeExt).filter(
                            FileAsset.episode_core_id == EpisodeExt.core_id,
                            FileAsset.user_id == media_file.user_id,
                            FileAsset.version_id == v.id,
                            EpisodeExt.series_core_id == core.id
                        )).count()
                        key = (cov, self._quality_rank(v.quality))
                        if key > best_key:
                            best_key = key
                            best = v
                    for v in versions:
                        v.preferred = (best is not None and v.id == best.id)
                    session.flush()
        except Exception:
            pass

    def _quality_rank(self, q: Optional[str]) -> int:
        """
        质量优先级排序（数值越小质量越高）
        
        支持: 4k/2160p/1080p/720p/480p
        """
        order = ["4k", "2160p", "1080p", "720p", "480p"]
        if not q:
            return len(order)
        ql = q.lower()
        for i, v in enumerate(order):
            if v in ql:
                return i
        return len(order)

    def _source_rank(self, s: Optional[str]) -> int:
        """
        来源优先级排序（数值越小来源越优）
        
        支持: bluray/web/hdtv/dvd
        """
        order = ["bluray", "web", "hdtv", "dvd"]
        if not s:
            return len(order)
        sl = s.lower()
        for i, v in enumerate(order):
            if v in sl:
                return i
        return len(order)

persistence_service = MetadataPersistenceService()
