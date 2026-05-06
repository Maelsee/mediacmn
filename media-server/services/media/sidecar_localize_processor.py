import logging
from typing import Optional
from datetime import datetime

from sqlmodel import select
from sqlalchemy import func

from core.db import get_async_session
from models.media_models import FileAsset, MediaCore, ExternalID, EpisodeExt, SeasonExt
from services.storage.storage_service import storage_service
from services.storage.client_pool import get_client_pool
from services.scraper import scraper_manager, MediaType
from services.media.metadata_enricher import metadata_enricher

logger = logging.getLogger(__name__)


class SidecarLocalizeProcessor:
    def __init__(self):
        self.storage_service = storage_service

    async def process(self, file_id: int, storage_id: int, language: str = "zh-CN") -> bool:
        """
        生成并本地化侧车文件（NFO/Poster/Fanart）

        流程:
            - 校验存储客户端与文件/核心存在性
            - 检查是否已本地化（存在NFO且至少一个主要artwork）
            - 根据核心规范外部ID加载插件并获取详情
            - 调用丰富器写侧车文件
        参数:
            file_id: 媒体文件ID
            storage_id: 存储配置ID
            language: 详情语言
        返回:
            是否本地化成功
        """
        try:
            if storage_id is None:
                logger.error("侧车本地化处理器缺少storage_id")
                return False
            async with get_async_session() as session:
                media_file = (await session.exec(select(FileAsset).filter(FileAsset.id == file_id))).first()
                if not media_file:
                    logger.error(f"侧车本地化失败，文件不存在: {file_id}")
                    return False

                core = (await session.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id))).first()
                if not core:
                    logger.error(f"侧车本地化失败，未找到核心媒体: file_id={file_id}")
                    return False

                pool = get_client_pool()
                async with pool.acquire(storage_id, user_id=media_file.user_id, client_factory=lambda: self.storage_service._create_and_connect(storage_id)) as storage_client:

                    from pathlib import Path
                    file_dir = str(Path(media_file.full_path).parent)
                    file_name = Path(media_file.full_path).stem

                    media_type = await self._determine_media_type(session, core, media_file)

                    # 通过 ExternalID 获取规范外部标识
                    ext = (await session.exec(select(ExternalID).filter(ExternalID.user_id == media_file.user_id, ExternalID.core_id == core.id))).first()
                    if not ext:
                        logger.error("无外部ID可用于重建侧车内容")
                        return False
                    provider = ext.source
                    external_key = ext.key

                    try:
                        from services.scraper.tmdb import TmdbScraper
                        try:
                            scraper_manager.register_plugin(TmdbScraper)
                        except Exception:
                            pass
                        loaded_plugins = scraper_manager.get_loaded_plugins()
                        if provider not in loaded_plugins:
                            await scraper_manager.load_plugin(provider)
                        scraper_manager.enable_plugin(provider)
                    except Exception as e:
                        logger.error(f"加载刮削插件失败: {e}")
                        return False

                    plugin = scraper_manager.get_plugin(provider)
                    details = None
                    try:
                        if media_type == MediaType.MOVIE and hasattr(plugin, "get_movie_details"):
                            details = await plugin.get_movie_details(external_key, language)
                        elif media_type == MediaType.TV_SERIES and hasattr(plugin, "get_series_details"):
                            details = await plugin.get_series_details(external_key, language)
                        elif media_type == MediaType.TV_EPISODE:
                            ep = (await session.exec(select(EpisodeExt).filter(EpisodeExt.user_id == media_file.user_id, EpisodeExt.core_id == core.id))).first()
                            series_id = None
                            series_provider = None
                            season_no = None
                            episode_no = None
                            if ep and ep.series_core_id:
                                sc = (await session.exec(select(MediaCore).filter(MediaCore.id == ep.series_core_id))).first()
                                if sc:
                                    # 通过 ExternalID 获取系列的外部标识
                                    ext2 = (await session.exec(select(ExternalID).filter(ExternalID.user_id == media_file.user_id, ExternalID.core_id == sc.id))).first()
                                    if ext2:
                                        series_provider = ext2.source
                                        series_id = ext2.key
                                    season_no = getattr(ep, "season_number", None)
                                    episode_no = getattr(ep, "episode_number", None)
                            if series_provider and series_id:
                                try:
                                    loaded = scraper_manager.get_loaded_plugins()
                                    if series_provider not in loaded:
                                        await scraper_manager.load_plugin(series_provider)
                                    scraper_manager.enable_plugin(series_provider)
                                except Exception:
                                    pass
                                plugin2 = scraper_manager.get_plugin(series_provider)
                                try:
                                    if hasattr(plugin2, "get_episode_details") and season_no is not None and episode_no is not None:
                                        details = await plugin2.get_episode_details(series_id, int(season_no), int(episode_no), language)
                                    elif hasattr(plugin2, "get_series_details"):
                                        details = await plugin2.get_series_details(series_id, language)
                                except Exception:
                                    details = None
                            if details is None and hasattr(plugin, "get_series_details"):
                                try:
                                    details = await plugin.get_series_details(external_key, language)
                                except Exception:
                                    details = None
                        else:
                            details = None
                    except Exception:
                        details = None
                    if not details:
                        logger.error("获取详情失败，无法生成侧车文件")
                        return False

                    import aiohttp
                    poster_url = None
                    fanart_url = None
                    if getattr(details, "artworks", None):
                        for a in details.artworks:
                            t = getattr(a, "type", None)
                            if t and getattr(t, "value", t) in ("poster", "POSTER") and not poster_url:
                                poster_url = getattr(a, "url", None)
                            if t and getattr(t, "value", t) in ("backdrop", "fanart", "BACKDROP", "FANART") and not fanart_url:
                                fanart_url = getattr(a, "url", None)
                    async def _remote_ok(url: Optional[str]) -> bool:
                        if not url:
                            return False
                        try:
                            timeout = aiohttp.ClientTimeout(total=10)
                            async with aiohttp.ClientSession(timeout=timeout) as s:
                                async with s.head(url) as r:
                                    if 200 <= r.status < 400:
                                        return True
                                async with s.get(url) as r2:
                                    return 200 <= r2.status < 400
                        except Exception:
                            return False
                    p_ok = await _remote_ok(poster_url)
                    f_ok = await _remote_ok(fanart_url)
                    if not (p_ok or f_ok):
                        return True

                    async def _valid(path: str) -> bool:
                        try:
                            if not await storage_client.exists(path):
                                return False
                            info = await storage_client.get_file_info(path)
                            if info and info.size and info.size > 0:
                                return True
                            return False
                        except Exception:
                            return False

                    nfo_path = f"{file_dir}/{file_name}.nfo"
                    poster_path = f"{file_dir}/{file_name}.poster.jpg"
                    fanart_path = f"{file_dir}/{file_name}.fanart.jpg"

                    nfo_valid = await _valid(nfo_path)
                    poster_valid = await _valid(poster_path)
                    fanart_valid = await _valid(fanart_path)

                    if nfo_valid and (poster_valid or fanart_valid):
                        try:
                            async with get_async_session() as s2:
                                core2 = (await s2.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id))).first()
                                if core2:
                                    try:
                                        from models.media_models import MovieExt, SeriesExt, SeasonExt
                                        if core2.kind == 'movie':
                                            mx2 = (await s2.exec(select(MovieExt).where(MovieExt.user_id == media_file.user_id, MovieExt.core_id == core2.id))).first()
                                            if mx2:
                                                mx2.nfo_path = nfo_path
                                        elif core2.kind == 'series':
                                            tv2 = (await s2.exec(select(SeriesExt).where(SeriesExt.user_id == media_file.user_id, SeriesExt.core_id == core2.id))).first()
                                            if tv2:
                                                tv2.nfo_path = nfo_path
                                        elif core2.kind == 'season':
                                            se2 = (await s2.exec(select(SeasonExt).where(SeasonExt.user_id == media_file.user_id, SeasonExt.core_id == core2.id))).first()
                                            if se2:
                                                se2.nfo_path = nfo_path
                                    except Exception:
                                        pass
                                    from models.media_models import Artwork
                                    poster_row = (await s2.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core2.id, func.lower(Artwork.type) == "poster"))).first()
                                    backdrop_row = (await s2.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core2.id, func.lower(Artwork.type) == "backdrop"))).first()
                                    if not backdrop_row:
                                        backdrop_row = (await s2.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core2.id, func.lower(Artwork.type) == "fanart"))).first()
                                    if poster_valid:
                                        if poster_row:
                                            poster_row.exists_local = True
                                            poster_row.local_path = poster_path
                                            poster_row.preferred = True or poster_row.preferred
                                        else:
                                            s2.add(Artwork(user_id=media_file.user_id, core_id=core2.id, type="poster", local_path=poster_path, preferred=True, exists_local=True, exists_remote=False))
                                    if fanart_valid:
                                        if backdrop_row:
                                            backdrop_row.exists_local = True
                                            backdrop_row.local_path = fanart_path
                                            backdrop_row.preferred = True or backdrop_row.preferred
                                        else:
                                            s2.add(Artwork(user_id=media_file.user_id, core_id=core2.id, type="backdrop", local_path=fanart_path, preferred=True, exists_local=True, exists_remote=False))
                                    await s2.commit()
                        except Exception:
                            pass
                        return True

                    ok_nfo = True
                    try:
                        if not nfo_valid:
                            # 构建更丰富的 NFO XML
                            # 取日期
                            dateadded = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            # 提取 TMDB/IMDB ID
                            tmdb_id = None
                            imdb_id = None
                            try:
                                if getattr(details, "external_ids", None):
                                    for eid in details.external_ids:
                                        if getattr(eid, "provider", None) == "tmdb" and getattr(eid, "external_id", None):
                                            tmdb_id = str(eid.external_id)
                                        if getattr(eid, "provider", None) == "imdb" and getattr(eid, "external_id", None):
                                            imdb_id = str(eid.external_id)
                            except Exception:
                                pass
                            tmdb_id = tmdb_id or (str(details.provider_id) if (details.provider == "tmdb" and details.provider_id) else None)
                            # 提取导演与演员
                            directors = []
                            actors = []
                            try:
                                for c in getattr(details, "credits", []) or []:
                                    ctype = getattr(c, "type", None)
                                    cname = getattr(c, "name", None) or ""
                                    role = getattr(c, "role", None)
                                    order = getattr(c, "order", None)
                                    tmdb_person_id = None
                                    try:
                                        for ex in (getattr(c, "external_ids", []) or []):
                                            if getattr(ex, "provider", None) == "tmdb" and getattr(ex, "external_id", None):
                                                tmdb_person_id = str(ex.external_id)
                                                break
                                    except Exception:
                                        tmdb_person_id = None
                                    ptype = getattr(ctype, "value", ctype)
                                    if ptype and str(ptype).lower() == "director":
                                        directors.append((cname, tmdb_person_id))
                                    elif ptype and str(ptype).lower() == "actor":
                                        actors.append((cname, role, order, tmdb_person_id))
                            except Exception:
                                pass

                            # CDATA 包裹
                            def _cdata(text: Optional[str]) -> str:
                                t = text or ""
                                return f"<![CDATA[{t}]]>"

                            # 概要/剧情
                            plot_text = details.overview or ""
                            outline_text = details.tagline or details.overview or ""

                            # 评分/年份/首映
                            rating = details.rating or 0
                            year = details.year or 0
                            premiered = None
                            try:
                                rd = getattr(details, "release_date", None)
                                if rd:
                                    if hasattr(rd, "strftime"):
                                        premiered = rd.strftime("%Y-%m-%d")
                                    else:
                                        premiered = str(rd)[:10]
                            except Exception:
                                premiered = None

                            # 标题
                            title = details.title or ""
                            original_title = details.original_title or title

                            # 类型
                            genres = getattr(details, "genres", []) or []

                            # 构造 XML 文本
                            lines = []
                            lines.append("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
                            lines.append("<movie>")
                            lines.append(f"  <dateadded>{dateadded}</dateadded>")
                            if tmdb_id:
                                lines.append(f"  <tmdbid>{tmdb_id}</tmdbid>")
                                lines.append(f"  <uniqueid type=\"tmdb\" default=\"true\">{tmdb_id}</uniqueid>")
                            if imdb_id:
                                lines.append(f"  <imdbid>{imdb_id}</imdbid>")
                                lines.append(f"  <uniqueid type=\"imdb\">{imdb_id}</uniqueid>")
                            lines.append(f"  <plot>{_cdata(plot_text)}</plot>")
                            lines.append(f"  <outline>{_cdata(outline_text)}</outline>")
                            for dname, dtmdb in directors:
                                if dtmdb:
                                    lines.append(f"  <director tmdbid=\"{dtmdb}\">{dname}</director>")
                                else:
                                    lines.append(f"  <director>{dname}</director>")
                            for name, role, order, pid in actors:
                                lines.append("  <actor>")
                                lines.append(f"    <name>{name}</name>")
                                lines.append(f"    <type>Actor</type>")
                                lines.append(f"    <role>{role or ''}</role>")
                                lines.append(f"    <order>{'' if (order is None) else order}</order>")
                                if pid:
                                    lines.append(f"    <tmdbid>{pid}</tmdbid>")
                                lines.append("  </actor>")
                            for g in genres:
                                lines.append(f"  <genre>{g}</genre>")
                            lines.append(f"  <rating>{rating}</rating>")
                            lines.append(f"  <title>{title}</title>")
                            lines.append(f"  <originaltitle>{original_title}</originaltitle>")
                            if premiered:
                                lines.append(f"  <premiered>{premiered}</premiered>")
                            lines.append(f"  <year>{year}</year>")
                            lines.append("</movie>")

                            nfo_xml = "\n".join(lines)
                            ok_nfo = await storage_client.upload(nfo_path, nfo_xml.encode("utf-8"), content_type="application/xml")
                    except Exception:
                        ok_nfo = False

                    async def _download(url: Optional[str]) -> Optional[bytes]:
                        if not url:
                            return None
                        try:
                            timeout = aiohttp.ClientTimeout(total=20)
                            async with aiohttp.ClientSession(timeout=timeout) as s:
                                async with s.get(url) as r:
                                    if r.status != 200:
                                        return None
                                    return await r.read()
                        except Exception:
                            return None

                    poster_ok = True
                    fanart_ok = True
                    try:
                        if not poster_valid and p_ok and poster_url:
                            pb = await _download(poster_url)
                            if pb:
                                poster_ok = await storage_client.upload(poster_path, pb, content_type="image/jpeg")
                        if not fanart_valid and f_ok and fanart_url:
                            fb = await _download(fanart_url)
                            if fb:
                                fanart_ok = await storage_client.upload(fanart_path, fb, content_type="image/jpeg")
                    except Exception:
                        pass

                    try:
                        async with get_async_session() as s2:
                            core2 = (await s2.exec(select(MediaCore).filter(MediaCore.id == media_file.core_id))).first()
                            if core2:
                                nfo_exists2 = await storage_client.exists(nfo_path)
                                try:
                                    from models.media_models import MovieExt, SeriesExt, SeasonExt
                                    if core2.kind == 'movie':
                                        mx2 = (await s2.exec(select(MovieExt).where(MovieExt.user_id == media_file.user_id, MovieExt.core_id == core2.id))).first()
                                        if mx2:
                                            mx2.nfo_path = nfo_path if nfo_exists2 else mx2.nfo_path
                                    elif core2.kind == 'series':
                                        tv2 = (await s2.exec(select(SeriesExt).where(SeriesExt.user_id == media_file.user_id, SeriesExt.core_id == core2.id))).first()
                                        if tv2:
                                            tv2.nfo_path = nfo_path if nfo_exists2 else tv2.nfo_path
                                    elif core2.kind == 'season':
                                        se2 = (await s2.exec(select(SeasonExt).where(SeasonExt.user_id == media_file.user_id, SeasonExt.core_id == core2.id))).first()
                                        if se2:
                                            se2.nfo_path = nfo_path if nfo_exists2 else se2.nfo_path
                                except Exception:
                                    pass
                                from models.media_models import Artwork
                                poster_exists2 = await storage_client.exists(poster_path)
                                fanart_exists2 = await storage_client.exists(fanart_path)
                                poster_row = (await s2.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core2.id, func.lower(Artwork.type) == "poster"))).first()
                                backdrop_row = (await s2.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core2.id, func.lower(Artwork.type) == "backdrop"))).first()
                                if not backdrop_row:
                                    backdrop_row = (await s2.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core2.id, func.lower(Artwork.type) == "fanart"))).first()
                                if poster_row:
                                    poster_row.exists_local = bool(poster_exists2)
                                    poster_row.local_path = poster_path if poster_exists2 else poster_row.local_path
                                    poster_row.preferred = bool(poster_exists2) or poster_row.preferred
                                elif poster_exists2:
                                    s2.add(Artwork(user_id=media_file.user_id, core_id=core2.id, type="poster", local_path=poster_path, preferred=True, exists_local=True, exists_remote=False))
                                if backdrop_row:
                                    backdrop_row.exists_local = bool(fanart_exists2)
                                    backdrop_row.local_path = fanart_path if fanart_exists2 else backdrop_row.local_path
                                    backdrop_row.preferred = bool(fanart_exists2) or backdrop_row.preferred
                                elif fanart_exists2:
                                    s2.add(Artwork(user_id=media_file.user_id, core_id=core2.id, type="backdrop", local_path=fanart_path, preferred=True, exists_local=True, exists_remote=False))
                                await s2.commit()
                    except Exception:
                        pass

                    return bool(ok_nfo and poster_ok and fanart_ok)

        except Exception as e:
            logger.exception(f"侧车本地化处理异常: {e}")
            return False

    async def _check_already_localized(self, storage_client, media_file: FileAsset, core: MediaCore) -> bool:
        return False

    async def _write_sidecar_files(self, storage_client, media_file: FileAsset, details) -> bool:
        """
        生成并写入侧车文件（NFO/Poster/Fanart）
        - NFO：简单XML快照（标题/年份/评分/简介/外部ID）
        - Poster/Fanart：下载远程图片并保存
        返回：是否全部成功
        """
        try:
            from pathlib import Path
            import aiohttp
            file_dir = str(Path(media_file.full_path).parent)
            file_name = Path(media_file.full_path).stem
            # 1) NFO
            nfo_path = f"{file_dir}/{file_name}.nfo"
            # 构造最小NFO
            title = details.title
            year = details.year or 0
            rating = details.rating or 0
            overview = details.overview or ""
            provider = details.provider or ""
            provider_id = details.provider_id or ""
            nfo_xml = (
                f"<movie>\n"
                f"  <title>{title}</title>\n"
                f"  <year>{year}</year>\n"
                f"  <rating>{rating}</rating>\n"
                f"  <plot>{overview}</plot>\n"
                f"  <id>{provider}:{provider_id}</id>\n"
                f"</movie>\n"
            )
            ok_nfo = await storage_client.upload(nfo_path, nfo_xml.encode("utf-8"), content_type="application/xml")
            # 2) 图片
            async def download(url: str) -> bytes:
                timeout = aiohttp.ClientTimeout(total=20)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise Exception(f"download_failed: {url} status={resp.status}")
                        return await resp.read()
            poster_ok = True
            fanart_ok = True
            try:
                poster_url = None
                fanart_url = None
                if getattr(details, "artworks", None):
                    for a in details.artworks:
                        t = getattr(a, "type", None)
                        if t and getattr(t, "value", t) in ("poster", "POSTER") and not poster_url:
                            poster_url = getattr(a, "url", None)
                        if t and getattr(t, "value", t) in ("backdrop", "fanart", "BACKDROP", "FANART") and not fanart_url:
                            fanart_url = getattr(a, "url", None)
                if poster_url:
                    poster_bytes = await download(poster_url)
                    poster_ok = await storage_client.upload(f"{file_dir}/{file_name}.poster.jpg", poster_bytes, content_type="image/jpeg")
                if fanart_url:
                    fanart_bytes = await download(fanart_url)
                    fanart_ok = await storage_client.upload(f"{file_dir}/{file_name}.fanart.jpg", fanart_bytes, content_type="image/jpeg")
            except Exception:
                pass
            return bool(ok_nfo and poster_ok and fanart_ok)
        except Exception:
            return False

    async def _determine_media_type(self, session, core: MediaCore, media_file: FileAsset) -> MediaType:
        """
        根据现有扩展/核心类型判断媒体类型，用于选择详情端点

        优先级:
            - 存在 EpisodeExt → TV_EPISODE
            - 核心为 tv_series/tv_season → TV_SERIES
            - 其他 → MOVIE
        """
        try:
            ep = (await session.exec(select(EpisodeExt).filter(EpisodeExt.core_id == media_file.core_id, EpisodeExt.user_id == media_file.user_id))).first()
            if ep:
                return MediaType.TV_EPISODE
            if core.kind in ("series", "season"):
                return MediaType.TV_SERIES
            return MediaType.MOVIE
        except Exception:
            return MediaType.MOVIE
