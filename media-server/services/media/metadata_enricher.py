"""
刮削器元数据服务 - 使用插件化架构
"""
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

from sqlmodel import select

from core.db import get_session as get_db_session
from models.media_models import MediaCore
from models.media_models import FileAsset
from services.scraper import scraper_manager, MediaType
from services.storage.storage_service import StorageService
from services.utils.filename_parser import FilenameParser, ParserMode, ParseInput
from dataclasses import asdict

logger = logging.getLogger(__name__)


class MetadataEnricher:
    """元数据丰富器 - 使用插件化刮削器"""
    
    def __init__(self):

        """
        初始化元数据丰富器
        
        创建存储服务和文件名解析器实例
        """
        self.storage_service = StorageService()
        self.parser = FilenameParser()
    
    async def enrich_media_file(self, file_id: int, storage_id: Optional[int] = None) -> bool:
        """
        丰富单个媒体文件的元数据

        流程：
        1. 获取文件信息和存储客户端
        2. 解析文件名提取标题、年份、季集信息
        3. 搜索元数据并进行类型校正（Movie/TV），支持语言回退
        4. 按校正类型获取详情（TV 优先季缓存/单集回退）
        5. 将覆盖版 ScraperResult 一次性持久化并绑定版本
        6. 入队侧车本地化任务（NFO/Poster/Fanart）
        
        req:
            file_id: 文件ID
            language: 首选语言（默认中文）
            storage_id: 存储配置ID（可选）完全不用,file_id查表就可以查到
        
        resp:
            bool: 是否成功完成元数据丰富

        """
       
        try:
            # 使用同步方式访问数据库
            from core.db import get_session as get_db_session
            
            with next(get_db_session()) as session:
                # 获取媒体文件信息
                media_file = session.exec(select(FileAsset).where(FileAsset.id == file_id)).first()
                
                if not media_file:
                    logger.error(f"媒体文件不存在: {file_id}")
                    return False
                
                # 获取存储客户端 - 优先使用传入的storage_id，否则使用文件关联的存储配置ID
                if storage_id:
                    storage_client = await self.storage_service.get_client(storage_id)
                    if not storage_client:
                        logger.error(f"无法获取存储客户端: {storage_id}")
                        return False
                else:
                    # 如果没有提供storage_id，尝试从文件路径推断或使用默认存储
                    logger.warning("未提供storage_id，跳过侧车文件写入")
                    storage_client = None
                
                # 解析文件名（Deep 模式，若快照存在则重用）
                seed_parent = str(Path(media_file.full_path).parent.name) # 父目录名作为种子
              
                seed_title = media_file.filename or Path(media_file.full_path).name
                # seed_year = None
                # seed_season = None
                # seed_episode = None
                # 名称解析器
                out = self.parser.parse(
                    ParseInput(
                        filename_raw=seed_title,
                        parent_hint=seed_parent,
                        grandparent_hint=str(Path(media_file.full_path).parent.parent.name) if Path(media_file.full_path).parent.parent else None,
                        full_path=str(Path(media_file.full_path)),            
                    ),
                    ParserMode.DEEP
                )
                title = out.title or (media_file.filename or Path(media_file.full_path).name)
                year = out.year if out.year is not None else None
                season = out.season_number if out.season_number is not None else None
                episode = out.episode_number if out.episode_number is not None else None
                language = out.language or None
                
                # 确定媒体类型(movie or tv)
                media_type = self._determine_media_type(media_file, season, episode)
                
                # 搜索元数据
                logger.info(f"🔍 开始搜索元数据: '{title}' ({year or '未知年份'}) - 类型: {media_type.value}")
                # 统一由管理器在启动期启用插件；此处仅确保默认插件可用
                try:
                    await scraper_manager.ensure_default_plugins()
                except Exception as e:
                    logger.warning(f"⚠️ 插件初始化检查失败: {e}")
                    return False
                
                # 始终使用年份进行搜索（推荐配置）
                logger.debug(f"🎯 搜索参数: 标题='{title}', 年份={year }, 语言={language}")
                
                # 调用的是插件中的search方法，中间加了语言回退策略
                search_results, corrected_type = await scraper_manager.search_with_type_correction(
                    title=title,
                    year=year,
                    initial_type=media_type,
                    language=language
                )
                # logger.info(f'搜索结果元数据: {search_results.raw_data}')
                logger.debug(f"🔍 搜索结果数量: {len(search_results)}")
                
                
                
                if not search_results:
                    logger.warning(f"❌ 未找到匹配的元数据: {title} ({year})")
                    return False
                
                # 选择最佳匹配
                best_match = search_results[0]
                logger.info(f"🏆 选择最佳匹配: {best_match.title} ({best_match.year}) - ID: {getattr(best_match, 'id', None)}")
                
                # 获取详情：按校正类型调用新细分接口
                details_obj = None
                try:
                    plugin = scraper_manager.get_plugin(best_match.provider)
                    if plugin and getattr(best_match, 'id', None):
                        if corrected_type == MediaType.MOVIE:
                            details_obj = await plugin.get_movie_details(best_match.id, language)
                            if details_obj:
                                logger.debug(f"✅ 电影详细信息获取成功: {details_obj.title}")
                        else:
                            if season is not None and episode is not None:
                                ep = await plugin.get_episode_details(best_match.id, season, episode, language)
                                if ep:
                                    try:
                                        sd = await plugin.get_series_details(best_match.id, language)
                                    except Exception:
                                        sd = None
                                    try:
                                        se = await plugin.get_season_details(best_match.id, season, language)
                                    except Exception:
                                        se = None
                                    if sd:
                                        ep.series = sd
                                    if se:
                                        ep.season = se
                                    details_obj = ep
                                    logger.debug("✅ 单集详细信息获取成功并补充系列/季信息")
                            if details_obj is None:
                                details_obj = await plugin.get_series_details(best_match.id, language)
                                if details_obj:
                                    logger.debug(f"✅ 只获取到系列详细信息: {details_obj.name}")
                    else:
                        logger.warning(f"⚠️ 未找到插件或无ID: provider={getattr(best_match, 'provider', None)}")
                except Exception as e:
                    logger.error(f"❌ 获取详细信息失败: {e}")
                
                # 入队持久化任务（解耦写库）
                try:
                    from services.task import Task, TaskType, TaskPriority, get_task_queue_service
                    tq = get_task_queue_service()
                    await tq.connect()
                    contract_type = None
                    payload = None
                    if details_obj and hasattr(details_obj, 'movie_id'):
                        contract_type = 'movie'
                        payload = asdict(details_obj)
                        external_key = str(getattr(details_obj, 'movie_id', best_match.id))
                        scope = 'movie_single'
                    elif details_obj and hasattr(details_obj, 'episode_number'):
                        contract_type = 'episode'
                        payload = asdict(details_obj)
                        external_key = str(getattr(details_obj, 'episode_id', f"{best_match.id}:{season}:{episode}"))
                        scope = 'episode_single'
                    elif details_obj and hasattr(details_obj, 'series_id'):
                        contract_type = 'series'
                        payload = asdict(details_obj)
                        external_key = str(getattr(details_obj, 'series_id', best_match.id))
                        scope = 'series_group'
                    else:
                        contract_type = 'series'
                        payload = asdict(best_match)
                        external_key = str(getattr(best_match, 'id', media_file.id))
                        scope = 'series_group'
                    quality = None
                    if getattr(out, 'resolution_tags', None):
                        quality = out.resolution_tags[0] if len(out.resolution_tags) > 0 else None
                    source = None
                    if getattr(out, 'quality_tags', None):
                        qt = [q.lower() for q in out.quality_tags]
                        for s in ['web', 'bluray', 'dvd', 'hdtv']:
                            if any(s in q for q in qt):
                                source = s
                                break
                    idempotency_key = f"{media_file.user_id}:{media_file.id}:{best_match.provider}:{contract_type}:{external_key}"
                    persist_task = Task(
                        task_type=TaskType.PERSIST_METADATA,
                        priority=TaskPriority.NORMAL,
                        params={
                            "file_id": media_file.id,
                            "user_id": media_file.user_id,
                            "storage_id": storage_id,
                            "contract_type": contract_type,
                            "contract_payload": payload,
                            "version_context": {
                                "scope": scope,
                                "quality": quality,
                                "source": source
                            },
                            "provider": best_match.provider,
                            "language": language,
                            "idempotency_key": idempotency_key
                        },
                        max_retries=3,
                        retry_delay=300,
                        timeout=3600
                    )
                    ok = await tq.enqueue_task(persist_task)
                    logger.info(f"元数据持久化任务已入队: {persist_task.id}")
                    if not ok:
                        logger.error("持久化任务入队失败")
                        return False
                except Exception as e:
                    logger.error(f"持久化任务入队异常: {e}")
                    return False

                # 异步本地化：入队侧车任务
                try:
                    from services.task import Task, TaskType, TaskPriority, get_task_queue_service
                    from core.config import get_settings
                    settings = get_settings()
                    if not bool(getattr(settings, "SIDE_CAR_LOCALIZATION_ENABLED", True)):
                        logger.info("侧车本地化关闭（env），跳过入队")
                    else:
                        if storage_id is None:
                            logger.error("侧车本地化启用但缺少storage_id，跳过入队")
                        else:
                            tq = get_task_queue_service()
                            await tq.connect()
                            sidecar_task = Task(
                                task_type=TaskType.SIDECAR_LOCALIZE,
                                priority=TaskPriority.LOW,
                                params={
                                    "file_id": media_file.id,
                                    "storage_id": storage_id,
                                    "language": language,
                                    "user_id": media_file.user_id
                                },
                                max_retries=3,
                                retry_delay=300,
                                timeout=1800
                            )
                            ok2 = await tq.enqueue_task(sidecar_task)
                            if ok2:
                                logger.info(f"侧车本地化任务已入队: {sidecar_task.id} -> file_id={media_file.id}")
                            else:
                                logger.error("侧车任务入队失败，跳过本地化")
                except Exception as e:
                    logger.error(f"侧车本地化任务入队异常，跳过本地化: {e}")
                
                return True
                
        except Exception as e:
            logger.exception(f"丰富媒体文件元数据失败: {e}")
            return False
    
    def _determine_media_type(self, media_file: FileAsset, season: Optional[int], episode: Optional[int]) -> MediaType:
        """
        确定媒体类型
        
        根据季集信息初步判断是电影、电视剧还是单集（仅作为搜索初始类型）
        
        Args:
            media_file: 媒体文件对象
            season: 季号（如果有）
            episode: 集号（如果有）
            
        Returns:
            MediaType: 媒体类型枚举值"
        """
        if season is not None or episode is not None:
            if episode is not None:
                return MediaType.TV_EPISODE
            else:
                return MediaType.TV_SERIES
        else:
            return MediaType.MOVIE

    
    async def enrich_multiple_files(self, file_ids: List[int], 
                                   language: str = "zh-CN", 
                                   storage_id: Optional[int] = None) -> Dict[int, bool]:
        """
        丰富多个媒体文件的元数据
        
        并发驱动器：逐文件执行单文件内核流程，保证每个文件的事务与容错独立
        
        Args:
            file_ids: 文件ID列表
            language: 首选语言
            storage_id: 存储配置ID（可选）
            
        Returns:
            Dict[int, bool]: 文件ID到成功状态的映射"""
        
        results = {}
        
        # 并发处理多个文件
        tasks = []
        for file_id in file_ids:
            task = asyncio.create_task(
                self._enrich_single_file_safe(file_id, language, storage_id)
            )
            tasks.append((file_id, task))
        
        # 等待所有任务完成
        for file_id, task in tasks:
            try:
                success = await task
                results[file_id] = success
            except Exception as e:
                logger.error(f"丰富文件 {file_id} 失败: {e}")
                results[file_id] = False
        
        return results
    
    async def _enrich_single_file_safe(self, file_id: int, language: str, storage_id: Optional[int]) -> bool:
        """
        安全地丰富单个文件
        
        包装 enrich_media_file，提供异常捕获保证批处理稳定
        
        Args:
            file_id: 文件ID
            language: 语言
            storage_id: 存储配置ID（可选）
            
        Returns:
            bool: 是否成功完成丰富" 
        """
        try:
            return await self.enrich_media_file(file_id, language, storage_id=storage_id)
        except Exception as e:
            logger.error(f"丰富文件 {file_id} 异常: {e}")
            return False
    


# 全局元数据丰富器实例
metadata_enricher = MetadataEnricher()
