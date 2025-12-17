import logging
import json
import os
import hashlib
import random
from datetime import datetime
from re import L
from typing import Optional, Dict, Any, List

from sqlmodel import Session, select

from models.media_models import (
    MediaCore, ExternalID, FileAsset, Artwork, Genre, MediaCoreGenre,
    Person, Credit, MovieExt, EpisodeExt, SeasonExt, SeriesExt, Collection,MediaVersion
)
from models.storage_models import StorageConfig
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

    # ==================== 版本管理核心辅助方法 ====================
    def _get_version_tags_and_fingerprint(self, media_file: FileAsset,core:MediaCore,scope) -> tuple[str,str]:
        """
        生成版本标签与指纹（核心区分字段）
        格式：scope_coreid_filenamehash_filesize,e.g movie_single_23_756f2a3b6256412_45678900
        """
        file_full_path = media_file.full_path or "unknown"
        filesize = media_file.size or 0
        filename_hash = hashlib.sha256(file_full_path.encode("utf-8")).hexdigest()[:16]
        # tags 格式：scope_coreid_filename_filesize,e.g movie_single_23_七月与安生 (2016) - 1080p.mkv_45678900
        tags = f"{scope}_{core.id}_{filename_hash}_{filesize}"

        fingerprint_str = f"{file_full_path}_{filesize}_{core.id}_{media_file.user_id}"
        fingerprint_str_hash = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()
        return tags,fingerprint_str_hash

    def _get_quality_level(self, media_file: FileAsset) -> Optional[str]:
        """根据分辨率映射质量(未实现!!!)"""
        resolution = media_file.resolution or None
        example = ["4k", "2160p", "1080p"]
        return resolution if resolution else example[random.randint(0, len(example) - 1)]

    def _get_file_source(self, session, media_file: FileAsset) -> str:
        """
        提取文件来源（provider）
        逻辑：从文件名中提取可能的来源（如"HDTV"、"Blu-ray"等）
        """
        storage_id = media_file.storage_id
        storage_type = None
        try:
            sc = session.exec(select(StorageConfig).where(StorageConfig.id == storage_id)).first() if storage_id else None
            storage_type = getattr(sc, 'storage_type', None)
        except Exception as e:
            logger.error(f"获取存储配置失败：{str(e)}",storage_type)
            storage_type = None
        
        return storage_type or "unknown"

    def _get_season_version_path(self, media_file: FileAsset) -> str:
        """
        提取单集文件的父文件夹路径作为季版本的唯一标识
        逻辑：取文件完整路径的上一级文件夹路径（标准化为绝对路径，统一分隔符）
        """
        try:
            # 标准化路径，处理不同系统的分隔符
            full_path = os.path.abspath(media_file.full_path)
            parent_dir = os.path.dirname(full_path)
            # 统一使用/作为分隔符，避免跨系统差异
            return parent_dir.replace("\\", "/")
        except Exception as e:
            logger.error(f"提取父文件夹路径失败：{str(e)}", exc_info=True)
            # 降级使用文件名作为路径（避免失败）
            return f"default_season_path_{media_file.filename}"

    def _generate_season_version_tags(self, season_version_path: str, season_core: MediaCore) -> str:
        """
        生成季版本的标签（唯一标识季版本）
        逻辑：父文件夹路径 + 季核心ID（确保同一季的不同文件夹版本唯一）
        """
        # 对路径进行MD5简化，避免标签过长
        path_hash = hashlib.sha256(season_version_path.encode("utf-8")).hexdigest()[:16]
        tags = f"season_group_{season_core.id}_{path_hash}"
        return tags

    def _upsert_season_version(self, session, media_file: FileAsset, season_core: MediaCore) -> int:
        """
        创建/更新季版本（season_group）
        返回：季版本ID
        """
        # 1. 提取文件父文件夹路径作为季版本的核心标识
        season_version_path = self._get_season_version_path(media_file)
        # 2. 生成季版本的唯一标签
        season_tags = self._generate_season_version_tags(season_version_path, season_core)
        # 3. 生成季版本的指纹（基于路径+季核心ID）
        fingerprint_str = f"{season_version_path}_{season_core.id}_{media_file.user_id}"
        season_fingerprint = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()

        # 4. 查询是否已有相同的季版本（用户+季核心+标签唯一）
        existing_season_version = session.exec(select(MediaVersion).where(
            MediaVersion.user_id == media_file.user_id,
            MediaVersion.core_id == season_core.id,
            MediaVersion.tags == season_tags,
            MediaVersion.scope == "season_group"
        )).first()

        if existing_season_version:
            # 更新现有季版本（补充空字段）
            existing_season_version.variant_fingerprint = existing_season_version.variant_fingerprint or season_fingerprint
            existing_season_version.updated_at = datetime.now()
            existing_season_version.season_version_path = season_version_path  # 更新季版本路径
            logger.debug(f"更新季版本: user_id={media_file.user_id}, season_core_id={season_core.id}, version_id={existing_season_version.id}")
            return existing_season_version.id
        else:
            # 检查该季核心是否已有季版本（第一个版本设为首选）
            has_existing_season_versions = session.exec(select(MediaVersion).where(
                MediaVersion.user_id == media_file.user_id,
                MediaVersion.core_id == season_core.id,
                MediaVersion.scope == "season_group"
            )).first() is not None

            # 创建新季版本
            new_season_version = MediaVersion(
                user_id=media_file.user_id,
                core_id=season_core.id,
                tags=season_tags,
                scope="season_group",  # 标记为季版本作用域
                variant_fingerprint=season_fingerprint,
                preferred=not has_existing_season_versions,  # 第一个季版本设为首选
                primary_file_asset_id=None,  # 季版本无主文件（管理一批单集文件）
                parent_version_id=None,  # 季版本无父版本
                season_version_path=season_version_path,  # 保存季版本路径
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(new_season_version)
            session.flush()  # 刷新获取ID
            logger.debug(f"创建季版本: user_id={media_file.user_id}, season_core_id={season_core.id}, version_id={new_season_version.id}, path={season_version_path}")
            return new_season_version.id

    def _upsert_media_version(self, session, media_file: FileAsset, core: MediaCore, metadata, season_version_id: Optional[int] = None) -> int:
        """
        创建/更新媒体版本（支持episode_child关联到season_group，支持movie）
        参数：
            season_version_id: 可选，季版本ID（仅episode类型需要）
        返回：版本ID
        """
       

        # 2. 确定版本作用域
        if core.kind == "movie":
            scope = "movie_single"
        elif core.kind == "episode":
            scope = "episode_child"  # 单集版本标记为子版本
        else:
            scope = "movie_single"  # 兜底

         # 1. 生成版本和指纹关键信息
        version_tags,variant_fingerprint = self._get_version_tags_and_fingerprint(media_file,core,scope)
        quality = self._get_quality_level(media_file)
        edition = self._get_attr(metadata, "edition") or self._get_attr(metadata, "episode_type") or "unknown"
        source = self._get_file_source(session, media_file)
        

        # 3. 查询是否已有相同版本（用户+核心+标签唯一）
        existing_version = session.exec(select(MediaVersion).where(
            MediaVersion.user_id == media_file.user_id,
            MediaVersion.core_id == core.id,
            MediaVersion.tags == version_tags,
            MediaVersion.scope == scope
        )).first()

        if existing_version:
            # 更新现有版本
            existing_version.quality = existing_version.quality or quality
            existing_version.source = existing_version.source or source
            existing_version.edition = existing_version.edition or edition
            existing_version.variant_fingerprint = existing_version.variant_fingerprint or variant_fingerprint
            # 若传入季版本ID，更新父版本关联
            if season_version_id:
                existing_version.parent_version_id = season_version_id
            existing_version.updated_at = datetime.now()
            # 补充主文件ID
            if not existing_version.primary_file_asset_id:
                existing_version.primary_file_asset_id = media_file.id
            logger.debug(f"更新{scope}版本: user_id={media_file.user_id}, core_id={core.id}, tags={version_tags}")
            return existing_version.id
        else:
            # 检查该核心是否已有版本（第一个版本设为首选）
            has_existing_versions = session.exec(select(MediaVersion).where(
                MediaVersion.user_id == media_file.user_id,
                MediaVersion.core_id == core.id,
                MediaVersion.scope == scope
            )).first() is not None

            # 创建新版本
            new_version = MediaVersion(
                user_id=media_file.user_id,
                core_id=core.id,
                tags=version_tags,
                quality=quality,
                source=source,
                edition=edition,
                scope=scope,
                variant_fingerprint=variant_fingerprint,
                preferred=not has_existing_versions,
                primary_file_asset_id=media_file.id,
                parent_version_id=season_version_id,  # 关联到季版本（子版本核心）
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(new_version)
            session.flush()
            logger.debug(f"创建{scope}版本: user_id={media_file.user_id}, core_id={core.id}, version_id={new_version.id}, parent_version_id={season_version_id}")
            return new_version.id

    def batch_operate_episode_versions_by_season(self, session, user_id: int, season_version_id: int, operation: str = "delete") -> bool:
        """
        批量操作季版本下的所有单集子版本
        参数：
            operation: 操作类型：delete（删除）/set_preferred（设为首选）
        返回：操作是否成功
        """
        try:
            # 1. 查询季版本下的所有单集子版本
            episode_versions = session.exec(select(MediaVersion).where(
                MediaVersion.user_id == user_id,
                MediaVersion.parent_version_id == season_version_id,
                MediaVersion.scope == "episode_child"
            )).all()

            if not episode_versions:
                logger.warning(f"季版本{season_version_id}下无单集子版本")
                return True

            # 2. 执行批量操作
            if operation == "delete":
                # 级联删除子版本（同时解除文件关联）
                for version in episode_versions:
                    # 解除文件关联
                    session.exec(
                        f"UPDATE file_asset SET version_id = NULL, updated_at = '{datetime.now()}' WHERE version_id = {version.id} AND user_id = {user_id}"
                    )
                    # 删除版本
                    session.delete(version)
                # 删除季版本
                season_version = session.exec(select(MediaVersion).where(MediaVersion.id == season_version_id)).first()
                if season_version:
                    session.delete(season_version)
                logger.info(f"批量删除季版本{season_version_id}及下属{len(episode_versions)}个单集版本")

            elif operation == "set_preferred":
                # 将季版本设为首选，同时将下属所有单集版本设为首选
                season_version = session.exec(select(MediaVersion).where(MediaVersion.id == season_version_id)).first()
                if season_version:
                    season_version.preferred = True
                    season_version.updated_at = datetime.now()
                for version in episode_versions:
                    version.preferred = True
                    version.updated_at = datetime.now()
                logger.info(f"批量将季版本{season_version_id}及下属{len(episode_versions)}个单集版本设为首选")

            session.flush()
            return True
        except Exception as e:
            logger.error(f"批量操作季版本失败：{str(e)}", exc_info=True)
            return False


    
    # ==================== 持久化元数据方法 ====================
    # def _upsert_artworks(self, session, user_id: int, core_id: int, provider: Optional[str], artworks) -> None:
    #     try:
    #         if artworks:
    #             for a in artworks:
    #                 # 支持 dict 和 dataclass：先尝试 dict.get，再用 getattr
    #                 a_type = self._get_attr(a, "type")
    #                 # 处理 Enum 类型：如果是 Enum，取其 value；如果已是字符串，直接使用
    #                 if hasattr(a_type, "value"):
    #                     _t = a_type.value
    #                 else:
    #                     _t = a_type
    #                 _t = "still" if _t == "thumb" else _t
    #                 by_type = session.exec(select(Artwork).where(
    #                     Artwork.user_id == user_id,
    #                     Artwork.core_id == core_id,
    #                     Artwork.type == _t
    #                 )).first()
    #                 if by_type:
    #                     try:
    #                         if not getattr(by_type, "remote_url", None):
    #                             by_type.remote_url = self._get_attr(a, "url")
    #                     except Exception:
    #                         by_type.remote_url = self._get_attr(a, "url")
    #                     by_type.provider = provider
    #                     by_type.language = self._get_attr(a, "language") or getattr(by_type, "language", None)
    #                     by_type.preferred = getattr(by_type, "preferred", False)
    #                     # by_type.exists_remote = True
    #                 else:
    #                     session.add(Artwork(user_id=user_id, core_id=core_id, type=_t, remote_url=self._get_attr(a, "url"), local_path=None, provider=provider, language=self._get_attr(a, "language"), preferred=False, exists_local=False))
    #     except Exception:
    #         pass

    def _upsert_artworks(self, session, user_id: int, core_id: int, provider: Optional[str], artworks) -> None:
        if not artworks:  # 空列表直接返回，避免无效循环
            return

        for artwork in artworks:
            try:
                # 1. 提取Artwork的核心属性（支持dict/dataclass）
                a_type = self._get_attr(artwork, "type")
                a_url = self._get_attr(artwork, "url")
                a_language = self._get_attr(artwork, "language")
                a_preferred = self._get_attr(artwork, "is_primary") is True  # 默认为False
                a_width = self._get_attr(artwork, "width")
                a_height = self._get_attr(artwork, "height")
                

                # 处理ArtworkType枚举（转为字符串value）
                _t = a_type.value if hasattr(a_type, "value") else a_type
                if not _t or not a_url:  # 类型/URL为空时跳过（避免无效数据）
                    continue

                # 2. 拆分“首选”和“非首选”逻辑处理
                if a_preferred:
                    # --------------------------
                    # 首选Artwork：同类型下仅允许1张
                    # --------------------------
                    # 步骤1：先将该类型下所有已有“首选”设为“非首选”（保证唯一首选）
                    existing_preferred = session.exec(
                        select(Artwork).where(
                            Artwork.user_id == user_id,
                            Artwork.core_id == core_id,
                            Artwork.type == _t,
                            Artwork.preferred == True
                        )
                    ).all()
                    for ep in existing_preferred:
                        ep.preferred = False

                    # 步骤2：查询是否已有“同类型+同URL”的记录（可能之前是非首选）
                    existing = session.exec(
                        select(Artwork).where(
                            Artwork.user_id == user_id,
                            Artwork.core_id == core_id,
                            Artwork.type == _t,
                            Artwork.remote_url == a_url
                        )
                    ).first()

                    if existing:
                        # 更新已有记录为“首选”，并同步其他字段
                        existing.preferred = True
                        existing.provider = provider or existing.provider
                        existing.language = a_language or existing.language
                        existing.width = a_width or existing.width
                        existing.height = a_height or existing.height
                       
                    else:
                        # 新增首选记录
                        session.add(Artwork(
                            user_id=user_id,
                            core_id=core_id,
                            type=_t,
                            remote_url=a_url,
                            local_path=None,
                            provider=provider,
                            language=a_language,
                            preferred=True,
                            exists_local=False,
                            width=a_width,
                            height=a_height,
                            
                        ))

                else:
                    # --------------------------
                    # 非首选Artwork：按“类型+URL”唯一标识（支持多图）
                    # --------------------------
                    # 步骤1：查询是否已有“同类型+同URL”的非首选记录（避免重复）
                    existing = session.exec(
                        select(Artwork).where(
                            Artwork.user_id == user_id,
                            Artwork.core_id == core_id,
                            Artwork.type == _t,
                            Artwork.remote_url == a_url,
                            Artwork.preferred == False  # 仅匹配非首选
                        )
                    ).first()

                    if existing:
                        # 更新已有非首选记录的字段（如语言、评分等可能变化）
                        existing.provider = provider or existing.provider
                        existing.language = a_language or existing.language
                        existing.width = a_width or existing.width
                        existing.height = a_height or existing.height
                        
                    else:
                        # 新增非首选记录（不影响其他非首选）
                        session.add(Artwork(
                            user_id=user_id,
                            core_id=core_id,
                            type=_t,
                            remote_url=a_url,
                            local_path=None,
                            provider=provider,
                            language=a_language,
                            preferred=False,
                            exists_local=False,
                            width=a_width,
                            height=a_height,
                           
                        ))

            except Exception as e:
                # 细化异常捕获，避免吞掉所有错误（建议添加日志）
                print(f"处理Artwork失败（URL: {a_url}）：{str(e)}")
                # 如需回滚局部错误：session.rollback()
                pass 
    
    def _upsert_credits(self, session, user_id: int, core_id: int, credits, provider: Optional[str]) -> None:
        # logger.info(f"开始处理Credits，共 {len(credits)} 条记录")
        if not credits:
            return
        
        for c in credits:
            if not c:
                continue

            name = self._get_attr(c, "name")
            original_name = self._get_attr(c, "original_name")
            provider_id = self._get_attr(c, "provider_id")
            purl = self._get_attr(c, "image_url")
            if not name:
                continue
            person = session.exec(select(Person).where(Person.provider_id == provider_id, Person.name == name,Person.provider == provider)).first()
            if not person:       
                person = Person(provider=provider, provider_id=provider_id, name=name,original_name=original_name, profile_url=purl)
                session.add(person)
                session.flush()
            else:
                try:
                    
                    person.original_name = original_name or person.original_name
                    if not getattr(person, "profile_url", None) and purl:
                        person.profile_url = purl
                except Exception as e:
                    logger.error(f"更新Person profile_url失败: {e}", exc_info=True)
                    pass
            # 处理 Enum 类型：如果是 Enum，取其 value；如果已是字符串，直接使用
            c_type = self._get_attr(c, "type")
            if hasattr(c_type, "value"):
                role_type = c_type.value
            else:
                role_type = c_type
            role = "cast" if role_type == "actor" else "crew"
            role = "guest" if self._get_attr(c, "is_flying") else role


            character = self._get_attr(c, "character") if role == "cast" else None # 演员角色名称,导演就是"Director"
            job = role_type # actor/director/writer
            order = self._get_attr(c, "order")
            existing = session.exec(select(Credit).where(
                Credit.user_id == user_id,
                Credit.core_id == core_id,
                Credit.person_id == person.id,
                Credit.role == role,
                Credit.job == job,
                # Credit.order == order
            )).first()
            if not existing:
                session.add(Credit(user_id=user_id, core_id=core_id, person_id=person.id, role=role, character=character, job=job, order=order))
                session.flush()
            else:
                existing.role = role
                existing.character = character
                existing.job = job
                existing.order = order
             
    def _upsert_genres(self, session, user_id: int, core_id: int, genres) -> None:
        try:
            for genre_name in genres or []:
                if not genre_name or "&" in genre_name:
                    continue
                genre = session.exec(select(Genre).where(Genre.name == genre_name)).first()
                if not genre:
                    genre = Genre(name=genre_name)
                    session.add(genre)
                    session.flush()
                existing_link = session.exec(select(MediaCoreGenre).where(MediaCoreGenre.user_id == user_id, MediaCoreGenre.core_id == core_id, MediaCoreGenre.genre_id == genre.id)).first()
                if not existing_link:
                    session.add(MediaCoreGenre(user_id=user_id, core_id=core_id, genre_id=genre.id))
        except Exception:
            pass
    
    def _upsert_external_ids(self, session, user_id: int, core_id: int, external_ids) -> None:
        try:
            if not external_ids:
                return
            
            for eid in external_ids:
                if not eid:
                    continue
                # 3. 用self._get_attr兼容dict和_DictWrapper/对象（代替eid.get()）
                provider = self._get_attr(eid, "provider")  # 无默认值，不存在则返回None
                external_id = self._get_attr(eid, "external_id")  # 原始外部ID（未转str）

                # 4. 过滤无效数据（provider为空或external_id为空）
                if not provider or external_id is None:
                    logger.debug(f"跳过无效外部ID（provider={provider}, external_id={external_id}）")
                    continue

                external_id = str(external_id)

                existing = session.exec(select(ExternalID).where(
                    ExternalID.user_id == user_id,
                    ExternalID.core_id == core_id,
                    ExternalID.source == provider,
                    # ExternalID.key == external_id
                )).first()
                if not existing:
                    session.add(ExternalID(user_id=user_id, core_id=core_id, source=provider, key=external_id))
                    session.flush()
                else:
                    existing.key = external_id
                # 更新核心表的tmdb_id
                if provider == 'tmdb':
                    media_core = session.exec(select(MediaCore).where(MediaCore.user_id == user_id, MediaCore.id == core_id)).first()
                    if media_core :
                        media_core.tmdb_id = external_id 
                        
        except Exception as e:
            logger.error(f"更新ExternalIDs失败: {e}", exc_info=True)
            pass
    
    def _check_series_type(self, type: str, genres: List[str]) -> str:
        """判断系列类型(TV/Animation/Reality)"""
        if type:
            if type.lower() in ["reality", "variety", "真人秀"]:
                return "Reality"
            elif type.lower() in ["animation", "动画"]:
                return "Animation"
        if genres :
            for genre in genres:
                # logger.info(f"检查genres决定类型: {genre}")
                # genre_name = genre.get("name", "").lower()
                if genre.lower() in ["动画", "animation"]:
                    return "Animation"
                if genre.lower() in ["真人秀", "reality", "variety"]:
                    return "Reality"
        return "TV"
        
    def _apply_series_detail(self, session, user_id: int, sd: ScraperSeriesDetail) -> MediaCore:
        name_val = getattr(sd, "name", None) or getattr(sd, "original_name", None) or ""
        genres = getattr(sd, "genres", []) or [] 
        type_val = getattr(sd, "type", None)  # Scripted|Reality(Variety)|Animation|Documentary|News|Talk Show|Other
        # try:
        #     has_animation = False
        #     if genres and type_val != "Animation":
        #         for genre in genres:
        #             logger.info(f"检查类型动画: {genre}")
        #             # genre_name = genre.get("name", "").lower()
        #             if genre.lower() in ["动画", "animation"]:
        #                 has_animation = True
        #                 break
        #     # 扩展动画类型
        #     type_val = "Animation" if has_animation else type_val 
        # except Exception as e:
        #     logger.error(f"Error checking animation type: {e}")
        #     pass  
        try:
            type_val = self._check_series_type(type_val, genres)
        except Exception as e:
            logger.error(f"系类类型判断出错: {e}")
            type_val = "TV"

        year_val = None
        try:
            dt = self._parse_dt(getattr(sd, "first_air_date", None))
            year_val = dt.year if dt else None
        except Exception:
            year_val = None
        series_core = session.exec(select(MediaCore).where(
            MediaCore.user_id == user_id,
            MediaCore.kind == "series",
            MediaCore.title == name_val,
            MediaCore.tmdb_id == getattr(sd, "series_id", None) if getattr(sd, "provider", None) == "tmdb" else None  
        )).first()
        
        if not series_core:
            series_core = MediaCore(
                user_id=user_id,
                kind="series",
                title=name_val,
                original_title=getattr(sd, "original_name", None),
                year=year_val,
                plot=getattr(sd, "overview", None),
                display_rating=getattr(sd, "vote_average", None),
                display_poster_path=getattr(sd, "poster_path", None),
                display_date=self._parse_dt(getattr(sd, "first_air_date", None)),
                subtype=type_val,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(series_core)
            session.flush()
        else:
            series_core.kind = "series"
            series_core.title = name_val
            series_core.original_title = getattr(sd, "original_name", None)
            series_core.year = year_val
            series_core.plot = getattr(sd, "overview", None)
            series_core.display_rating = getattr(sd, "vote_average", None)
            series_core.display_poster_path = getattr(sd, "poster_path", None)
            series_core.display_date = self._parse_dt(getattr(sd, "first_air_date", None))
            series_core.subtype = type_val
            series_core.updated_at = datetime.now()
            # 或者直接不更新，直接返回
        # try:
        #     if getattr(sd, "provider", None) and getattr(sd, "series_id", None):
        #         existing = session.exec(select(ExternalID).where(
        #             ExternalID.user_id == user_id,
        #             ExternalID.core_id == series_core.id,
        #             ExternalID.source == sd.provider,
        #             ExternalID.key == str(sd.series_id)
        #         )).first()
        #         if not existing:
        #             session.add(ExternalID(user_id=user_id, core_id=series_core.id, source=sd.provider, key=str(sd.series_id)))
        #             session.flush()
        #         series_core.canonical_source = series_core.canonical_source or sd.provider
        #         series_core.canonical_external_key = series_core.canonical_external_key or str(sd.series_id)
        #         try:
        #             if sd.provider == "tmdb":
        #                 sid = int(str(sd.series_id)) if str(sd.series_id).isdigit() else None
        #                 if sid is not None:
        #                     series_core.tmdb_id = series_core.tmdb_id or sid
        #         except Exception:
        #             pass
        # except Exception:
        #     pass

        
        
        tv_ext = session.exec(select(SeriesExt).where(SeriesExt.core_id == series_core.id, SeriesExt.user_id == user_id)).first()
        if not tv_ext:
            tv_ext = SeriesExt(user_id=user_id, core_id=series_core.id)
            session.add(tv_ext)
        try:
            tv_ext.title = name_val or tv_ext.title
            tv_ext.overview = getattr(sd, "overview", None) or tv_ext.overview
            tv_ext.season_count = getattr(sd, "number_of_seasons", None)
            tv_ext.episode_count = getattr(sd, "number_of_episodes", None)
            rt = getattr(sd, "episode_run_time", None)
            if isinstance(rt, list) and len(rt) > 0:
                tv_ext.episode_run_time = int(rt[0]) if isinstance(rt[0], (int, float)) else None
            tv_ext.status = getattr(sd, "status", None)
            tv_ext.rating = getattr(sd, "vote_average", None)
            tv_ext.origin_country = list(getattr(sd, "origin_country", []) or [])
            try:
                fd = getattr(sd, "first_air_date", None)
                ld = getattr(sd, "last_air_date", None)
                tv_ext.aired_date = self._parse_dt(fd) if fd else tv_ext.aired_date
                tv_ext.last_aired_date = self._parse_dt(ld) if ld else tv_ext.last_aired_date
            except Exception:
                pass
            tv_ext.poster_path = getattr(sd, "poster_path", None) or tv_ext.poster_path
            tv_ext.backdrop_path = getattr(sd, "backdrop_path", None) or tv_ext.backdrop_path
            tv_ext.series_type = type_val or tv_ext.series_type
            raw_data = getattr(sd, 'raw_data', None)
            if isinstance(raw_data, _DictWrapper):
                raw_data = raw_data._data
            tv_ext.raw_data = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
        except Exception:
            pass
        # try:
        #     if getattr(tv_ext, "poster_path", None):
        #         art_p = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == series_core.id, Artwork.type == "poster", Artwork.preferred==True)).first()
        #         if not art_p:
        #             session.add(Artwork(user_id=user_id, core_id=series_core.id, type="poster", remote_url=tv_ext.poster_path, provider=getattr(sd, "provider", None), preferred=True))
        #         else:
        #             art_p.remote_url = art_p.remote_url or tv_ext.poster_path
        #             art_p.provider = getattr(sd, "provider", None) or getattr(art_p, "provider", None)
        #             art_p.preferred = True
        #             # art_p.exists_remote = True
        #     if getattr(tv_ext, "backdrop_path", None):
        #         art_b = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == series_core.id, Artwork.type == "backdrop", Artwork.preferred==True)).first()
        #         if not art_b:
        #             session.add(Artwork(user_id=user_id, core_id=series_core.id, type="backdrop", remote_url=tv_ext.backdrop_path, provider=getattr(sd, "provider", None), preferred=True))
        #         else:
        #             art_b.remote_url = art_b.remote_url or tv_ext.backdrop_path
        #             art_b.provider = getattr(sd, "provider", None) or getattr(art_b, "provider", None)
        #             art_b.preferred = True
        #             # art_b.exists_remote = True
        # except Exception:
        #     pass
        try:
            self._upsert_genres(session, user_id, series_core.id, getattr(sd, "genres", []) or [])
        except Exception as e:
            logger.error(f"更新剧集流派失败: {e}")
            pass
        try:
            self._upsert_artworks(session, user_id, series_core.id, getattr(sd, "provider", None), getattr(sd, "artworks", None))
        except Exception as e:
            logger.error(f"更新剧集海报失败: {e}")
            pass
        # try:
        #     self._upsert_credits(session, user_id, series_core.id, getattr(sd, "credits", None), getattr(sd, "provider", None))
        # except Exception as e:
        #     logger.error(f"更新剧集演员失败: {e}")
        #     pass
        try:
            self._upsert_external_ids(session, user_id, series_core.id, getattr(sd, "external_ids", None))
        except Exception as e:
            logger.error(f"更新剧集外部ID失败: {e}")
            pass
        return series_core
    
    def _apply_season_detail(self, session, user_id: int, series_core: Optional[MediaCore], se: ScraperSeasonDetail) -> MediaCore:
        season_num = getattr(se, "season_number", None) 
        season_name = getattr(se, "name", None)
       
        existing_se = None
        try:
            if series_core:
                existing_se = session.exec(select(SeasonExt).where(SeasonExt.user_id == user_id, SeasonExt.series_core_id == series_core.id, SeasonExt.season_number == season_num)).first()
        except Exception as e:
            logger.error(f"获取剧集详情失败: {e}")
            existing_se = None
        season_core = None
        if existing_se:
            season_core = session.exec(select(MediaCore).where(MediaCore.id == existing_se.core_id)).first()
        if not season_core:
            season_core = session.exec(select(MediaCore).where(
                MediaCore.user_id == user_id,
                MediaCore.kind == "season",
                MediaCore.title == season_name,  #季title不可用，太多重复
                MediaCore.tmdb_id == (getattr(se, "season_id", None) if getattr(se, "season_id", None) else None)
            )).first()

        # 彻底不存在该season
        if not season_core:
            season_core = MediaCore(
                user_id=user_id, 
                kind="season", 
                title=season_name,
                display_date=self._parse_dt(getattr(se, "air_date", None)), 
                display_poster_path=getattr(se, "poster_path", None),
                display_rating=getattr(se, "vote_average", None),
                created_at=datetime.now(), 
                updated_at=datetime.now()
            )
            session.add(season_core)
            session.flush()
        else:
            season_core.kind = "season"
            season_core.title = season_name
            season_core.display_date = self._parse_dt(getattr(se, "air_date", None))
            season_core.display_poster_path = getattr(se, "poster_path", None)
            season_core.display_rating = getattr(se, "vote_average", None)
            season_core.updated_at = datetime.now()
            # 直接返回或者可以更新已有的数据（我认为可以不更新，减少数据库操作）

        se_ext = session.exec(select(SeasonExt).where(
            # SeasonExt.core_id == season_core.id,
            SeasonExt.series_core_id == (series_core.id if series_core else None),
            SeasonExt.season_number == season_num, 
            SeasonExt.user_id == user_id,
            )).first()
        if not se_ext:
            se_ext = SeasonExt(user_id=user_id, core_id=season_core.id, series_core_id=series_core.id if series_core else None, season_number=season_num)
            session.add(se_ext)
        try:
            se_ext.title = season_name or se_ext.title
            se_ext.overview = getattr(se, "overview", None) or se_ext.overview
            se_ext.episode_count = getattr(se, "episode_count", None)
            se_ext.rating = getattr(se, "vote_average", None)
            ad = getattr(se, "air_date", None)
            se_ext.aired_date = self._parse_dt(ad) if ad else se_ext.aired_date
            se_ext.poster_path = getattr(se, "poster_path", None) or se_ext.poster_path
            
            # 替换原来的 raw_data 赋值行
            raw_data = getattr(se, 'raw_data', None)
            # 如果是 _DictWrapper 类型，获取其内部字典数据
            if isinstance(raw_data, _DictWrapper):
                raw_data = raw_data._data
            # 序列化为JSON字符串
            se_ext.raw_data = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
        except Exception as e:
            logger.error(f"更新剧集详情失败: {e}")
            pass
        # try:
        #     if getattr(se_ext, "poster_path", None):
        #         art_p = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == season_core.id, Artwork.type == "poster", Artwork.preferred==True)).first()
        #         if not art_p:
        #             session.add(Artwork(user_id=user_id, core_id=season_core.id, type="poster", remote_url=se_ext.poster_path, provider=getattr(se, "provider", None), preferred=True))
        #         else:
        #             art_p.remote_url = art_p.remote_url or se_ext.poster_path
        #             art_p.provider = getattr(se, "provider", None) or getattr(art_p, "provider", None)
        #             art_p.preferred = True
        #             # art_p.exists_remote = True
        # except Exception as e:
        #     logger.error(f"更新剧集海报失败: {e}")
        #     pass
        # try:
        #     if getattr(se, "provider", None) and getattr(se, "season_id", None):
        #         existing = session.exec(select(ExternalID).where(
        #             ExternalID.user_id == user_id,
        #             ExternalID.core_id == season_core.id,
        #             ExternalID.source == se.provider,
        #             ExternalID.key == str(se.season_id)
        #         )).first()
        #         if not existing:
        #             session.add(ExternalID(user_id=user_id, core_id=season_core.id, source=se.provider, key=str(se.season_id)))
        #         season_core.canonical_source = season_core.canonical_source or se.provider
        #         season_core.canonical_external_key = season_core.canonical_external_key or str(se.season_id)
        #         try:
        #             if se.provider == "tmdb":
        #                 sid = int(str(se.season_id)) if str(se.season_id).isdigit() else None
        #                 if sid is not None:
        #                     season_core.tmdb_id = season_core.tmdb_id or sid
        #         except Exception as e:
        #             logger.error(f"更新剧集外部ID失败: {e}")
        #             raise
        # except Exception as e:
        #     logger.error(f"更新剧集外部ID失败: {e}")
        #     pass
        try:
            self._upsert_artworks(session, user_id, season_core.id, getattr(se, "provider", None), getattr(se, "artworks", None))
        except Exception as e:
            logger.error(f"更新剧集海报失败: {e}")
            pass
        try:
            self._upsert_credits(session, user_id, season_core.id, getattr(se, "credits", None), getattr(se, "provider", None))
        except Exception as e:
            logger.error(f"更新剧集演员失败: {e}")
            pass
        try:
            self._upsert_external_ids(session, user_id, season_core.id, getattr(se, "external_ids", None))
        except Exception as e:
            logger.error(f"更新剧集外部ID失败: {e}")
            pass
        return season_core
    # 方法入口
    def apply_metadata(self, session, media_file: FileAsset, metadata,metadata_type: str,path_info: Dict) -> None:
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
            - 电视剧分层映射: SeriesExt/SeasonExt/EpisodeExt        
            - 通用映射: Artwork/Genre/MediaCoreGenre/Person/Credit
            - 电影扩展与合集: MovieExt/Collection
        """
        # 如果 metadata 是 dict，包装为可通过 getattr 访问的对象
        if isinstance(metadata, dict):
            metadata = _DictWrapper(metadata)
        
        # core = session.exec(select(MediaCore).where(MediaCore.id == media_file.core_id)).first()
        core = None
        if metadata_type == "movie":
            # logger.info(f"应用电影元数据：文件ID={media_file.id}, 元数据={metadata}")
            core = self._apply_movie_detail(session, media_file, metadata)
 
        elif metadata_type == "episode":
            core = self._apply_episode_detail(session, media_file, metadata)
   
        elif metadata_type == "series":
            core = self._apply_series_detail(session, media_file.user_id, metadata)
            if not self._get_attr(media_file, "core_id"):
                media_file.core_id = core.id
            
        elif metadata_type == "search_result":
            core = self._apply_search_result(session, media_file, metadata)

        else:
            logger.warning(f"不支持的元数据类型: {metadata_type}")
            return
        # 更新文件的路径信息字段
        self._apply_file_path_info(session, media_file, path_info)
        
        # 更新mediacore缓存
        # self._refresh_display_cache_for_core(session, core, media_file.user_id)
        session.flush()

    def _apply_movie_detail(self, session, media_file: FileAsset, metadata: ScraperMovieDetail) -> MediaCore:
        # 添加或更新媒体核心元数据
        core = session.exec(select(MediaCore).where(
            # MediaCore.id == media_file.core_id,
            MediaCore.title == metadata.title,
            MediaCore.kind == "movie",
            MediaCore.user_id == media_file.user_id,
            MediaCore.tmdb_id == getattr(metadata, "movie_id", None) if getattr(metadata, "movie_id", None) else None
            )).first()
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
            logger.info(f"电影中更新了media_file.core_id: {core.id} for file: {media_file.id}")

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
            media_file.core_id = core.id
        
        # 改元信息提供商ID
        # if getattr(metadata, "provider", None) and getattr(metadata, "movie_id", None):
        #     existing = session.exec(select(ExternalID).where(
        #         ExternalID.user_id == media_file.user_id,
        #         ExternalID.core_id == core.id,
        #         ExternalID.source == metadata.provider,
        #         ExternalID.key == str(metadata.movie_id)
        #     )).first()
        #     if not existing:
        #         session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=metadata.provider, key=str(metadata.movie_id)))
        #         session.flush()
        #     core.canonical_source = core.canonical_source or metadata.provider
        #     core.canonical_external_key = core.canonical_external_key or str(metadata.movie_id)
        #     try:
        #         if metadata.provider == "tmdb":
        #             mid = int(str(metadata.movie_id)) if str(metadata.movie_id).isdigit() else None
        #             if mid is not None:
        #                 core.tmdb_id = core.tmdb_id or mid
        #     except Exception:
        #         pass

        # 外部平台信息列表（tmdb，imdb）
        # try:
        #     for eid in getattr(metadata, "external_ids", []) or []:
        #         if not eid or not getattr(eid, "provider", None) or not getattr(eid, "external_id", None):
        #             continue
        #         existing = session.exec(select(ExternalID).where(
        #             ExternalID.user_id == media_file.user_id,
        #             ExternalID.core_id == core.id,
        #             ExternalID.source == eid.provider,
        #             ExternalID.key == str(eid.external_id)
        #         )).first()
        #         if not existing:
        #             session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=eid.provider, key=str(eid.external_id)))
        # except Exception:
        #     pass
        # 电影详细信息
        movie_ext = session.exec(select(MovieExt).where(MovieExt.user_id == media_file.user_id, MovieExt.core_id == core.id)).first()
        if not movie_ext:
            movie_ext = MovieExt(user_id=media_file.user_id, core_id=core.id)
            session.add(movie_ext)
            session.flush()
        try:
            movie_ext.tagline = getattr(metadata, "tagline", None)
            movie_ext.title = getattr(metadata, "title", None) or movie_ext.title
            rv = getattr(metadata, "vote_average", None)
            movie_ext.rating = float(rv) if isinstance(rv, (int, float)) else movie_ext.rating
            movie_ext.overview = getattr(metadata, "overview", None) or movie_ext.overview
            movie_ext.origin_country = list(getattr(metadata, "origin_country", []))
            # logger.info(f"原国家: {getattr(metadata, 'origin_country', None)}")

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
            movie_ext.runtime_minutes = getattr(metadata, "runtime", None) or movie_ext.runtime_minutes
            movie_ext.status = getattr(metadata, "status", None) or movie_ext.status
            
            # 替换原来的 raw_data 赋值行
            raw_data = getattr(metadata, 'raw_data', None)
            # 如果是 _DictWrapper 类型，获取其内部字典数据
            if isinstance(raw_data, _DictWrapper):
                raw_data = raw_data._data
            # 序列化为JSON字符串
            movie_ext.raw_data = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
           
        except Exception as e:
            logger.info(f"电影原始数据转换失败errer:{str(e)}")
            pass
        try:
            col = getattr(metadata, "belongs_to_collection", None)
            if isinstance(col, dict) and col.get("id"):
                collection = session.exec(select(Collection).where(Collection.id == col.get("id"))).first()
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
        # try:
        #     ppath = getattr(metadata, "poster_path", None)
        #     bpath = getattr(metadata, "backdrop_path", None)
        #     prov = getattr(metadata, "provider", None)
        #     if ppath:
        #         art_p = session.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "poster", Artwork.preferred==True)).first()
        #         if not art_p:
        #             session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="poster", remote_url=ppath, provider=prov, preferred=True))
        #         else:
        #             art_p.remote_url = art_p.remote_url or ppath
        #             art_p.provider = prov or getattr(art_p, "provider", None)
        #             art_p.preferred = True
        #         #     art_p.exists_remote = True
        #     if bpath:
        #         art_b = session.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "backdrop", Artwork.preferred==True)).first()
        #         if not art_b:
        #             session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="backdrop", remote_url=bpath, provider=prov, preferred=True))
        #         else:
        #             art_b.remote_url = art_b.remote_url or bpath
        #             art_b.provider = prov or getattr(art_b, "provider", None)
        #             art_b.preferred = True
        # except Exception:
        #     pass
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
        
        try:
            self._upsert_external_ids(session, media_file.user_id, core.id, getattr(metadata, "external_ids", None))
        except Exception:
            pass
        
        # 7. 核心逻辑：创建/更新版本，并关联文件到版本
        version_id = self._upsert_media_version(session, media_file, core, metadata)
        media_file.version_id = version_id  # 文件关联版本
        media_file.updated_at = datetime.now()

        return core

    def _refresh_display_cache_for_core(self, session, core: MediaCore, user_id: int) -> None:
        try:
            if core.kind == 'movie':
                mx = session.exec(select(MovieExt).where(MovieExt.core_id == core.id, MovieExt.user_id == user_id)).first()
                if mx:
                    core.display_rating = getattr(mx, 'rating', None)
                    core.display_poster_path = getattr(mx, 'poster_path', None)
                    core.display_date = getattr(mx, 'release_date', None)
            elif core.kind == 'series':
                tv = session.exec(select(SeriesExt).where(SeriesExt.core_id == core.id, SeriesExt.user_id == user_id)).first()
                if tv:
                    core.display_rating = getattr(tv, 'rating', None)
                    core.display_poster_path = getattr(tv, 'poster_path', None)
                se_first = session.exec(select(SeasonExt).where(SeasonExt.series_core_id == core.id).order_by(SeasonExt.season_number)).first()
                if se_first and getattr(se_first, 'aired_date', None):
                    core.display_date = se_first.aired_date
                    try:
                        core.year = se_first.aired_date.year
                    except Exception:
                        pass
                if tv and getattr(tv, 'rating', None) is not None and core.display_rating is None:
                    core.display_rating = tv.rating
            elif core.kind == 'season':
                se = session.exec(select(SeasonExt).where(SeasonExt.core_id == core.id, SeasonExt.user_id == user_id)).first()
                if se:
                    try:
                        if se.series_core_id:
                            series = session.exec(select(MediaCore).where(MediaCore.id == se.series_core_id)).first()
                            if series:
                                core.title = f"{series.title} 第{se.season_number}季"
                    except Exception:
                        pass
                    core.display_rating = getattr(se, 'rating', None)
                    core.display_poster_path = getattr(se, 'poster_path', None)
                    core.display_date = getattr(se, 'aired_date', None)
            elif core.kind == 'episode':
                ep = session.exec(select(EpisodeExt).where(EpisodeExt.core_id == core.id, EpisodeExt.user_id == user_id)).first()
                if ep:
                    core.title = ep.title or core.title
                    core.display_rating = getattr(ep, 'rating', None)
                    core.display_poster_path = None
                    core.display_date = getattr(ep, 'aired_date', None)
        except Exception:
            pass

    def _apply_episode_detail(self, session, media_file: FileAsset, metadata: ScraperEpisodeDetail) -> MediaCore:
        series_core = None
        season_core = None
        season_version_id = None
        title_val = getattr(metadata, "name", None) or ""
        try:
            if getattr(metadata, "series", None):
                series_core = self._apply_series_detail(session, media_file.user_id, metadata.series)
            if getattr(metadata, "season", None) and series_core:
                season_core = self._apply_season_detail(session, media_file.user_id, series_core, metadata.season)
                # 新增：创建/更新季版本（基于文件父文件夹路径）
                season_version_id = self._upsert_season_version(session, media_file, season_core)
        except Exception as e:
            logger.error(f"创建/更新季版本失败: {e}", exc_info=True)
            pass
        episode_core = session.exec(select(MediaCore).where(
            # MediaCore.id == media_file.core_id,
            MediaCore.user_id == media_file.user_id,
            MediaCore.kind == "episode",
            MediaCore.title == title_val,
            MediaCore.tmdb_id == getattr(metadata, "episode_id", None) if getattr(metadata, "episode_id", None) else None
            )).first()

        if not episode_core:
            
            episode_core = MediaCore(
                user_id=media_file.user_id,
                kind="episode",
                title=title_val,
                original_title=None,
                year=None,
                plot=getattr(metadata, "overview", None),
                display_rating=getattr(metadata, "vote_average", None),
                display_poster_path=getattr(metadata, "still_path", None),
                display_date=self._parse_dt(getattr(metadata, "air_date", None)),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(episode_core)
            session.flush()
            media_file.core_id = episode_core.id
            logger.info(f"集中更新了media_file.core_id: {episode_core.id} for file: {media_file.id}")
        else:
            episode_core.kind = "episode"
            episode_core.title = title_val or episode_core.title
            episode_core.plot = getattr(metadata, "overview", None) or episode_core.plot
            episode_core.display_rating = getattr(metadata, "vote_average", None)
            episode_core.display_poster_path = getattr(metadata, "still_path", None)
            episode_core.display_date = self._parse_dt(getattr(metadata, "air_date", None))
            episode_core.updated_at = datetime.now()
            media_file.core_id = episode_core.id
        ep_ext = session.exec(select(EpisodeExt).where(
            # EpisodeExt.core_id == episode_core.id, 
            EpisodeExt.user_id == media_file.user_id,
            # EpisodeExt.series_core_id == (series_core.id if series_core else None),
            EpisodeExt.series_core_id == series_core.id if series_core else EpisodeExt.series_core_id,
            EpisodeExt.season_number == getattr(metadata, "season_number", 1),
            EpisodeExt.episode_number == getattr(metadata, "episode_number", 1)
            )).first()
        if not ep_ext:
            ep_ext = EpisodeExt(
                user_id=media_file.user_id, 
                core_id=episode_core.id, 
                series_core_id=series_core.id if series_core else None, 
                season_core_id=season_core.id if season_core else None, 
                episode_number=getattr(metadata, "episode_number", None) or 1, 
                season_number=getattr(metadata, "season_number", None) or 1
                )
            session.add(ep_ext)
        try:
            ep_ext.core_id = episode_core.id # 记录存在但是需要关联到新core_id
            ep_ext.title = title_val or ep_ext.title
            ep_ext.overview = getattr(metadata, "overview", None) or ep_ext.overview
            ep_ext.runtime = getattr(metadata, "runtime", None)
            ep_ext.rating = getattr(metadata, "vote_average", None)
            ep_ext.vote_count = getattr(metadata, "vote_count", None)
            ep_ext.still_path = getattr(metadata, "still_path", None)
            ep_ext.episode_type = getattr(metadata, "episode_type", None)
            ad = getattr(metadata, "air_date", None)
            ep_ext.aired_date = self._parse_dt(ad) if ad else ep_ext.aired_date
        except Exception as e:
            logger.error(f"更新EpisodeExt失败: {e}", exc_info=True)
            pass
        # try:
        #     if getattr(ep_ext, "still_path", None):
        #         art_s = session.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == episode_core.id, Artwork.type == "still", Artwork.preferred==True)).first()
        #         if not art_s:
        #             session.add(Artwork(user_id=media_file.user_id, core_id=episode_core.id, type="still", remote_url=ep_ext.still_path, provider=getattr(metadata, "provider", None), preferred=True))
        #         else:
        #             art_s.remote_url = art_s.remote_url or ep_ext.still_path
        #             art_s.provider = getattr(metadata, "provider", None) or getattr(art_s, "provider", None)
        #             art_s.preferred = True
        #             # art_s.exists_remote = True
        # except Exception:
        #     pass
        # try:
        #     if getattr(metadata, "provider", None) and getattr(metadata, "episode_id", None):
        #         existing = session.exec(select(ExternalID).where(
        #             ExternalID.user_id == media_file.user_id,
        #             ExternalID.core_id == episode_core.id,
        #             ExternalID.source == metadata.provider,
        #             ExternalID.key == str(metadata.episode_id)
        #         )).first()
        #         if not existing:
        #             session.add(ExternalID(user_id=media_file.user_id, core_id=episode_core.id, source=metadata.provider, key=str(metadata.episode_id)))
                
        #         episode_core.canonical_source = episode_core.canonical_source or metadata.provider
        #         episode_core.canonical_external_key = episode_core.canonical_external_key or str(metadata.episode_id)
        #         try:
        #             if metadata.provider == "tmdb":
        #                 sid = int(metadata.episode_id) if str(metadata.episode_id).isdigit() else None
        #                 if sid is not None:
        #                     episode_core.tmdb_id = episode_core.tmdb_id or sid
        #         except Exception:
        #             pass
        # except Exception as e:
        #     logger.error(f"应用剧集外部ID失败：{str(e)}", exc_info=True)
        #     pass
        try:
            self._upsert_artworks(session, media_file.user_id, episode_core.id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
        except Exception as e:
            logger.error(f"应用剧集封面失败：{str(e)}", exc_info=True)
            pass
        try:
            self._upsert_credits(session, media_file.user_id, episode_core.id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
        except Exception as e:
            logger.error(f"应用剧集演员失败：{str(e)}", exc_info=True)
            pass
        
        try:
            self._upsert_external_ids(session, media_file.user_id, episode_core.id, getattr(metadata, "external_ids", None))
        except Exception as e:
            logger.error(f"应用剧集外部ID失败：{str(e)}", exc_info=True)
            pass
        
        
        # 7. 核心逻辑：创建/更新单集子版本，并关联到季版本
        # 传入season_version_id，让单集版本关联到季版本
        version_id = self._upsert_media_version(session, media_file, episode_core, metadata, season_version_id)
        media_file.version_id = version_id  # 文件关联单集版本
        media_file.season_version_id = season_version_id  # 文件关联季版本
        media_file.updated_at = datetime.now()

        return episode_core

    def _apply_search_result(self, session, media_file: FileAsset, metadata: ScraperSearchResult) -> MediaCore:
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
        # try:
        #     prov = getattr(metadata, "provider", None)
        #     pid = getattr(metadata, "id", None)
        #     if prov and pid:
        #         existing = session.exec(select(ExternalID).where(
        #             ExternalID.user_id == media_file.user_id,
        #             ExternalID.core_id == core.id,
        #             ExternalID.source == prov,
        #             ExternalID.key == str(pid)
        #         )).first()
        #         if not existing:
        #             session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=prov, key=str(pid)))
        #             session.flush()
        #         core.canonical_source = core.canonical_source or prov
        #         core.canonical_external_key = core.canonical_external_key or str(pid)
        #         if prov == "tmdb" and str(pid).isdigit():
        #             core.tmdb_id = core.tmdb_id or int(str(pid))
        # except Exception:
        #     pass
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

    def _apply_file_path_info(self, session, media_file: FileAsset, path_info: Dict) -> None:
        """
        应用文件路径信息到领域模型

        事务说明:
            1. 更新文件的路径信息字段
        """
        # 1. 更新文件的路径信息字段
        media_file.resolution = media_file.resolution or path_info.get("screen_size")
        media_file.frame_rate = media_file.frame_rate or path_info.get("frame_rate")
        media_file.mimetype = media_file.mimetype or path_info.get("mimetype")
        media_file.video_codec = media_file.video_codec or path_info.get("video_codec")
        media_file.audio_codec = media_file.audio_codec or path_info.get("audio_codec")
        media_file.container = media_file.container or path_info.get("container")
        media_file.updated_at = datetime.now()

persistence_service = MetadataPersistenceService()
