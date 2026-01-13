import logging
import json
import os
import hashlib
import random
from datetime import datetime
from re import L
from typing import Optional, Dict, Any, List

from sqlmodel import Session, select, update, func
from sqlalchemy.dialects.postgresql import insert # <-- 关键导入

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
    def __init__(self):
      
        # 1. 架构优化：定义处理函数分发器
        self._metadata_handlers = {
            "movie": self._apply_movie_detail,
            "episode": self._apply_episode_detail,
            # "series": self._apply_series_detail,
            # "search_result": self._apply_search_result,
        }

    def _get_handler(self, metadata_type: str):
        """安全地获取处理函数，如果类型不支持则返回 None"""
        return self._metadata_handlers.get(metadata_type)
    
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

    def _cleanup_orphan_versions_after_rebind(
        self,
        session: Session,
        user_id: int,
        old_version_id: Optional[int],
        new_version_id: Optional[int],
        old_season_version_id: Optional[int],
        new_season_version_id: Optional[int],
    ) -> None:
        if old_version_id and old_version_id != new_version_id:
            cnt = session.exec(
                select(func.count(FileAsset.id)).where(
                    FileAsset.user_id == user_id,
                    FileAsset.version_id == old_version_id,
                )
            ).one()
            if int(cnt or 0) == 0:
                v = session.get(MediaVersion, old_version_id)
                if v and getattr(v, "user_id", None) == user_id:
                    session.delete(v)

        if old_season_version_id and old_season_version_id != new_season_version_id:
            season_cnt = session.exec(
                select(func.count(FileAsset.id)).where(
                    FileAsset.user_id == user_id,
                    FileAsset.season_version_id == old_season_version_id,
                )
            ).one()
            if int(season_cnt or 0) == 0:
                children = session.exec(
                    select(MediaVersion).where(
                        MediaVersion.user_id == user_id,
                        MediaVersion.parent_version_id == old_season_version_id,
                    )
                ).all()
                for child in children or []:
                    child_id = getattr(child, "id", None)
                    if not child_id:
                        continue
                    child_cnt = session.exec(
                        select(func.count(FileAsset.id)).where(
                            FileAsset.user_id == user_id,
                            FileAsset.version_id == child_id,
                        )
                    ).one()
                    if int(child_cnt or 0) == 0:
                        session.delete(child)

                if hasattr(session, "flush"):
                    session.flush()

                remaining_children = session.exec(
                    select(func.count(MediaVersion.id)).where(
                        MediaVersion.user_id == user_id,
                        MediaVersion.parent_version_id == old_season_version_id,
                    )
                ).one()
                if int(remaining_children or 0) == 0:
                    sv = session.get(MediaVersion, old_season_version_id)
                    if sv and getattr(sv, "user_id", None) == user_id:
                        session.delete(sv)

    # ==================== 版本管理核心辅助方法 ====================   
    def _parse_dt(self, v) -> tuple[Optional[datetime],Optional[int]]:
        """
        将日期值解析为 datetime 对象
        
        参数:
            v: 支持 datetime 或 YYYY-MM-DD 字符串
        返回:
            (datetime,year) 或 (None,None)（解析失败返回 None）
        """
        if not v:
            return None,None
        try:
            from datetime import datetime as _dt
            if isinstance(v, _dt):
                return v,v.year
            if isinstance(v, str) and v:
                return _dt.strptime(v[:10], "%Y-%m-%d"),_dt.strptime(v[:10], "%Y-%m-%d").year
        except Exception:
            return None,None
        return None,None

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
        文件来源存储类型（从存储配置中提取）
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
    
    # region _upsert_season_version
    # def _upsert_season_version(self, session, media_file: FileAsset, season_core: MediaCore) -> int:
    #     """
    #     创建/更新季版本（season_group）
    #     返回：季版本ID
    #     """
    #     # 1. 提取文件父文件夹路径作为季版本的核心标识
    #     season_version_path = self._get_season_version_path(media_file)
    #     # 2. 生成季版本的唯一标签
    #     season_tags = self._generate_season_version_tags(season_version_path, season_core)
    #     # 3. 生成季版本的指纹（基于路径+季核心ID）
    #     fingerprint_str = f"{season_version_path}_{season_core.id}_{media_file.user_id}"
    #     season_fingerprint = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()

    #     # 4. 查询是否已有相同的季版本（用户+季核心+标签唯一）
    #     existing_season_version = session.exec(select(MediaVersion).where(
    #         MediaVersion.user_id == media_file.user_id,
    #         MediaVersion.core_id == season_core.id,
    #         MediaVersion.tags == season_tags,
    #         MediaVersion.scope == "season_group"
    #     )).first()

    #     if existing_season_version:
    #         # 更新现有季版本（补充空字段）
    #         existing_season_version.variant_fingerprint = existing_season_version.variant_fingerprint or season_fingerprint
    #         existing_season_version.updated_at = datetime.now()
    #         existing_season_version.season_version_path = season_version_path  # 更新季版本路径
    #         logger.debug(f"更新季版本: user_id={media_file.user_id}, season_core_id={season_core.id}, version_id={existing_season_version.id}")
    #         return existing_season_version.id
    #     else:
    #         # 检查该季核心是否已有季版本（第一个版本设为首选）
    #         has_existing_season_versions = session.exec(select(MediaVersion).where(
    #             MediaVersion.user_id == media_file.user_id,
    #             MediaVersion.core_id == season_core.id,
    #             MediaVersion.scope == "season_group"
    #         )).first() is not None

    #         # 创建新季版本
    #         new_season_version = MediaVersion(
    #             user_id=media_file.user_id,
    #             core_id=season_core.id,
    #             tags=season_tags,
    #             scope="season_group",  # 标记为季版本作用域
    #             variant_fingerprint=season_fingerprint,
    #             preferred=not has_existing_season_versions,  # 第一个季版本设为首选
    #             primary_file_asset_id=None,  # 季版本无主文件（管理一批单集文件）
    #             parent_version_id=None,  # 季版本无父版本
    #             season_version_path=season_version_path,  # 保存季版本路径
    #             created_at=datetime.now(),
    #             updated_at=datetime.now()
    #         )
    #         session.add(new_season_version)
    #         session.flush()  # 刷新获取ID
    #         logger.debug(f"创建季版本: user_id={media_file.user_id}, season_core_id={season_core.id}, version_id={new_season_version.id}, path={season_version_path}")
    #         return new_season_version.id
    # endregion 这是一段可折叠的注释

    # region  _upsert_media_version
    # def _upsert_media_version(self, session, media_file: FileAsset, core: MediaCore, metadata, season_version_id: Optional[int] = None) -> int:
    #     """
    #     创建/更新媒体版本（支持episode_child关联到season_group，支持movie）
    #     参数：
    #         season_version_id: 可选，季版本ID（仅episode类型需要）
    #     返回：版本ID
    #     """
       

    #     # 2. 确定版本作用域
    #     if core.kind == "movie":
    #         scope = "movie_single"
    #     elif core.kind == "episode":
    #         scope = "episode_child"  # 单集版本标记为子版本
    #     else:
    #         scope = "movie_single"  # 兜底

    #      # 1. 生成版本和指纹关键信息
    #     version_tags,variant_fingerprint = self._get_version_tags_and_fingerprint(media_file,core,scope)
    #     quality = self._get_quality_level(media_file)
    #     edition = self._get_attr(metadata, "edition") or self._get_attr(metadata, "episode_type") or "unknown"
    #     source = self._get_file_source(session, media_file)
        

    #     # 3. 查询是否已有相同版本（用户+核心+标签唯一）
    #     existing_version = session.exec(select(MediaVersion).where(
    #         MediaVersion.user_id == media_file.user_id,
    #         MediaVersion.core_id == core.id,
    #         MediaVersion.tags == version_tags,
    #         MediaVersion.scope == scope
    #     )).first()

    #     if existing_version:
    #         # 更新现有版本
    #         existing_version.quality = existing_version.quality or quality
    #         existing_version.source = existing_version.source or source
    #         existing_version.edition = existing_version.edition or edition
    #         existing_version.variant_fingerprint = existing_version.variant_fingerprint or variant_fingerprint
    #         # 若传入季版本ID，更新父版本关联
    #         if season_version_id:
    #             existing_version.parent_version_id = season_version_id
    #         existing_version.updated_at = datetime.now()
    #         # 补充主文件ID
    #         if not existing_version.primary_file_asset_id:
    #             existing_version.primary_file_asset_id = media_file.id
    #         logger.debug(f"更新{scope}版本: user_id={media_file.user_id}, core_id={core.id}, tags={version_tags}")
    #         return existing_version.id
    #     else:
    #         # 检查该核心是否已有版本（第一个版本设为首选）
    #         has_existing_versions = session.exec(select(MediaVersion).where(
    #             MediaVersion.user_id == media_file.user_id,
    #             MediaVersion.core_id == core.id,
    #             MediaVersion.scope == scope
    #         )).first() is not None

    #         # 创建新版本
    #         new_version = MediaVersion(
    #             user_id=media_file.user_id,
    #             core_id=core.id,
    #             tags=version_tags,
    #             quality=quality,
    #             source=source,
    #             edition=edition,
    #             scope=scope,
    #             variant_fingerprint=variant_fingerprint,
    #             preferred=not has_existing_versions,
    #             primary_file_asset_id=media_file.id,
    #             parent_version_id=season_version_id,  # 关联到季版本（子版本核心）
    #             created_at=datetime.now(),
    #             updated_at=datetime.now()
    #         )
    #         session.add(new_version)
    #         session.flush()
    #         logger.debug(f"创建{scope}版本: user_id={media_file.user_id}, core_id={core.id}, version_id={new_version.id}, parent_version_id={season_version_id}")
    #         return new_version.id
    # endregion 这是一段可折叠的注释
 
    def _upsert_season_version(self, session, media_file: FileAsset, season_core: MediaCore) -> int:
        """
        使用数据库级别的 UPSERT 来原子化地创建/更新季版本，
        完美解决并发问题，并巧妙地处理“首选版本”逻辑。
        """
        
        # 1. 提取和生成关键信息
        season_version_path = self._get_season_version_path(media_file)
        season_tags = self._generate_season_version_tags(season_version_path, season_core)
        fingerprint_str = f"{season_version_path}_{season_core.id}_{media_file.user_id}"
        season_fingerprint = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()
        
        savepoint = session.begin_nested()
        try:
            # --- 2. 原子化 Upsert Season Version ---
            stmt = insert(MediaVersion).values(
                user_id=media_file.user_id,
                core_id=season_core.id,
                tags=season_tags,
                scope="season_group",
                variant_fingerprint=season_fingerprint,
                preferred=True,  # 插入时，默认设为首选
                primary_file_asset_id=None,  # 季版本无主文件
                parent_version_id=None,      # 季版本无父版本
                season_version_path=season_version_path,
                created_at=datetime.now(),
                updated_at=datetime.now()
            ).on_conflict_do_update(
                index_elements=['user_id', 'core_id', 'tags'],  # 与数据库唯一约束匹配
                set_={
                    # 使用 COALESCE 函数实现“如果为空则更新”的逻辑
                    'variant_fingerprint': func.coalesce(MediaVersion.variant_fingerprint, season_fingerprint),
                    # 这些字段总是更新为最新值
                    'season_version_path': season_version_path,
                    'updated_at': datetime.now(),
                    # 注意：'preferred' 字段不在这里，所以冲突时不会被更新，保持其原始状态
                }
            ).returning(MediaVersion.id)

            result = session.execute(stmt)
            version_id = result.scalar_one()

            logger.debug(f"UPSERT 季版本: user_id={media_file.user_id}, season_core_id={season_core.id}, version_id={version_id}, path={season_version_path}")
            # 提交保存点
            savepoint.commit()
            return version_id
        except Exception as e:
            logger.error(f"创建/更新季版本时发生错误: {str(e)}", exc_info=True)
            savepoint.rollback()
            raise e
    
    def _upsert_media_version(self, session, media_file: FileAsset, core: MediaCore, metadata, season_version_id: Optional[int] = None) -> int:
        """
        使用数据库级别的 UPSERT 来原子化地创建/更新媒体版本，
        完美解决并发问题，并巧妙地处理“首选版本”逻辑。
        """
        # 增加对core为None的处理
        if not core:
            # 可以根据media_file获取core，或者抛出更明确的错误
            core = session.get(MediaCore, media_file.core_id)
            if not core:
                raise ValueError(f"无法找到与文件关联的MediaCore: {media_file.id}")
        # 1. 确定版本作用域
        if core.kind == "movie":
            scope = "movie_single"
        elif core.kind == "episode":
            scope = "episode_child"
        else:
            scope = "movie_single"

        # 2. 生成版本和指纹关键信息
        version_tags, variant_fingerprint = self._get_version_tags_and_fingerprint(media_file, core, scope)
        quality = self._get_quality_level(media_file)
        edition = self._get_attr(metadata, "edition") or self._get_attr(metadata, "episode_type") or "unknown"
        source = self._get_file_source(session, media_file)
        savepoint = session.begin_nested()
        try:
            # --- 3. 原子化 Upsert MediaVersion ---
            stmt = insert(MediaVersion).values(
                user_id=media_file.user_id,
                core_id=core.id,
                tags=version_tags,
                scope=scope,
                quality=quality,
                source=source,
                edition=edition,
                variant_fingerprint=variant_fingerprint,
                preferred=True,  # 插入时，默认设为首选
                primary_file_asset_id=media_file.id,
                parent_version_id=season_version_id,
                created_at=datetime.now(),
                updated_at=datetime.now()
            ).on_conflict_do_update(
                index_elements=['user_id', 'core_id', 'tags'],  # 与数据库唯一约束匹配
                set_={
                    # 使用 COALESCE 函数实现“如果为空则更新”的逻辑
                    # 如果数据库中的值（MediaVersion.quality）为 NULL，则用新值（quality）更新
                    'quality': func.coalesce(MediaVersion.quality, quality),
                    'source': func.coalesce(MediaVersion.source, source),
                    'edition': func.coalesce(MediaVersion.edition, edition),
                    'variant_fingerprint': func.coalesce(MediaVersion.variant_fingerprint, variant_fingerprint),
                    # 这些字段总是更新为最新值
                    'parent_version_id': season_version_id,
                    'primary_file_asset_id': media_file.id,
                    'updated_at': datetime.now(),
                    # 注意：'preferred' 字段不在这里，所以冲突时不会被更新，保持其原始状态
                }
            ).returning(MediaVersion.id)

            result = session.execute(stmt)
            version_id = result.scalar_one()
            # 提交保存点
            savepoint.commit()
            logger.debug(f"UPSERT {scope}版本: user_id={media_file.user_id}, core_id={core.id}, version_id={version_id}")
            return version_id
        except Exception as e:
            logger.error(f"创建/更新{scope}版本时发生错误: {str(e)}", exc_info=True)
            savepoint.rollback()
            raise e

    # ==================== 持久化元数据方法 ====================
    # ============非原子操作处理=============
    # region _upsert_artworks
    # def _upsert_artworks(self, session, user_id: int, core_id: int, provider: Optional[str], artworks) -> None:
    #     if not artworks:  # 空列表直接返回，避免无效循环
    #         return

    #     for artwork in artworks:
    #         try:
    #             # 1. 提取Artwork的核心属性（支持dict/dataclass）
    #             a_type = self._get_attr(artwork, "type")
    #             a_url = self._get_attr(artwork, "url")
    #             a_language = self._get_attr(artwork, "language")
    #             a_preferred = self._get_attr(artwork, "is_primary") is True  # 默认为False
    #             a_width = self._get_attr(artwork, "width")
    #             a_height = self._get_attr(artwork, "height")
                

    #             # 处理ArtworkType枚举（转为字符串value）
    #             _t = a_type.value if hasattr(a_type, "value") else a_type
    #             if not _t or not a_url:  # 类型/URL为空时跳过（避免无效数据）
    #                 continue

    #             # 2. 拆分“首选”和“非首选”逻辑处理
    #             if a_preferred:
    #                 # --------------------------
    #                 # 首选Artwork：同类型下仅允许1张
    #                 # --------------------------
    #                 # 步骤1：先将该类型下所有已有“首选”设为“非首选”（保证唯一首选）
    #                 existing_preferred = session.exec(
    #                     select(Artwork).where(
    #                         Artwork.user_id == user_id,
    #                         Artwork.core_id == core_id,
    #                         Artwork.type == _t,
    #                         Artwork.preferred == True
    #                     )
    #                 ).all()
    #                 for ep in existing_preferred:
    #                     ep.preferred = False

    #                 # 步骤2：查询是否已有“同类型+同URL”的记录（可能之前是非首选）
    #                 existing = session.exec(
    #                     select(Artwork).where(
    #                         Artwork.user_id == user_id,
    #                         Artwork.core_id == core_id,
    #                         Artwork.type == _t,
    #                         Artwork.remote_url == a_url
    #                     )
    #                 ).first()

    #                 if existing:
    #                     # 更新已有记录为“首选”，并同步其他字段
    #                     existing.preferred = True
    #                     existing.provider = provider or existing.provider
    #                     existing.language = a_language or existing.language
    #                     existing.width = a_width or existing.width
    #                     existing.height = a_height or existing.height
                       
    #                 else:
    #                     # 新增首选记录
    #                     session.add(Artwork(
    #                         user_id=user_id,
    #                         core_id=core_id,
    #                         type=_t,
    #                         remote_url=a_url,
    #                         local_path=None,
    #                         provider=provider,
    #                         language=a_language,
    #                         preferred=True,
    #                         exists_local=False,
    #                         width=a_width,
    #                         height=a_height,
                            
    #                     ))

    #             else:
    #                 # --------------------------
    #                 # 非首选Artwork：按“类型+URL”唯一标识（支持多图）
    #                 # --------------------------
    #                 # 步骤1：查询是否已有“同类型+同URL”的非首选记录（避免重复）
    #                 existing = session.exec(
    #                     select(Artwork).where(
    #                         Artwork.user_id == user_id,
    #                         Artwork.core_id == core_id,
    #                         Artwork.type == _t,
    #                         Artwork.remote_url == a_url,
    #                         Artwork.preferred == False  # 仅匹配非首选
    #                     )
    #                 ).first()

    #                 if existing:
    #                     # 更新已有非首选记录的字段（如语言、评分等可能变化）
    #                     existing.provider = provider or existing.provider
    #                     existing.language = a_language or existing.language
    #                     existing.width = a_width or existing.width
    #                     existing.height = a_height or existing.height
                        
    #                 else:
    #                     # 新增非首选记录（不影响其他非首选）
    #                     session.add(Artwork(
    #                         user_id=user_id,
    #                         core_id=core_id,
    #                         type=_t,
    #                         remote_url=a_url,
    #                         local_path=None,
    #                         provider=provider,
    #                         language=a_language,
    #                         preferred=False,
    #                         exists_local=False,
    #                         width=a_width,
    #                         height=a_height,
                           
    #                     ))

    #         except Exception as e:
    #             # 细化异常捕获，避免吞掉所有错误（建议添加日志）
    #             print(f"处理Artwork失败（URL: {a_url}）：{str(e)}")
    #             # 如需回滚局部错误：session.rollback()
    #             pass 
    # endregion 
    
    # region _upsert_external_ids
    # def _upsert_external_ids(self, session, user_id: int, core_id: int, external_ids) -> None:
    #     try:
    #         if not external_ids:
    #             return
            
    #         for eid in external_ids:
    #             if not eid:
    #                 continue
    #             # 3. 用self._get_attr兼容dict和_DictWrapper/对象（代替eid.get()）
    #             provider = self._get_attr(eid, "provider")  # 无默认值，不存在则返回None
    #             external_id = self._get_attr(eid, "external_id")  # 原始外部ID（未转str）

    #             # 4. 过滤无效数据（provider为空或external_id为空）
    #             if not provider or external_id is None:
    #                 logger.debug(f"跳过无效外部ID（provider={provider}, external_id={external_id}）")
    #                 continue

    #             external_id = str(external_id)

    #             existing = session.exec(select(ExternalID).where(
    #                 ExternalID.user_id == user_id,
    #                 ExternalID.core_id == core_id,
    #                 ExternalID.source == provider,
    #                 # ExternalID.key == external_id
    #             )).first()
    #             if not existing:
    #                 session.add(ExternalID(user_id=user_id, core_id=core_id, source=provider, key=external_id))
    #                 session.flush()
    #             else:
    #                 existing.key = external_id
    #             # 更新核心表的tmdb_id
    #             if provider == 'tmdb':
    #                 media_core = session.exec(select(MediaCore).where(MediaCore.user_id == user_id, MediaCore.id == core_id)).first()
    #                 if media_core :
    #                     media_core.tmdb_id = external_id 
                        
    #     except Exception as e:
    #         logger.error(f"更新ExternalIDs失败: {e}", exc_info=True)
    #         pass
    # endregion _upsert_external_ids
    
    # region _upsert_credits
    # def _upsert_credits(self, session, user_id: int, core_id: int, credits, provider: Optional[str]) -> None:
    #     # logger.info(f"开始处理Credits，共 {len(credits)} 条记录")
    #     if not credits:
    #         return
        
    #     for c in credits:
    #         try:
    #             if not c:
    #                 continue

    #             name = self._get_attr(c, "name")
    #             original_name = self._get_attr(c, "original_name")
    #             provider_id = self._get_attr(c, "provider_id")
    #             purl = self._get_attr(c, "image_url")
    #             if not name:
    #                 continue
    #             person = session.exec(select(Person).where(Person.provider_id == provider_id, Person.name == name,Person.provider == provider)).first()
    #             if not person:       
    #                 person = Person(provider=provider, provider_id=provider_id, name=name,original_name=original_name, profile_url=purl)
    #                 session.add(person)
    #                 session.flush()
    #             else:
    #                 try:
                        
    #                     person.original_name = original_name or person.original_name
    #                     if not getattr(person, "profile_url", None) and purl:
    #                         person.profile_url = purl
    #                 except Exception as e:
    #                     logger.error(f"更新Person profile_url失败: {e}", exc_info=True)
    #                     pass
    #             # 处理 Enum 类型：如果是 Enum，取其 value；如果已是字符串，直接使用
    #             c_type = self._get_attr(c, "type")
    #             if hasattr(c_type, "value"):
    #                 role_type = c_type.value
    #             else:
    #                 role_type = c_type
    #             role = "cast" if role_type == "actor" else "crew"
    #             role = "guest" if self._get_attr(c, "is_flying") else role


    #             character = self._get_attr(c, "character") if role == "cast" else None # 演员角色名称,导演就是"Director"
    #             job = role_type # actor/director/writer
    #             order = self._get_attr(c, "order")
    #             existing = session.exec(select(Credit).where(
    #                 Credit.user_id == user_id,
    #                 Credit.core_id == core_id,
    #                 Credit.person_id == person.id,
    #                 Credit.role == role,
    #                 Credit.job == job,
    #                 # Credit.order == order
    #             )).first()
    #             if not existing:
    #                 session.add(Credit(user_id=user_id, core_id=core_id, person_id=person.id, role=role, character=character, job=job, order=order))
    #                 session.flush()
    #             else:
    #                 existing.role = role
    #                 existing.character = character
    #                 existing.job = job
    #                 existing.order = order
    #         except Exception as e:
    #             logger.error(f"处理Person/Credit失败（name={name}, provider={provider}）: {str(e)}", exc_info=True)
    #             # 关键：异常后回滚Session，避免后续操作报错
    #             session.rollback()
    #             # 重新开始事务（可选，根据业务需求）
    #             session.begin()
    #             continue  # 跳过当前记录，处理下一条
    # endregion _upsert_credits
    
    # region _upsert_genres
    # def _upsert_genres(self, session, user_id: int, core_id: int, genres) -> None:
    #     try:
    #         for genre_name in genres or []:
    #             if not genre_name or "&" in genre_name:
    #                 continue
    #             genre = session.exec(select(Genre).where(Genre.name == genre_name)).first()
    #             if not genre:
    #                 genre = Genre(name=genre_name)
    #                 session.add(genre)
    #                 session.flush()
    #             existing_link = session.exec(select(MediaCoreGenre).where(MediaCoreGenre.user_id == user_id, MediaCoreGenre.core_id == core_id, MediaCoreGenre.genre_id == genre.id)).first()
    #             if not existing_link:
    #                 session.add(MediaCoreGenre(user_id=user_id, core_id=core_id, genre_id=genre.id))
    #     except Exception:
    #         pass
    # endregion _upsert_genres
    
    # ============原子操作处理=============
    def _upsert_credits(self, session, user_id: int, core_id: int, credits, provider: Optional[str]) -> None:
        """
        使用数据库级别的 UPSERT 操作来原子化地处理 Person 和 Credit 的创建/更新，
        彻底解决并发环境下的竞态条件问题。
        """
        if not credits:
            return

        for c in credits:
            # 1. 创建保存点：用于局部回滚
            savepoint = session.begin_nested()
            try:
                if not c:
                    continue

                # --- 1. 处理 Person ---
                name = self._get_attr(c, "name")
                original_name = self._get_attr(c, "original_name")
                provider_id = self._get_attr(c, "provider_id")
                purl = self._get_attr(c, "image_url")
                if not name:
                    continue

                # 使用 UPSERT (INSERT ... ON CONFLICT DO NOTHING) 来原子化地创建 Person
                # 这会尝试插入，如果 (provider, provider_id, name) 冲突，则什么都不做
                stmt_person = insert(Person).values(
                    provider=provider,
                    provider_id=provider_id,
                    name=name,
                    original_name=original_name,
                    profile_url=purl
                ).on_conflict_do_nothing(
                    index_elements=['provider', 'provider_id', 'name']  # 指定唯一约束的列
                )
                session.execute(stmt_person)

                # 无论是否插入了新数据，都重新查询一次以确保获取到 person 对象
                person = session.exec(select(Person).where(
                    Person.provider_id == provider_id,
                    Person.name == name,
                    Person.provider == provider
                )).first()

                # 如果此时 person 仍然为 None，说明有其他严重问题（如 provider_id 为 None）
                if not person:
                    logger.error(f"UPSERT Person 后仍无法获取到记录 (name={name}, provider={provider}, provider_id={provider_id})")
                    continue

                # 更新可能缺失的字段 (例如，profile_url)
                # 这部分逻辑在 person 对象获取后执行，确保总是作用于一个有效的实例
                person.original_name = original_name or person.original_name
                if not person.profile_url and purl:
                    person.profile_url = purl

                # --- 2. 处理 Credit ---
                # 处理 Enum 类型
                c_type = self._get_attr(c, "type")
                if hasattr(c_type, "value"):
                    role_type = c_type.value
                else:
                    role_type = c_type
                role = "cast" if role_type == "actor" else "crew"
                role = "guest" if self._get_attr(c, "is_flying") else role

                character = self._get_attr(c, "character") if role == "cast" else None
                job = role_type
                order = self._get_attr(c, "order")

                # 使用 UPSERT (INSERT ... ON CONFLICT DO UPDATE) 来原子化地创建/更新 Credit
                # 如果 (user_id, core_id, person_id, role, job) 冲突，则更新 character 和 order
                stmt_credit = insert(Credit).values(
                    user_id=user_id,
                    core_id=core_id,
                    person_id=person.id,
                    role=role,
                    character=character,
                    job=job,
                    order=order
                ).on_conflict_do_update(
                    index_elements=['user_id', 'core_id', 'person_id', 'role', 'job'], # 假设这是 Credit 表的唯一/候选键
                    set_={
                        'character': character,
                        'order': order
                    }
                )
                session.execute(stmt_credit)
                 
                # 2. 无错误则释放保存点（提交局部操作）
                savepoint.commit()

            except Exception as e:
                logger.error(f"处理 Person/Credit 失败（name={name if 'name' in locals() else 'N/A'}, provider={provider}）: {str(e)}", exc_info=True)
                # 关键：发生任何异常时回滚当前事务，避免会话状态污染
                savepoint.rollback()
                continue  # 跳过当前记录，处理下一条
    
    def _upsert_artworks(self, session, user_id: int, core_id: int, provider: Optional[str], artworks) -> None:
        """
        使用数据库级别的 UPSERT 和原子性 UPDATE 来处理 Artwork，
        确保“唯一首选”逻辑在并发环境下的正确性和一致性。
        """
        if not artworks:
            return

        for artwork in artworks:
            # 1. 创建保存点：用于局部回滚
            savepoint = session.begin_nested()
            try:
                # 1. 提取Artwork的核心属性
                a_type = self._get_attr(artwork, "type")
                a_url = self._get_attr(artwork, "url")
                a_language = self._get_attr(artwork, "language")
                a_preferred = self._get_attr(artwork, "is_primary") is True
                a_width = self._get_attr(artwork, "width")
                a_height = self._get_attr(artwork, "height")

                _t = a_type.value if hasattr(a_type, "value") else a_type
                if not _t or not a_url:
                    continue

                # 定义通用值
                values = {
                    "provider": provider,
                    "language": a_language,
                    "width": a_width,
                    "height": a_height,
                }

                if a_preferred:
                    # --- 首选 Artwork 的原子化处理 ---

                    # 步骤1: UPSERT 当前 Artwork，并确保其 preferred=True
                    # 假设 (user_id, core_id, type, remote_url, preferred) 是唯一键
                    stmt = insert(Artwork).values(
                        user_id=user_id,
                        core_id=core_id,
                        type=_t,
                        remote_url=a_url,
                        preferred=True,  # 插入或更新时，强制设为首选
                        **values
                    ).on_conflict_do_update(
                        index_elements=['user_id', 'core_id', 'type', 'remote_url'],
                        set_= {
                            "preferred": True,  # 冲突时，也更新为首选
                            **values
                        }
                    ).returning(Artwork.id) # 返回被插入/更新记录的ID

                    result = session.execute(stmt)
                    current_artwork_id = result.scalar_one()

                    # 步骤2: 原子性地将其他同类型的 Artwork 设为非首选
                    # 这是一个独立的原子操作，确保只有一个首选
                    session.execute(
                        update(Artwork).where(
                            Artwork.user_id == user_id,
                            Artwork.core_id == core_id,
                            Artwork.type == _t,
                            Artwork.id != current_artwork_id # 关键：排除刚刚操作的那条记录
                        ).values(preferred=False)
                    )

                else:
                    # --- 非首选 Artwork 的原子化处理 ---
                    # UPSERT 当前 Artwork，但不修改 preferred 状态
                    stmt = insert(Artwork).values(
                        user_id=user_id,
                        core_id=core_id,
                        type=_t,
                        remote_url=a_url,
                        preferred=False, # 插入时设为非首选
                        **values
                    ).on_conflict_do_update(
                        index_elements=['user_id', 'core_id', 'type', 'remote_url'],
                        set_=values # 冲突时，只更新其他元数据，不碰 preferred
                    )
                    session.execute(stmt)
                
                # 提交保存点：如果所有操作都成功，提交保存点
                savepoint.commit()

            except Exception as e:
                # 使用 logger 替代 print，并记录详细信息
                logger.error(f"处理 Artwork 失败（URL: {a_url if 'a_url' in locals() else 'N/A'}）: {str(e)}", exc_info=True)
                # 关键：发生任何异常时回滚当前事务
                savepoint.rollback()
                continue  # 跳过当前 artwork，处理下一个
     
    def _upsert_genres(self, session, user_id: int, core_id: int, genres) -> None:
        """
        使用数据库级别的 UPSERT 操作来原子化地处理 Genre 和 MediaCoreGenre 的创建，
        解决并发环境下的竞态条件，并改进了错误处理。
        """
        if not genres:
            return

        for genre_name in genres:
            # 1. 创建保存点：用于局部回滚
            savepoint = session.begin_nested()
            try:
                if not genre_name or "&" in genre_name:
                    continue

                # --- 1. 处理 Genre 表 ---
                # 使用 UPSERT (INSERT ... ON CONFLICT DO NOTHING) 来原子化地创建 Genre
                stmt_genre = insert(Genre).values(name=genre_name).on_conflict_do_nothing(
                    index_elements=['name']  # 假设 Genre.name 是唯一键
                )
                session.execute(stmt_genre)

                # 无论是否插入了新数据，都查询一次以获取 genre 对象
                genre = session.exec(select(Genre).where(Genre.name == genre_name)).first()

                if not genre:
                    # 如果查询不到，说明有其他问题（比如 genre_name 为空或格式错误）
                    logger.error(f"UPSERT Genre 后仍无法获取到记录: {genre_name}")
                    continue

                # --- 2. 处理 MediaCoreGenre 关联表 ---
                # 使用 UPSERT (INSERT ... ON CONFLICT DO NOTHING) 来原子化地创建关联
                # 如果 (user_id, core_id, genre_id) 的链接已存在，则什么都不做
                stmt_link = insert(MediaCoreGenre).values(
                    user_id=user_id,
                    core_id=core_id,
                    genre_id=genre.id
                ).on_conflict_do_nothing(
                    index_elements=['user_id', 'core_id', 'genre_id']  # 指定关联表的唯一键
                )
                session.execute(stmt_link)
                
                # 2. 提交保存点：如果所有操作都成功，提交保存点
                savepoint.commit()
                
            except Exception as e:
                # 记录详细的错误信息，而不是静默忽略
                logger.error(f"处理 Genre 失败（name={genre_name if 'genre_name' in locals() else 'N/A'}）: {str(e)}", exc_info=True)
                # 关键：发生任何异常时回滚当前事务，避免会话状态污染
                savepoint.rollback()
                continue  # 跳过当前类型，处理下一个

    def _upsert_external_ids(self, session, user_id: int, core_id: int, external_ids) -> None:
        """
        使用数据库级别的 UPSERT 操作来原子化地处理 ExternalID 的创建/更新，
        解决并发环境下的竞态条件，并改进了错误处理。
        """
        if not external_ids:
            return

        for eid in external_ids:
            # 创建保存点：用于局部回滚
            savepoint = session.begin_nested()
            try:
                if not eid:
                    continue

                # 1. 提取和验证数据
                provider = self._get_attr(eid, "provider")
                external_id_raw = self._get_attr(eid, "external_id")

                if not provider or external_id_raw is None:
                    logger.debug(f"跳过无效外部ID（provider={provider}, external_id={external_id_raw}）")
                    continue

                external_id_str = str(external_id_raw)

                # --- 2. 原子化地 Upsert ExternalID ---
                # 使用 UPSERT (INSERT ... ON CONFLICT DO UPDATE) 来创建或更新记录
                # 如果 (user_id, core_id, source) 冲突，则更新 key 字段
                stmt = insert(ExternalID).values(
                    user_id=user_id,
                    core_id=core_id,
                    source=provider,
                    key=external_id_str
                ).on_conflict_do_update(
                    index_elements=['user_id', 'core_id', 'source'],  # 假设这是 ExternalID 表的唯一键
                    set_={
                        'key': external_id_str  # 冲突时，更新 key
                    }
                )
                session.execute(stmt)

                # --- 3. 条件性更新 MediaCore ---
                # 如果 provider 是 'tmdb'，则更新主表的 tmdb_id
                # if provider == 'tmdb':
                #     # 直接执行 UPDATE 语句比先 SELECT 再 UPDATE 更高效
                #     session.execute(
                #         update(MediaCore).where(
                #             MediaCore.user_id == user_id,
                #             MediaCore.id == core_id
                #         ).values(tmdb_id=external_id_str)
                #     )
                
                # 提交保存点：如果所有操作都成功，提交保存点
                savepoint.commit()
                
            except Exception as e:
                logger.error(f"处理 ExternalID 失败（provider={provider if 'provider' in locals() else 'N/A'}）: {str(e)}", exc_info=True)
                # 关键：发生任何异常时回滚当前事务
                savepoint.rollback()
                continue  # 跳过当前ID，处理下一个

    def _apply_movie_detail(self, session, media_file: FileAsset, metadata: ScraperMovieDetail) -> MediaCore:
        """
        使用数据库级别的 UPSERT 操作来原子化地处理电影核心信息、扩展信息和系列信息，
        解决并发环境下的竞态条件，并提升了整体性能。
        """
        # 创建保存点：用于局部回滚（不影响外层事务）
        savepoint = session.begin_nested()
        try:
            user_id = media_file.user_id
            kind = "movie"

            # 1. 提取并预处理所有元数据
            title = metadata.title
            original_title = getattr(metadata, "original_title", None)           
            plot = getattr(metadata, "overview", None)
            display_rating = getattr(metadata, "vote_average", None)
            display_poster_path = getattr(metadata, "poster_path", None)
            display_date,year_val = self._parse_dt(getattr(metadata, "release_date", None))
            tmdb_id = str(getattr(metadata, "movie_id", None)) if getattr(metadata, "provider", None) == "tmdb" and getattr(metadata, "movie_id", None) else None

            # --- 2. 原子化 Upsert MediaCore ---
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
                # 与数据库唯一约束匹配(之后修改，与tmdbid解耦，充分利用多刮削插件)
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

            # --- 3. 原子化 Upsert MovieExt ---    
            raw_data = getattr(metadata, 'raw_data', None)
            # 如果是 _DictWrapper 类型，获取其内部字典数据
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

            # --- 4. 处理 Collection ---
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

            # 如果存在 collection_id，则更新 MovieExt 的关联
            if collection_id:
                session.execute(
                    update(MovieExt).where(
                        MovieExt.user_id == user_id,
                        MovieExt.core_id == core_id
                    ).values(collection_id=collection_id)
                )

            # --- 5. 调用其他已经改造过的 Upsert 辅助函数 ---
            self._upsert_artworks(session, user_id, core_id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
            self._upsert_credits(session, user_id, core_id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
            self._upsert_genres(session, user_id, core_id, getattr(metadata, "genres", []) or [])
            self._upsert_external_ids(session, user_id, core_id, getattr(metadata, "external_ids", None))

            # --- 6. 更新媒体版本 ---
            core = session.get(MediaCore, core_id)
            version_id = self._upsert_media_version(session, media_file, core, metadata) # core 参数可以不用了，因为 media_file 已关联
            media_file.version_id = version_id
            media_file.updated_at = datetime.now()

            # 无错误则提交保存点（确认局部事务）
            savepoint.commit()

            # --- 7. 返回完整的 MediaCore 对象 ---
            return core

        except Exception as e:
            logger.error(f"处理电影元数据失败: {e}", exc_info=True)
            savepoint.rollback()
            raise   
        
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
        """
        使用数据库级别的 UPSERT 操作来原子化地处理剧集核心信息和扩展信息，
        解决并发环境下的竞态条件。
        """
         # 创建保存点：用于局部回滚（不影响外层事务）
        savepoint = session.begin_nested()
        try:
            # 1. 提取并预处理所有元数据
            name_val = getattr(sd, "name", None)  or ""
            genres = getattr(sd, "genres", []) or []
            first_air_date,year_val = self._parse_dt(getattr(sd, "first_air_date", None))
            last_air_date,_ = self._parse_dt(getattr(sd, "last_air_date", None))  
            tmdb_id=str(getattr(sd, "series_id", None)) if getattr(sd, "provider", None) == "tmdb" and getattr(sd, "series_id", None) else None
            type_val = getattr(sd, "type", None)
            try:
                type_val = self._check_series_type(type_val, genres)
            except Exception as e:
                logger.error(f"系类类型判断出错: {e}")
                type_val = "TV"

            # --- 2. 原子化 Upsert MediaCore (Series) ---
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
                index_elements=["user_id", "kind", "tmdb_id"],  # 与数据库唯一约束匹配
                set_={
                    # 'original_title': getattr(sd, "original_name", None),
                    'plot': getattr(sd, "overview", None),
                    # 'display_rating': getattr(sd, "vote_average", None),
                    # 'display_poster_path': getattr(sd, "poster_path", None),
                    # 'display_date': first_air_date,
                    # 'year': year_val,
                    # 'title': name_val,
                    # 'subtype': type_val,
                    # 'tmdb_id': func.coalesce(MediaCore.tmdb_id, tmdb_id),
                    'updated_at': datetime.now()
                }
            ).returning(MediaCore.id)

            result = session.execute(stmt_core)
            series_core_id = result.scalar_one()

            # --- 3. 原子化 Upsert SeriesExt ---
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
                    # 'title': name_val,
                    'overview': getattr(sd, "overview", None),
                    # 'season_count': getattr(sd, "number_of_seasons", None),
                    # 'episode_count': getattr(sd, "number_of_episodes", None),
                    # 'episode_run_time': int(getattr(sd, "episode_run_time", [None])[0]) if isinstance(getattr(sd, "episode_run_time", []), list) and getattr(sd, "episode_run_time", []) else SeriesExt.episode_run_time,
                    # 'status': getattr(sd, "status", None),
                    # 'rating': getattr(sd, "vote_average", None),
                    # 'origin_country': list(getattr(sd, "origin_country", []) or []),
                    # 'aired_date': first_air_date,
                    # 'last_aired_date': last_air_date,
                    # 'poster_path': getattr(sd, "poster_path", None),
                    # 'backdrop_path': getattr(sd, "backdrop_path", None),
                    # 'series_type': type_val,
                    # 'raw_data': json.dumps(raw_data, ensure_ascii=False)
                }
            )
            session.execute(stmt_ext)

            # --- 4. 调用其他已经改造过的 Upsert 辅助函数 ---
            self._upsert_genres(session, user_id, series_core_id, genres)
            self._upsert_artworks(session, user_id, series_core_id, getattr(sd, "provider", None), getattr(sd, "artworks", None))
            self._upsert_external_ids(session, user_id, series_core_id, getattr(sd, "external_ids", None))
                     
            # 无错误则提交保存点（确认局部事务）
            savepoint.commit()

            # 返回完整的 MediaCore 对象
            series_core = session.get(MediaCore, series_core_id)
            if not series_core:
                raise RuntimeError(f"UPSERT 成功但未查询到 series_core（ID: {series_core_id}）")
            return series_core

        except Exception as e:
            # 捕获所有异常，回滚保存点，避免事务污染
            savepoint.rollback()
            logger.error(f"处理系列信息时发生错误，已回滚保存点: {str(e)}", exc_info=True)
            raise  # 重新抛出异常，让上层处理（如终止任务）
    
    def _apply_season_detail(self, session, user_id: int, series_core: Optional[MediaCore], se: ScraperSeasonDetail) -> MediaCore:
        """
        使用数据库级别的 UPSERT 操作来原子化地处理季核心信息和扩展信息，
        解决并发环境下的竞态条件。
        """
        # 创建保存点：用于局部回滚（不影响外层事务）
        savepoint = session.begin_nested()
        try:
            season_num = getattr(se, "season_number", None)
            season_name = getattr(se, "name", None)
            air_date,year_val = self._parse_dt(getattr(se, "air_date", None))

            tmdb_id=str(getattr(se, "season_id", None)) if getattr(se, "provider", None) == "tmdb" and getattr(se, "season_id", None) else None
            

            # --- 1. 原子化 Upsert MediaCore (Season) ---
            # 我们优先使用 tmdb_id 作为唯一标识，如果没有则使用标题和年份
            stmt_core = insert(MediaCore).values(
                user_id=user_id,
                kind="season",
                title=f"{series_core.title}-{season_name}",
                year=year_val,
                display_date=air_date,
                display_poster_path=getattr(se, "poster_path", None),
                display_rating=getattr(se, "vote_average", None),         
                tmdb_id=tmdb_id,
                parent_id=series_core.id ,
                created_at=datetime.now(),
                updated_at=datetime.now()
            ).on_conflict_do_update(
                # 这里假设 (user_id, title, kind, year) 是唯一键，如果 tmdb_id 存在，优先用它
                index_elements=["user_id", "kind","tmdb_id"],
                set_={
                    # 'display_date': air_date,
                    # 'display_poster_path': getattr(se, "poster_path", None),
                    # 'display_rating': getattr(se, "vote_average", None),
                    # 'year': year_val,
                    # 'title': season_name,
                    # 'tmdb_id': func.coalesce(MediaCore.tmdb_id, tmdb_id),
                    'updated_at': datetime.now()
                }
            ).returning(MediaCore.id)

            result = session.execute(stmt_core)
            season_core_id = result.scalar_one()

            # --- 2. 原子化 Upsert SeasonExt ---
            raw_data = getattr(se, 'raw_data', None)
            if isinstance(raw_data, _DictWrapper):
                raw_data = raw_data._data


            stmt_ext = insert(SeasonExt).values(
                user_id=user_id,
                core_id=season_core_id,
                series_core_id=series_core.id if series_core else None,
                season_number=season_num,
                # title=season_name,
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
                    # 'episode_count': getattr(se, "episode_count", None),
                    # 'rating': getattr(se, "vote_average", None),
                    # 'aired_date': air_date,
                    # 'poster_path': getattr(se, "poster_path", None),
                    # 'raw_data': json.dumps(raw_data, ensure_ascii=False)
                }
            )
            session.execute(stmt_ext)

            # --- 3. 调用其他已经改造过的 Upsert 辅助函数 ---          
            self._upsert_artworks(session, user_id, season_core_id, getattr(se, "provider", None), getattr(se, "artworks", None))  
            self._upsert_credits(session, user_id, season_core_id, getattr(se, "credits", None), getattr(se, "provider", None))
            self._upsert_external_ids(session, user_id, season_core_id, getattr(se, "external_ids", None))

            # 提交保存点：如果一切正常，提交保存点
            savepoint.commit()

            # 返回完整的 MediaCore 对象 
            return session.get(MediaCore, season_core_id)
        except Exception as e:
            # 回滚保存点：如果发生错误，回滚到保存点
            savepoint.rollback()
            logger.error(f"处理季信息时发生错误，已回滚保存点: {str(e)}", exc_info=True)
            raise e
        
    def _apply_episode_detail(self, session, media_file: FileAsset, metadata: ScraperEpisodeDetail) -> MediaCore:
        """
        使用数据库级别的 UPSERT 操作来原子化地处理单集核心信息和扩展信息，
        解决并发环境下的竞态条件。
        """
        # 创建保存点：用于局部回滚（不影响外层事务）
        savepoint = session.begin_nested()
        try:
            user_id = media_file.user_id
            title_val = getattr(metadata, "name", None) or ""
            air_date,year_val = self._parse_dt(getattr(metadata, "air_date", None))
            tmdb_id = str(getattr(metadata, "episode_id", None)) if getattr(metadata, "provider", None) == "tmdb" and getattr(metadata, "episode_id", None) else None
            still_path_url = getattr(metadata, "still_path", None)
           
            # 1. 首先安全地获取或创建 series_core 和 season_core
            # 这些函数已经被改造为并发安全
            series_core = None
            season_core = None
            season_version_id = None
            try:
                if getattr(metadata, "series", None):
                    series_core = self._apply_series_detail(session, user_id, metadata.series)
                if getattr(metadata, "season", None) and series_core:
                    season_core = self._apply_season_detail(session, user_id, series_core, metadata.season)
                    season_version_id = self._upsert_season_version(session, media_file, season_core)
            except Exception as e:
                logger.error(f"创建/更新季/系列信息失败: {e}", exc_info=True)
                # 根据业务逻辑决定是否继续执行，这里我们继续
                return None

            # --- 2. 原子化 Upsert MediaCore (Episode) ---
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
                index_elements=["user_id", "kind", "tmdb_id"],  # 与数据库唯一约束匹配
                set_={
                    # 'plot': getattr(metadata, "overview", None),
                    # 'display_rating': getattr(metadata, "vote_average", None),
                    # 'display_poster_path': still_path_url,
                    # 'display_date': air_date,
                    # 'year': year_val,
                    # 'title': title_val,
                    # 'tmdb_id': func.coalesce(MediaCore.tmdb_id, tmdb_id),
                    'updated_at': datetime.now()
                }
            ).returning(MediaCore.id)

            result = session.execute(stmt_core)
            episode_core_id = result.scalar_one()
            logger.debug(f"旧ID：{media_file.core_id} 新核心ID: {episode_core_id}")
            media_file.core_id = episode_core_id

            # --- 3. 原子化 Upsert EpisodeExt ---
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
                index_elements=['user_id', 'series_core_id', 'season_number', 'episode_number'],  # 与数据库唯一约束匹配
                set_={
                    'core_id': episode_core_id,  # 确保关联到最新的 core_id
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

            # --- 4. 调用其他已经改造过的 Upsert 辅助函数 ---
            # self._upsert_artworks(session, user_id, episode_core_id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))   
            self._upsert_credits(session, user_id, episode_core_id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
            self._upsert_external_ids(session, user_id, episode_core_id, getattr(metadata, "external_ids", None))
       
            # --- 5. 更新媒体版本 ---
            episode_core = session.get(MediaCore, episode_core_id)
            # 传入season_version_id，让单集版本关联到季版本
            version_id = self._upsert_media_version(session, media_file, episode_core, metadata, season_version_id) # core 参数可以不用了，因为 media_file 已关联
            media_file.version_id = version_id
            media_file.season_version_id = season_version_id
            media_file.updated_at = datetime.now()

            # 提交保存点：如果一切正常，提交保存点
            savepoint.commit()
            # --- 7. 返回完整的 MediaCore 对象 ---
            return episode_core
        except Exception as e:
            # 回滚保存点：如果发生错误，回滚到保存点
            savepoint.rollback()
            logger.error(f"处理季信息时发生错误，已回滚保存点: {str(e)}", exc_info=True)
            raise e

    def _apply_file_path_info(self, session, media_file: FileAsset, path_info: Dict) -> None:
        """
        应用文件路径信息到领域模型

        事务说明:
            1. 更新文件的路径信息字段
        """
        # 创建保存点用于局部回滚
        savepoint = session.begin_nested()
        try:
            media_file.resolution = media_file.resolution or path_info.get("screen_size")
            media_file.frame_rate = media_file.frame_rate or path_info.get("frame_rate")
            media_file.mimetype = media_file.mimetype or path_info.get("mimetype")
            media_file.video_codec = media_file.video_codec or path_info.get("video_codec")
            media_file.audio_codec = media_file.audio_codec or path_info.get("audio_codec")
            media_file.container = media_file.container or path_info.get("container")
            media_file.updated_at = datetime.now()
            # 提交保存点
            savepoint.commit()
        except Exception as e:
            logger.error(f"应用文件路径信息时发生错误: {str(e)}", exc_info=True)
            savepoint.rollback()
            # raise e

    def apply_metadata(self, session, media_file: FileAsset, metadata, metadata_type: str, path_info: Dict) -> bool:
        """
        一次性幂等地将刮削结果写入领域模型，并更新相关扩展信息。

        事务说明:
            - 本方法内部仅执行 flush，不提交事务；由调用方统一 commit。
        参数:
            session: SQLModel 会话
            media_file: 当前媒体文件记录（用于定位/创建 MediaCore）
            metadata: 新契约对象或 dict，支持 ScraperMovieDetail/ScraperSeriesDetail/ScraperEpisodeDetail/ScraperSearchResult 或其对应的 dict 形式
        行为:
            - 创建/更新 MediaCore 与 ExternalID
            - 电视剧分层映射: SeriesExt/SeasonExt/EpisodeExt        
            - 通用映射: Artwork/Genre/MediaCoreGenre/Person/Credit
            - 电影扩展与合集: MovieExt/Collection
        返回:
            - bool: 操作是否成功
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
                    # 这里可以选择抛出异常或降级为 dict
            else:
                metadata = _DictWrapper(metadata)
                    # 如果没有找到对应的模型类，metadata 依然是 dict
                    # 这可能会导致后续 handler 报错，建议增加警告
                logger.info(f"类型 {metadata_type} 没有关联的模型类，将以 dict 形式继续")
        
        


        handler = self._get_handler(metadata_type)
        if not handler:
            logger.warning(f"不支持的元数据类型: {metadata_type}")
            return False

        core = None
        try:
            old_version_id = getattr(media_file, "version_id", None)
            old_season_version_id = getattr(media_file, "season_version_id", None)

            # 2. 架构优化：使用分发器调用具体处理函数
            if metadata_type == "series":
                # series 的处理函数签名不同，需要特殊处理
                core = handler(session, media_file.user_id, metadata)
            else:
                # movie, episode, search_result 的签名一致
                core = handler(session, media_file, metadata)

            if not core:
                logger.error(f"处理元数据失败，处理函数 {handler.__name__} 返回了 None。文件ID: {media_file.id}, 类型: {metadata_type}")
                return False

            # 3. 代码清晰度优化：集中更新 media_file 的核心关联
            # 对于 series 类型，只有当文件本身没有 core_id 时才关联
            if metadata_type != "series" or not media_file.core_id:
                media_file.core_id = core.id

            # 更新文件的路径信息字段
            self._apply_file_path_info(session, media_file, path_info)

            # session.flush() 确保当前事务中的所有更改都发送到数据库，
            # 使得后续可能依赖新ID的操作能够成功。
            session.flush()

            self._cleanup_orphan_versions_after_rebind(
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
            # 2. 健壮性优化：统一的异常捕获和日志记录
            logger.error(f"应用元数据时发生未预期的错误: {e}", exc_info=True)
            # 考虑是否需要在这里回滚，但通常由调用方决定
            # session.rollback()
            return False

    # async def apply_metadata_batch_async(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    #     if not items:
    #         return {"processed": 0, "succeeded": 0, "errors": []}

    #     from core.db import get_session as get_db_session
    #     from models.media_models import FileAsset

    #     def _run() -> Dict[str, Any]:
    #         processed = 0
    #         succeeded = 0
    #         errors: List[Dict[str, Any]] = []
    #         with next(get_db_session()) as session:
    #             for item in items:
    #                 file_id = item.get("file_id")
    #                 contract_type = item.get("contract_type")
    #                 metadata = item.get("contract_payload") or {}
    #                 path_info = item.get("path_info") or {}
    #                 if not file_id or not contract_type or not metadata:
    #                     errors.append({"file_id": file_id, "error": "missing_params"})
    #                     continue
    #                 media_file = session.get(FileAsset, file_id)
    #                 if not media_file:
    #                     errors.append({"file_id": file_id, "error": "file_not_found"})
    #                     continue
    #                 ok = self.apply_metadata(session, media_file, metadata=metadata, metadata_type=contract_type, path_info=path_info)
    #                 processed += 1
    #                 if ok:
    #                     succeeded += 1
    #                 else:
    #                     errors.append({"file_id": file_id, "error": "apply_failed"})
    #             session.commit()
    #         return {"processed": processed, "succeeded": succeeded, "errors": errors}

    #     return await asyncio.to_thread(_run)
    
    # region _apply_series_detail 
    # def _apply_series_detail(self, session, user_id: int, sd: ScraperSeriesDetail) -> MediaCore:
    #     name_val = getattr(sd, "name", None) or getattr(sd, "original_name", None) or ""
    #     genres = getattr(sd, "genres", []) or [] 
    #     type_val = getattr(sd, "type", None)  # Scripted|Reality(Variety)|Animation|Documentary|News|Talk Show|Other
    
    #     try:
    #         type_val = self._check_series_type(type_val, genres)
    #     except Exception as e:
    #         logger.error(f"系类类型判断出错: {e}")
    #         type_val = "TV"

    #     year_val = None
    #     try:
    #         dt = self._parse_dt(getattr(sd, "first_air_date", None))
    #         year_val = dt.year if dt else None
    #     except Exception:
    #         year_val = None
    #     series_core = session.exec(select(MediaCore).where(
    #         MediaCore.user_id == user_id,
    #         MediaCore.kind == "series",
    #         MediaCore.title == name_val,
    #         MediaCore.tmdb_id == getattr(sd, "series_id", None) if getattr(sd, "provider", None) == "tmdb" else None  
    #     )).first()
        
    #     if not series_core:
    #         series_core = MediaCore(
    #             user_id=user_id,
    #             kind="series",
    #             title=name_val,
    #             original_title=getattr(sd, "original_name", None),
    #             year=year_val,
    #             plot=getattr(sd, "overview", None),
    #             display_rating=getattr(sd, "vote_average", None),
    #             display_poster_path=getattr(sd, "poster_path", None),
    #             display_date=self._parse_dt(getattr(sd, "first_air_date", None)),
    #             subtype=type_val,
    #             created_at=datetime.now(),
    #             updated_at=datetime.now()
    #         )
    #         session.add(series_core)
    #         session.flush()
    #     else:
    #         series_core.kind = "series"
    #         series_core.title = name_val
    #         series_core.original_title = getattr(sd, "original_name", None)
    #         series_core.year = year_val
    #         series_core.plot = getattr(sd, "overview", None)
    #         series_core.display_rating = getattr(sd, "vote_average", None)
    #         series_core.display_poster_path = getattr(sd, "poster_path", None)
    #         series_core.display_date = self._parse_dt(getattr(sd, "first_air_date", None))
    #         series_core.subtype = type_val
    #         series_core.updated_at = datetime.now()
    #         # 或者直接不更新，直接返回
    #     # try:
    #     #     if getattr(sd, "provider", None) and getattr(sd, "series_id", None):
    #     #         existing = session.exec(select(ExternalID).where(
    #     #             ExternalID.user_id == user_id,
    #     #             ExternalID.core_id == series_core.id,
    #     #             ExternalID.source == sd.provider,
    #     #             ExternalID.key == str(sd.series_id)
    #     #         )).first()
    #     #         if not existing:
    #     #             session.add(ExternalID(user_id=user_id, core_id=series_core.id, source=sd.provider, key=str(sd.series_id)))
    #     #             session.flush()
    #     #         series_core.canonical_source = series_core.canonical_source or sd.provider
    #     #         series_core.canonical_external_key = series_core.canonical_external_key or str(sd.series_id)
    #     #         try:
    #     #             if sd.provider == "tmdb":
    #     #                 sid = int(str(sd.series_id)) if str(sd.series_id).isdigit() else None
    #     #                 if sid is not None:
    #     #                     series_core.tmdb_id = series_core.tmdb_id or sid
    #     #         except Exception:
    #     #             pass
    #     # except Exception:
    #     #     pass

        
        
    #     tv_ext = session.exec(select(SeriesExt).where(SeriesExt.core_id == series_core.id, SeriesExt.user_id == user_id)).first()
    #     if not tv_ext:
    #         tv_ext = SeriesExt(user_id=user_id, core_id=series_core.id)
    #         session.add(tv_ext)
    #     try:
    #         tv_ext.title = name_val or tv_ext.title
    #         tv_ext.overview = getattr(sd, "overview", None) or tv_ext.overview
    #         tv_ext.season_count = getattr(sd, "number_of_seasons", None)
    #         tv_ext.episode_count = getattr(sd, "number_of_episodes", None)
    #         rt = getattr(sd, "episode_run_time", None)
    #         if isinstance(rt, list) and len(rt) > 0:
    #             tv_ext.episode_run_time = int(rt[0]) if isinstance(rt[0], (int, float)) else None
    #         tv_ext.status = getattr(sd, "status", None)
    #         tv_ext.rating = getattr(sd, "vote_average", None)
    #         tv_ext.origin_country = list(getattr(sd, "origin_country", []) or [])
    #         try:
    #             fd = getattr(sd, "first_air_date", None)
    #             ld = getattr(sd, "last_air_date", None)
    #             tv_ext.aired_date = self._parse_dt(fd) if fd else tv_ext.aired_date
    #             tv_ext.last_aired_date = self._parse_dt(ld) if ld else tv_ext.last_aired_date
    #         except Exception:
    #             pass
    #         tv_ext.poster_path = getattr(sd, "poster_path", None) or tv_ext.poster_path
    #         tv_ext.backdrop_path = getattr(sd, "backdrop_path", None) or tv_ext.backdrop_path
    #         tv_ext.series_type = type_val or tv_ext.series_type
    #         raw_data = getattr(sd, 'raw_data', None)
    #         if isinstance(raw_data, _DictWrapper):
    #             raw_data = raw_data._data
    #         tv_ext.raw_data = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
    #     except Exception:
    #         pass
    #     # try:
    #     #     if getattr(tv_ext, "poster_path", None):
    #     #         art_p = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == series_core.id, Artwork.type == "poster", Artwork.preferred==True)).first()
    #     #         if not art_p:
    #     #             session.add(Artwork(user_id=user_id, core_id=series_core.id, type="poster", remote_url=tv_ext.poster_path, provider=getattr(sd, "provider", None), preferred=True))
    #     #         else:
    #     #             art_p.remote_url = art_p.remote_url or tv_ext.poster_path
    #     #             art_p.provider = getattr(sd, "provider", None) or getattr(art_p, "provider", None)
    #     #             art_p.preferred = True
    #     #             # art_p.exists_remote = True
    #     #     if getattr(tv_ext, "backdrop_path", None):
    #     #         art_b = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == series_core.id, Artwork.type == "backdrop", Artwork.preferred==True)).first()
    #     #         if not art_b:
    #     #             session.add(Artwork(user_id=user_id, core_id=series_core.id, type="backdrop", remote_url=tv_ext.backdrop_path, provider=getattr(sd, "provider", None), preferred=True))
    #     #         else:
    #     #             art_b.remote_url = art_b.remote_url or tv_ext.backdrop_path
    #     #             art_b.provider = getattr(sd, "provider", None) or getattr(art_b, "provider", None)
    #     #             art_b.preferred = True
    #     #             # art_b.exists_remote = True
    #     # except Exception:
    #     #     pass
    #     try:
    #         self._upsert_genres(session, user_id, series_core.id, getattr(sd, "genres", []) or [])
    #     except Exception as e:
    #         logger.error(f"更新剧集流派失败: {e}")
    #         pass
    #     try:
    #         self._upsert_artworks(session, user_id, series_core.id, getattr(sd, "provider", None), getattr(sd, "artworks", None))
    #     except Exception as e:
    #         logger.error(f"更新剧集海报失败: {e}")
    #         pass
    #     # try:
    #     #     self._upsert_credits(session, user_id, series_core.id, getattr(sd, "credits", None), getattr(sd, "provider", None))
    #     # except Exception as e:
    #     #     logger.error(f"更新剧集演员失败: {e}")
    #     #     pass
    #     try:
    #         self._upsert_external_ids(session, user_id, series_core.id, getattr(sd, "external_ids", None))
    #     except Exception as e:
    #         logger.error(f"更新剧集外部ID失败: {e}")
    #         pass
    #     return series_core
    # endregion     
    
    # region _apply_season_detail 
    # def _apply_season_detail(self, session, user_id: int, series_core: Optional[MediaCore], se: ScraperSeasonDetail) -> MediaCore:
    #     season_num = getattr(se, "season_number", None) 
    #     season_name = getattr(se, "name", None)
       
    #     existing_se = None
    #     try:
    #         if series_core:
    #             existing_se = session.exec(select(SeasonExt).where(SeasonExt.user_id == user_id, SeasonExt.series_core_id == series_core.id, SeasonExt.season_number == season_num)).first()
    #     except Exception as e:
    #         logger.error(f"获取剧集详情失败: {e}")
    #         existing_se = None
    #     season_core = None
    #     if existing_se:
    #         season_core = session.exec(select(MediaCore).where(MediaCore.id == existing_se.core_id)).first()
    #     if not season_core:
    #         season_core = session.exec(select(MediaCore).where(
    #             MediaCore.user_id == user_id,
    #             MediaCore.kind == "season",
    #             MediaCore.title == season_name,  #季title不可用，太多重复
    #             MediaCore.tmdb_id == (getattr(se, "season_id", None) if getattr(se, "season_id", None) else None)
    #         )).first()

    #     # 彻底不存在该season
    #     if not season_core:
    #         season_core = MediaCore(
    #             user_id=user_id, 
    #             kind="season", 
    #             title=season_name,
    #             display_date=self._parse_dt(getattr(se, "air_date", None)), 
    #             display_poster_path=getattr(se, "poster_path", None),
    #             display_rating=getattr(se, "vote_average", None),
    #             created_at=datetime.now(), 
    #             updated_at=datetime.now()
    #         )
    #         session.add(season_core)
    #         session.flush()
    #     else:
    #         season_core.kind = "season"
    #         season_core.title = season_name
    #         season_core.display_date = self._parse_dt(getattr(se, "air_date", None))
    #         season_core.display_poster_path = getattr(se, "poster_path", None)
    #         season_core.display_rating = getattr(se, "vote_average", None)
    #         season_core.updated_at = datetime.now()
    #         # 直接返回或者可以更新已有的数据（我认为可以不更新，减少数据库操作）

    #     se_ext = session.exec(select(SeasonExt).where(
    #         # SeasonExt.core_id == season_core.id,
    #         SeasonExt.series_core_id == (series_core.id if series_core else None),
    #         SeasonExt.season_number == season_num, 
    #         SeasonExt.user_id == user_id,
    #         )).first()
    #     if not se_ext:
    #         se_ext = SeasonExt(user_id=user_id, core_id=season_core.id, series_core_id=series_core.id if series_core else None, season_number=season_num)
    #         session.add(se_ext)
    #     try:
    #         se_ext.title = season_name or se_ext.title
    #         se_ext.overview = getattr(se, "overview", None) or se_ext.overview
    #         se_ext.episode_count = getattr(se, "episode_count", None)
    #         se_ext.rating = getattr(se, "vote_average", None)
    #         ad = getattr(se, "air_date", None)
    #         se_ext.aired_date = self._parse_dt(ad) if ad else se_ext.aired_date
    #         se_ext.poster_path = getattr(se, "poster_path", None) or se_ext.poster_path
            
    #         # 替换原来的 raw_data 赋值行
    #         raw_data = getattr(se, 'raw_data', None)
    #         # 如果是 _DictWrapper 类型，获取其内部字典数据
    #         if isinstance(raw_data, _DictWrapper):
    #             raw_data = raw_data._data
    #         # 序列化为JSON字符串
    #         se_ext.raw_data = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
    #     except Exception as e:
    #         logger.error(f"更新剧集详情失败: {e}")
    #         pass
    #     # try:
    #     #     if getattr(se_ext, "poster_path", None):
    #     #         art_p = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == season_core.id, Artwork.type == "poster", Artwork.preferred==True)).first()
    #     #         if not art_p:
    #     #             session.add(Artwork(user_id=user_id, core_id=season_core.id, type="poster", remote_url=se_ext.poster_path, provider=getattr(se, "provider", None), preferred=True))
    #     #         else:
    #     #             art_p.remote_url = art_p.remote_url or se_ext.poster_path
    #     #             art_p.provider = getattr(se, "provider", None) or getattr(art_p, "provider", None)
    #     #             art_p.preferred = True
    #     #             # art_p.exists_remote = True
    #     # except Exception as e:
    #     #     logger.error(f"更新剧集海报失败: {e}")
    #     #     pass
    #     # try:
    #     #     if getattr(se, "provider", None) and getattr(se, "season_id", None):
    #     #         existing = session.exec(select(ExternalID).where(
    #     #             ExternalID.user_id == user_id,
    #     #             ExternalID.core_id == season_core.id,
    #     #             ExternalID.source == se.provider,
    #     #             ExternalID.key == str(se.season_id)
    #     #         )).first()
    #     #         if not existing:
    #     #             session.add(ExternalID(user_id=user_id, core_id=season_core.id, source=se.provider, key=str(se.season_id)))
    #     #         season_core.canonical_source = season_core.canonical_source or se.provider
    #     #         season_core.canonical_external_key = season_core.canonical_external_key or str(se.season_id)
    #     #         try:
    #     #             if se.provider == "tmdb":
    #     #                 sid = int(str(se.season_id)) if str(se.season_id).isdigit() else None
    #     #                 if sid is not None:
    #     #                     season_core.tmdb_id = season_core.tmdb_id or sid
    #     #         except Exception as e:
    #     #             logger.error(f"更新剧集外部ID失败: {e}")
    #     #             raise
    #     # except Exception as e:
    #     #     logger.error(f"更新剧集外部ID失败: {e}")
    #     #     pass
    #     try:
    #         self._upsert_artworks(session, user_id, season_core.id, getattr(se, "provider", None), getattr(se, "artworks", None))
    #     except Exception as e:
    #         logger.error(f"更新剧集海报失败: {e}")
    #         pass
    #     try:
    #         self._upsert_credits(session, user_id, season_core.id, getattr(se, "credits", None), getattr(se, "provider", None))
    #     except Exception as e:
    #         logger.error(f"更新剧集演员失败: {e}")
    #         pass
    #     try:
    #         self._upsert_external_ids(session, user_id, season_core.id, getattr(se, "external_ids", None))
    #     except Exception as e:
    #         logger.error(f"更新剧集外部ID失败: {e}")
    #         pass
    #     return season_core
    # endregion
    
    # region _apply_episode_detail
    # def _apply_episode_detail(self, session, media_file: FileAsset, metadata: ScraperEpisodeDetail) -> MediaCore:
    #     series_core = None
    #     season_core = None
    #     season_version_id = None
    #     title_val = getattr(metadata, "name", None) or ""
    #     try:
    #         if getattr(metadata, "series", None):
    #             series_core = self._apply_series_detail(session, media_file.user_id, metadata.series)
    #         if getattr(metadata, "season", None) and series_core:
    #             season_core = self._apply_season_detail(session, media_file.user_id, series_core, metadata.season)
    #             # 新增：创建/更新季版本（基于文件父文件夹路径）
    #             season_version_id = self._upsert_season_version(session, media_file, season_core)
    #     except Exception as e:
    #         logger.error(f"创建/更新季版本失败: {e}", exc_info=True)
    #         pass
    #     episode_core = session.exec(select(MediaCore).where(
    #         # MediaCore.id == media_file.core_id,
    #         MediaCore.user_id == media_file.user_id,
    #         MediaCore.kind == "episode",
    #         MediaCore.title == title_val,
    #         MediaCore.tmdb_id == getattr(metadata, "episode_id", None) if getattr(metadata, "episode_id", None) else None
    #         )).first()

    #     if not episode_core:
            
    #         episode_core = MediaCore(
    #             user_id=media_file.user_id,
    #             kind="episode",
    #             title=title_val,
    #             original_title=None,
    #             year=None,
    #             plot=getattr(metadata, "overview", None),
    #             display_rating=getattr(metadata, "vote_average", None),
    #             display_poster_path=getattr(metadata, "still_path", None),
    #             display_date=self._parse_dt(getattr(metadata, "air_date", None)),
    #             created_at=datetime.now(),
    #             updated_at=datetime.now()
    #         )
    #         session.add(episode_core)
    #         session.flush()
    #         media_file.core_id = episode_core.id
    #         logger.info(f"集中更新了media_file.core_id: {episode_core.id} for file: {media_file.id}")
    #     else:
    #         episode_core.kind = "episode"
    #         episode_core.title = title_val or episode_core.title
    #         episode_core.plot = getattr(metadata, "overview", None) or episode_core.plot
    #         episode_core.display_rating = getattr(metadata, "vote_average", None)
    #         episode_core.display_poster_path = getattr(metadata, "still_path", None)
    #         episode_core.display_date = self._parse_dt(getattr(metadata, "air_date", None))
    #         episode_core.updated_at = datetime.now()
    #         media_file.core_id = episode_core.id
    #     ep_ext = session.exec(select(EpisodeExt).where(
    #         # EpisodeExt.core_id == episode_core.id, 
    #         EpisodeExt.user_id == media_file.user_id,
    #         # EpisodeExt.series_core_id == (series_core.id if series_core else None),
    #         EpisodeExt.series_core_id == series_core.id if series_core else EpisodeExt.series_core_id,
    #         EpisodeExt.season_number == getattr(metadata, "season_number", 1),
    #         EpisodeExt.episode_number == getattr(metadata, "episode_number", 1)
    #         )).first()
    #     if not ep_ext:
    #         ep_ext = EpisodeExt(
    #             user_id=media_file.user_id, 
    #             core_id=episode_core.id, 
    #             series_core_id=series_core.id if series_core else None, 
    #             season_core_id=season_core.id if season_core else None, 
    #             episode_number=getattr(metadata, "episode_number", None) or 1, 
    #             season_number=getattr(metadata, "season_number", None) or 1
    #             )
    #         session.add(ep_ext)
    #     try:
    #         ep_ext.core_id = episode_core.id # 记录存在但是需要关联到新core_id
    #         ep_ext.title = title_val or ep_ext.title
    #         ep_ext.overview = getattr(metadata, "overview", None) or ep_ext.overview
    #         ep_ext.runtime = getattr(metadata, "runtime", None)
    #         ep_ext.rating = getattr(metadata, "vote_average", None)
    #         ep_ext.vote_count = getattr(metadata, "vote_count", None)
    #         ep_ext.still_path = getattr(metadata, "still_path", None)
    #         ep_ext.episode_type = getattr(metadata, "episode_type", None)
    #         ad = getattr(metadata, "air_date", None)
    #         ep_ext.aired_date = self._parse_dt(ad) if ad else ep_ext.aired_date
    #     except Exception as e:
    #         logger.error(f"更新EpisodeExt失败: {e}", exc_info=True)
    #         pass
    #     # try:
    #     #     if getattr(ep_ext, "still_path", None):
    #     #         art_s = session.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == episode_core.id, Artwork.type == "still", Artwork.preferred==True)).first()
    #     #         if not art_s:
    #     #             session.add(Artwork(user_id=media_file.user_id, core_id=episode_core.id, type="still", remote_url=ep_ext.still_path, provider=getattr(metadata, "provider", None), preferred=True))
    #     #         else:
    #     #             art_s.remote_url = art_s.remote_url or ep_ext.still_path
    #     #             art_s.provider = getattr(metadata, "provider", None) or getattr(art_s, "provider", None)
    #     #             art_s.preferred = True
    #     #             # art_s.exists_remote = True
    #     # except Exception:
    #     #     pass
    #     # try:
    #     #     if getattr(metadata, "provider", None) and getattr(metadata, "episode_id", None):
    #     #         existing = session.exec(select(ExternalID).where(
    #     #             ExternalID.user_id == media_file.user_id,
    #     #             ExternalID.core_id == episode_core.id,
    #     #             ExternalID.source == metadata.provider,
    #     #             ExternalID.key == str(metadata.episode_id)
    #     #         )).first()
    #     #         if not existing:
    #     #             session.add(ExternalID(user_id=media_file.user_id, core_id=episode_core.id, source=metadata.provider, key=str(metadata.episode_id)))
                
    #     #         episode_core.canonical_source = episode_core.canonical_source or metadata.provider
    #     #         episode_core.canonical_external_key = episode_core.canonical_external_key or str(metadata.episode_id)
    #     #         try:
    #     #             if metadata.provider == "tmdb":
    #     #                 sid = int(metadata.episode_id) if str(metadata.episode_id).isdigit() else None
    #     #                 if sid is not None:
    #     #                     episode_core.tmdb_id = episode_core.tmdb_id or sid
    #     #         except Exception:
    #     #             pass
    #     # except Exception as e:
    #     #     logger.error(f"应用剧集外部ID失败：{str(e)}", exc_info=True)
    #     #     pass
    #     try:
    #         self._upsert_artworks(session, media_file.user_id, episode_core.id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
    #     except Exception as e:
    #         logger.error(f"应用剧集封面失败：{str(e)}", exc_info=True)
    #         pass
    #     try:
    #         self._upsert_credits(session, media_file.user_id, episode_core.id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
    #     except Exception as e:
    #         logger.error(f"应用剧集演员失败：{str(e)}", exc_info=True)
    #         pass
        
    #     try:
    #         self._upsert_external_ids(session, media_file.user_id, episode_core.id, getattr(metadata, "external_ids", None))
    #     except Exception as e:
    #         logger.error(f"应用剧集外部ID失败：{str(e)}", exc_info=True)
    #         pass
        
        
    #     # 7. 核心逻辑：创建/更新单集子版本，并关联到季版本
    #     # 传入season_version_id，让单集版本关联到季版本
    #     version_id = self._upsert_media_version(session, media_file, episode_core, metadata, season_version_id)
    #     media_file.version_id = version_id  # 文件关联单集版本
    #     media_file.season_version_id = season_version_id  # 文件关联季版本
    #     media_file.updated_at = datetime.now()

    #     return episode_core
    
    # endregion
  
    # region _apply_movie_detail
    # def _apply_movie_detail(self, session, media_file: FileAsset, metadata: ScraperMovieDetail) -> MediaCore:
    #     # 添加或更新媒体核心元数据
    #     core = session.exec(select(MediaCore).where(
    #         # MediaCore.id == media_file.core_id,
    #         MediaCore.title == metadata.title,
    #         MediaCore.kind == "movie",
    #         MediaCore.user_id == media_file.user_id,
    #         MediaCore.tmdb_id == getattr(metadata, "movie_id", None) if getattr(metadata, "movie_id", None) else None
    #         )).first()
    #     year_val = None
    #     try:
    #         dt = self._parse_dt(getattr(metadata, "release_date", None))
    #         year_val = dt.year if dt else None
    #     except Exception:
    #         year_val = None
    #     if not core:
    #         core = MediaCore(
    #             user_id=media_file.user_id,
    #             kind="movie",
    #             title=metadata.title,
    #             original_title=getattr(metadata, "original_title", None),
    #             year=year_val,
    #             plot=getattr(metadata, "overview", None),
    #             display_rating=getattr(metadata, "vote_average", None),
    #             display_poster_path=getattr(metadata, "poster_path", None),
    #             display_date=self._parse_dt(getattr(metadata, "release_date", None)),
    #             created_at=datetime.now(),
    #             updated_at=datetime.now()
    #         )
    #         session.add(core)
    #         session.flush()
    #         media_file.core_id = core.id
    #         # logger.info(f"电影中更新了media_file.core_id: {core.id} for file: {media_file.id}")

    #     else:
    #         core.kind = "movie"
    #         core.title = metadata.title
    #         core.original_title = getattr(metadata, "original_title", None)
    #         core.year = year_val
    #         core.plot = getattr(metadata, "overview", None)
    #         core.display_rating = getattr(metadata, "vote_average", None)
    #         core.display_poster_path = getattr(metadata, "poster_path", None)
    #         core.display_date = self._parse_dt(getattr(metadata, "release_date", None))
    #         core.updated_at = datetime.now()
    #         media_file.core_id = core.id
        
    #     # 改元信息提供商ID
    #     # if getattr(metadata, "provider", None) and getattr(metadata, "movie_id", None):
    #     #     existing = session.exec(select(ExternalID).where(
    #     #         ExternalID.user_id == media_file.user_id,
    #     #         ExternalID.core_id == core.id,
    #     #         ExternalID.source == metadata.provider,
    #     #         ExternalID.key == str(metadata.movie_id)
    #     #     )).first()
    #     #     if not existing:
    #     #         session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=metadata.provider, key=str(metadata.movie_id)))
    #     #         session.flush()
    #     #     core.canonical_source = core.canonical_source or metadata.provider
    #     #     core.canonical_external_key = core.canonical_external_key or str(metadata.movie_id)
    #     #     try:
    #     #         if metadata.provider == "tmdb":
    #     #             mid = int(str(metadata.movie_id)) if str(metadata.movie_id).isdigit() else None
    #     #             if mid is not None:
    #     #                 core.tmdb_id = core.tmdb_id or mid
    #     #     except Exception:
    #     #         pass

    #     # 外部平台信息列表（tmdb，imdb）
    #     # try:
    #     #     for eid in getattr(metadata, "external_ids", []) or []:
    #     #         if not eid or not getattr(eid, "provider", None) or not getattr(eid, "external_id", None):
    #     #             continue
    #     #         existing = session.exec(select(ExternalID).where(
    #     #             ExternalID.user_id == media_file.user_id,
    #     #             ExternalID.core_id == core.id,
    #     #             ExternalID.source == eid.provider,
    #     #             ExternalID.key == str(eid.external_id)
    #     #         )).first()
    #     #         if not existing:
    #     #             session.add(ExternalID(user_id=media_file.user_id, core_id=core.id, source=eid.provider, key=str(eid.external_id)))
    #     # except Exception:
    #     #     pass
    #     # 电影详细信息
    #     movie_ext = session.exec(select(MovieExt).where(MovieExt.user_id == media_file.user_id, MovieExt.core_id == core.id)).first()
    #     if not movie_ext:
    #         movie_ext = MovieExt(user_id=media_file.user_id, core_id=core.id)
    #         session.add(movie_ext)
    #         session.flush()
    #     try:
    #         movie_ext.tagline = getattr(metadata, "tagline", None)
    #         movie_ext.title = getattr(metadata, "title", None) or movie_ext.title
    #         rv = getattr(metadata, "vote_average", None)
    #         movie_ext.rating = float(rv) if isinstance(rv, (int, float)) else movie_ext.rating
    #         movie_ext.overview = getattr(metadata, "overview", None) or movie_ext.overview
    #         movie_ext.origin_country = list(getattr(metadata, "origin_country", []))
    #         # logger.info(f"原国家: {getattr(metadata, 'origin_country', None)}")

    #     except Exception:
    #         pass
    #     try:
    #         rd = getattr(metadata, "release_date", None)
    #         movie_ext.release_date = self._parse_dt(rd) if rd else movie_ext.release_date
    #     except Exception:
    #         pass
    #     try:
    #         movie_ext.poster_path = getattr(metadata, "poster_path", None) or movie_ext.poster_path
    #         movie_ext.backdrop_path = getattr(metadata, "backdrop_path", None) or movie_ext.backdrop_path
    #         movie_ext.imdb_id = getattr(metadata, "imdb_id", None) or movie_ext.imdb_id
    #         movie_ext.runtime_minutes = getattr(metadata, "runtime", None) or movie_ext.runtime_minutes
    #         movie_ext.status = getattr(metadata, "status", None) or movie_ext.status
            
    #         # 替换原来的 raw_data 赋值行
    #         raw_data = getattr(metadata, 'raw_data', None)
    #         # 如果是 _DictWrapper 类型，获取其内部字典数据
    #         if isinstance(raw_data, _DictWrapper):
    #             raw_data = raw_data._data
    #         # 序列化为JSON字符串
    #         movie_ext.raw_data = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
           
    #     except Exception as e:
    #         logger.info(f"电影原始数据转换失败errer:{str(e)}")
    #         pass
    #     try:
    #         col = getattr(metadata, "belongs_to_collection", None)
    #         if isinstance(col, dict) and col.get("id"):
    #             collection = session.exec(select(Collection).where(Collection.id == col.get("id"))).first()
    #             if not collection:
    #                 collection = Collection(
    #                     id=col.get("id"),
    #                     name=col.get("name"),
    #                     poster_path=col.get("poster_path"),
    #                     backdrop_path=col.get("backdrop_path"),
    #                     overview=col.get("overview"),
    #                     created_at=datetime.now(),
    #                     updated_at=datetime.now()
    #                 )
    #                 session.add(collection)
    #             else:
    #                 collection.name = col.get("name")
    #                 collection.poster_path = col.get("poster_path")
    #                 collection.backdrop_path = col.get("backdrop_path")
    #                 collection.overview = col.get("overview")
    #                 collection.updated_at = datetime.now()
    #             movie_ext.collection_id = collection.id
    #     except Exception:
    #         pass
    #     # 图片海报等统一处理
    #     try:
    #         self._upsert_artworks(session, media_file.user_id, core.id, getattr(metadata, "provider", None), getattr(metadata, "artworks", None))
    #     except Exception:
    #         pass

    #     # 直接根据 metadata 的 poster/backdrop 写入 Artwork，避免需要二次查询
    #     # try:
    #     #     ppath = getattr(metadata, "poster_path", None)
    #     #     bpath = getattr(metadata, "backdrop_path", None)
    #     #     prov = getattr(metadata, "provider", None)
    #     #     if ppath:
    #     #         art_p = session.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "poster", Artwork.preferred==True)).first()
    #     #         if not art_p:
    #     #             session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="poster", remote_url=ppath, provider=prov, preferred=True))
    #     #         else:
    #     #             art_p.remote_url = art_p.remote_url or ppath
    #     #             art_p.provider = prov or getattr(art_p, "provider", None)
    #     #             art_p.preferred = True
    #     #         #     art_p.exists_remote = True
    #     #     if bpath:
    #     #         art_b = session.exec(select(Artwork).where(Artwork.user_id == media_file.user_id, Artwork.core_id == core.id, Artwork.type == "backdrop", Artwork.preferred==True)).first()
    #     #         if not art_b:
    #     #             session.add(Artwork(user_id=media_file.user_id, core_id=core.id, type="backdrop", remote_url=bpath, provider=prov, preferred=True))
    #     #         else:
    #     #             art_b.remote_url = art_b.remote_url or bpath
    #     #             art_b.provider = prov or getattr(art_b, "provider", None)
    #     #             art_b.preferred = True
    #     # except Exception:
    #     #     pass
    #     # 演职人员信息
    #     try:
    #         self._upsert_credits(session, media_file.user_id, core.id, getattr(metadata, "credits", None), getattr(metadata, "provider", None))
    #     except Exception:
    #         pass
    #     # 类型信息
    #     try:
    #         self._upsert_genres(session, media_file.user_id, core.id, getattr(metadata, "genres", []) or [])
    #     except Exception:
    #         pass
        
    #     try:
    #         self._upsert_external_ids(session, media_file.user_id, core.id, getattr(metadata, "external_ids", None))
    #     except Exception:
    #         pass
        
    #     # 7. 核心逻辑：创建/更新版本，并关联文件到版本
    #     version_id = self._upsert_media_version(session, media_file, core, metadata)
    #     media_file.version_id = version_id  # 文件关联版本
    #     media_file.updated_at = datetime.now()

    #     return core
    # endregion _apply_movie_detail
    
    # region apply_metadata
    # 方法入口
    # def apply_metadata(self, session, media_file: FileAsset, metadata,metadata_type: str,path_info: Dict) -> None:
    #     """
    #     一次性幂等地将刮削结果写入领域模型，并更新相关扩展信息

    #     事务说明:
    #         - 本方法内部仅执行 flush，不提交事务；由调用方统一 commit
    #     参数:
    #         session: SQLModel 会话
    #         media_file: 当前媒体文件记录（用于定位/创建 MediaCore）
    #         metadata: 新契约对象或 dict，支持 ScraperMovieDetail/ScraperSeriesDetail/ScraperEpisodeDetail/ScraperSearchResult 或其对应的 dict 形式
    #     行为:
    #         - 创建/更新 MediaCore 与 ExternalID
    #         - 电视剧分层映射: SeriesExt/SeasonExt/EpisodeExt        
    #         - 通用映射: Artwork/Genre/MediaCoreGenre/Person/Credit
    #         - 电影扩展与合集: MovieExt/Collection
    #     """
    #     # 如果 metadata 是 dict，包装为可通过 getattr 访问的对象
    #     if isinstance(metadata, dict):
    #         metadata = _DictWrapper(metadata)
        
    #     # core = session.exec(select(MediaCore).where(MediaCore.id == media_file.core_id)).first()
    #     core = None
    #     if metadata_type == "movie":
    #         # logger.info(f"应用电影元数据：文件ID={media_file.id}, 元数据={metadata}")
    #         core = self._apply_movie_detail(session, media_file, metadata)
 
    #     elif metadata_type == "episode":
    #         core = self._apply_episode_detail(session, media_file, metadata)
   
    #     elif metadata_type == "series":
    #         core = self._apply_series_detail(session, media_file.user_id, metadata)
    #         if not self._get_attr(media_file, "core_id"):
    #             media_file.core_id = core.id
            
    #     elif metadata_type == "search_result":
    #         core = self._apply_search_result(session, media_file, metadata)

    #     else:
    #         logger.warning(f"不支持的元数据类型: {metadata_type}")
    #         return
    #     # 更新文件的路径信息字段
    #     self._apply_file_path_info(session, media_file, path_info)
        
    #     # 更新mediacore缓存
    #     # self._refresh_display_cache_for_core(session, core, media_file.user_id)
    #     session.flush()
    # endregion
    
    # region
    # def _refresh_display_cache_for_core(self, session, core: MediaCore, user_id: int) -> None:
    #     try:
    #         if core.kind == 'movie':
    #             mx = session.exec(select(MovieExt).where(MovieExt.core_id == core.id, MovieExt.user_id == user_id)).first()
    #             if mx:
    #                 core.display_rating = getattr(mx, 'rating', None)
    #                 core.display_poster_path = getattr(mx, 'poster_path', None)
    #                 core.display_date = getattr(mx, 'release_date', None)
    #         elif core.kind == 'series':
    #             tv = session.exec(select(SeriesExt).where(SeriesExt.core_id == core.id, SeriesExt.user_id == user_id)).first()
    #             if tv:
    #                 core.display_rating = getattr(tv, 'rating', None)
    #                 core.display_poster_path = getattr(tv, 'poster_path', None)
    #             se_first = session.exec(select(SeasonExt).where(SeasonExt.series_core_id == core.id).order_by(SeasonExt.season_number)).first()
    #             if se_first and getattr(se_first, 'aired_date', None):
    #                 core.display_date = se_first.aired_date
    #                 try:
    #                     core.year = se_first.aired_date.year
    #                 except Exception:
    #                     pass
    #             if tv and getattr(tv, 'rating', None) is not None and core.display_rating is None:
    #                 core.display_rating = tv.rating
    #         elif core.kind == 'season':
    #             se = session.exec(select(SeasonExt).where(SeasonExt.core_id == core.id, SeasonExt.user_id == user_id)).first()
    #             if se:
    #                 try:
    #                     if se.series_core_id:
    #                         series = session.exec(select(MediaCore).where(MediaCore.id == se.series_core_id)).first()
    #                         if series:
    #                             core.title = f"{series.title} 第{se.season_number}季"
    #                 except Exception:
    #                     pass
    #                 core.display_rating = getattr(se, 'rating', None)
    #                 core.display_poster_path = getattr(se, 'poster_path', None)
    #                 core.display_date = getattr(se, 'aired_date', None)
    #         elif core.kind == 'episode':
    #             ep = session.exec(select(EpisodeExt).where(EpisodeExt.core_id == core.id, EpisodeExt.user_id == user_id)).first()
    #             if ep:
    #                 core.title = ep.title or core.title
    #                 core.display_rating = getattr(ep, 'rating', None)
    #                 core.display_poster_path = None
    #                 core.display_date = getattr(ep, 'aired_date', None)
    #     except Exception:
    #         pass
    # endregion
    
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


persistence_service = MetadataPersistenceService()
