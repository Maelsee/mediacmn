"""
刮削器元数据服务 - 使用插件化架构
"""
import asyncio
import logging
# from pathlib import Path
from typing import Dict, List, Optional, Any, TypedDict
# from dataclasses import dataclass, field
from sqlmodel import select
from guessit import guessit
from core.db import AsyncSessionLocal
# from models.media_models import MediaCore
from models.media_models import FileAsset
from models.user import User
from services.scraper import scraper_manager, MediaType
from services.storage.storage_service import storage_service
# from services.utils.filename_parser import FilenameParser, ParserMode, ParseInput
# from dataclasses import asdict
from services.scraper.base import   ScraperSearchResult

logger = logging.getLogger(__name__)

# 类型别名：避免序列化/反序列化开销
# MetadataResult 为 dict 而非 dataclass，消除 Enum 转换成本
# MetadataResult = Dict[str, Any]  # 结构: {user_id, file_id, contract_type, contract_payload} 
class MetadataResult(TypedDict):
    user_id: int
    file_id: int
    contract_type: str
    contract_payload: Dict[str, Any]
    path_info: Dict[str, Any]
    success: bool
    error_msg: str

# class MetadataResult(BaseModel):
#     user_id: int
#     file_id: int
#     contract_type: str
#     # payload 可以是任何 Scraper 模型，或者是 dict
#     contract_payload: Dict[str, Any] = {}
#     path_info: Dict[str, Any] = {}
#     success: bool
#     error_msg: str = ""

class MetadataEnricher:
    """元数据丰富器 - 使用插件化刮削器"""
    
    def __init__(self):

        """
        初始化元数据丰富器
        
        创建存储服务和文件名解析器实例
        """
        self.storage_service = storage_service
        # self.parser = FilenameParser()
    
    def _get_best_match(self,search_results: List[ScraperSearchResult],parsed_data: dict,) -> Optional[ScraperSearchResult]:  # parsed_data名称解析器结果：{title: str, year: Optional[int], language: Optional[str], country: Optional[str]}
    
        """
        从搜索结果中选择最优匹配
        :param search_results: 插件返回的搜索结果列表
        :param parsed_data: 名称解析器结果（必须包含title，其他可选）
        :return: 最优匹配结果，无结果时返回None
        """
        if not search_results:
            logger.warning("搜索结果为空，无法选择最优匹配")
            return None
        if not parsed_data.get("title"):
            logger.error("名称解析器未返回title，无法匹配")
            return None

        # -------------------------- 步骤1：过滤无效结果 --------------------------
        parsed_title = parsed_data["title"].strip()
        parsed_country = parsed_data.get("country")  # 解析的地区（可选）
        filtered_results = []

        for result in search_results:
            # 1.1 标题相关性过滤：解析的title必须是结果title/original_name的子集（避免同名无关结果）
            result_title_candidates = [t for t in [result.title, result.original_name] if t and t.strip()]
            title_matched = any(parsed_title in candidate.strip() for candidate in result_title_candidates)
            if not title_matched:
                continue

            # 1.2 地区合理性过滤：解析有country时，结果origin_country必须包含该地区（避免海外版本）
            if parsed_country and parsed_country.strip() not in [c.strip() for c in result.origin_country]:
                continue

            # 符合过滤条件，加入候选列表
            filtered_results.append(result)

        # 若过滤后无结果，保留原搜索结果（避免过度过滤导致无匹配）
        if not filtered_results or len(filtered_results) <=2 :
            logger.debug(f"过滤后候选结果过少，保留原搜索结果（共{len(search_results)}条）")
            filtered_results = search_results

        # -------------------------- 步骤2：给候选结果打分 --------------------------
        scored_results = []
        for result in filtered_results:
            score = 0  # 总分初始化为0
            result_year = result.year  # 搜索结果的年份（已存在于ScraperSearchResult）
            result_lang = result.original_language  # 搜索结果的原始语言
            result_vote_avg = result.vote_average or 0.0  # 评分（默认0）
            result_vote_count = result.vote_count or 0  # 投票数（默认0）
            result_popularity = result.popularity or 0.0  # 流行度（默认0）

            # 2.1 标题精确匹配（权重30：核心维度，完全匹配优先级最高）
            if any(
                parsed_title == candidate.strip() 
                for candidate in [result.title, result.original_name] if candidate and candidate.strip()
            ):
                score += 30

            # 2.2 年份匹配（权重25：核心维度，区分同名称不同版本）
            parsed_year = parsed_data.get("year")
            if parsed_year and result_year:
                year_diff = abs(parsed_year - result_year)
                if year_diff == 0:  # 年份完全一致
                    score += 25
                elif 1 <= year_diff <= 2:  # 年份差距1-2年（兼容解析误差）
                    score += 10

            # 2.3 地区匹配（权重15：辅助维度，优先本地版本）
            if parsed_country and parsed_country.strip() in [c.strip() for c in result.origin_country]:
                score += 15

            # 2.4 语言匹配（权重15：辅助维度，优先原始语言匹配）
            parsed_lang = parsed_data.get("language")
            if parsed_lang and result_lang:
                # 支持前缀匹配（如zh-CN匹配zh，en-US匹配en）
                parsed_lang_prefix = parsed_lang.split("-")[0].strip()
                result_lang_prefix = result_lang.split("-")[0].strip()
                if parsed_lang_prefix == result_lang_prefix:
                    score += 15

            # 2.5 评分与投票数（权重10：可靠性维度，避免低投票高评分的异常结果）
            # 公式：(评分/10)*5 + (min(投票数, 100)/100)*5 → 评分和投票各占5分，投票数上限100（避免极端值）
            vote_score = (result_vote_avg / 10) * 5 + (min(result_vote_count, 100) / 100) * 5
            score += round(vote_score, 1)  # 保留1位小数，避免分数膨胀

            # 2.6 流行度（权重5：热度维度，优先高热度结果）
            # 流行度归一化：取0-5分（流行度上限按50计算，超过50按5分算）
            popularity_score = min(result_popularity / 10, 5)  # 50/10=5，适配TMDB流行度范围
            score += round(popularity_score, 1)

            # 记录结果与分数
            scored_results.append((result, round(score, 1)))
            # logger.info(f"结果打分：title={result.title}, id={result.id}, 总分={round(score,1)}")

        # -------------------------- 步骤3：排序并选择最优结果 --------------------------
        # 排序规则：1.总分降序 → 2.投票数降序（同分下优先高投票） → 3.流行度降序（再同分优先高热度）
        scored_results.sort(
            key=lambda x: (-x[1], -x[0].vote_count or 0, -x[0].popularity or 0.0)
        )

        # 取排序后的第一个结果作为最优匹配
        best_match = scored_results[0][0]
        logger.debug(
            f"最优匹配结果：title={best_match.title}, id={best_match.id}, "
            f"总分={scored_results[0][1]}, 来源={best_match.provider}"
        )
        return best_match

    async def enrich_media_file(self, file_asset: FileAsset, language: str = '') -> MetadataResult:
        """
        丰富单个媒体文件元数据（参数改为FileAsset）
        不再查询数据库，直接使用传入的file_asset处理
        """
        logger.debug(f'用户语言{language}')
        try:
            # -------------------------- 1. 解析文件名（直接用file_asset的full_path） --------------------------
            # path_info = guessit(file_asset.full_path)
            # 将 CPU 密集型的 guessit 调用放到线程池中执行
            path_info = await asyncio.to_thread(guessit, file_asset.full_path)
            title = path_info.get("title")
            season = path_info.get("season")
            episode = path_info.get("episode")
            year = path_info.get("year")
            country = path_info.get("country")  # 默认中国
            corrected_type = MediaType.MOVIE if path_info.get("type") == "movie" else MediaType.TV_EPISODE


            # 异步搜索元数据
            logger.info(f"🔍 搜索参数：title='{title}', 年份={year}, 语言={language}, 类型={corrected_type.value}")
            search_results = await scraper_manager.search_media(
                title=title,
                year=year,
                media_type=corrected_type,
                language=language
            )

            if not search_results:
                err_msg = f"未找到元数据: title='{title}' (年份={year})"
                logger.warning(err_msg)
                return {
                    "user_id": file_asset.user_id,
                    "file_id": file_asset.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": err_msg
                }

            # -------------------------- 3. 选择最优匹配与获取详情 --------------------------
            parsed_data = {"title": title, "year": year, "language": language, "country": country}
            best_match = self._get_best_match(search_results, parsed_data)
            logger.info(f"🏆 最佳匹配：title='{best_match.title}', 年份={best_match.year}, ID={getattr(best_match, 'id', None)}")
            if not best_match:
                err_msg = f"无最优匹配结果: title='{title}' (年份={year})"
                logger.warning(err_msg)
                return {
                    "user_id": file_asset.user_id,
                    "file_id": file_asset.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": err_msg
                }

            # 获取元数据详情
            contract_type = ""
            details_obj = None
            try:
                plugin = scraper_manager.get_plugin(best_match.provider)
                if not plugin or not getattr(best_match, "id", None):
                    raise ValueError(f"插件不存在或无ID: provider={best_match.provider}")

                if corrected_type == MediaType.MOVIE:
                    contract_type = "movie"
                    details_obj = await plugin.get_movie_details(best_match.id, language)
                else:
                    if season is not None and episode is not None:
                        contract_type = "episode"
                        details_obj = await plugin.get_episode_details(best_match.id, season, episode, language)
                        # 补充季/系列信息
                        if details_obj:
                            try:
                                details_obj.series = await plugin.get_series_details(best_match.id, language)
                            except Exception as e:
                                logger.warning(f"补全系列信息失败: {str(e)}")
                            try:
                                details_obj.season = await plugin.get_season_details(best_match.id, season, language)
                            except Exception as e:
                                logger.warning(f"补全季信息失败: {str(e)}")
                    if details_obj is None:
                        contract_type = "series"
                        details_obj = await plugin.get_series_details(best_match.id, language)
                logger.debug(f"详情获取成功: contract_type={contract_type}")

            except Exception as e:
                err_msg = f"详情获取失败: {str(e)}"
                logger.error(err_msg)
                details_obj = best_match  # 降级使用搜索结果
                contract_type = "search_result"

            # -------------------------- 4. 返回结果 --------------------------
            return {
                "user_id": file_asset.user_id,
                "file_id": file_asset.id,
                "contract_type": contract_type,
                # 【关键修改】：使用 model_dump() 替代 asdict()
                # 这里的 details_obj 可能是 MovieDetail, EpisodeDetail 或 SearchResult
                "contract_payload": details_obj.model_dump() if details_obj else {},
                "path_info": path_info,
                "success": True,
                "error_msg": ""
            }

        # -------------------------- 全局异常捕获 --------------------------
        except Exception as e:
            err_msg = f"元数据丰富失败: file_id={file_asset.id}, 错误={str(e)}"
            logger.exception(err_msg)
            return {
                "user_id": file_asset.user_id,
                "file_id": file_asset.id,
                "contract_type": "",
                "contract_payload": {},
                "path_info": {},
                "success": False,
                "error_msg": err_msg
            }

    async def enrich_multiple_files(self, file_ids: List[int],user_id: int,max_concurrency: int = 20) -> List[MetadataResult]:
        """
        批量丰富元数据（核心优化：一次性查库）
        1. 异步批量查询所有file_ids对应的FileAsset
        2. 直接调用enrich_media_file（传FileAsset）
        3. 处理查不到FileAsset的file_id
        """
        results: List[MetadataResult] = []
        semaphore = asyncio.Semaphore(max_concurrency)  # 并发控制

        # -------------------------- 核心步骤：一次性查询所有FileAsset --------------------------
        async with AsyncSessionLocal() as session:
            # 批量查询：IN条件一次获取所有数据，减少数据库连接次数
            stmt = select(FileAsset).where(FileAsset.id.in_(file_ids))
            result = await session.exec(stmt)
            file_assets = result.all()

            user_stmt = select(User).where(User.id == user_id)
            user_result = await session.exec(user_stmt)
            language = user_result.first().language
        
           

        # 构建file_id到FileAsset的映射，方便快速匹配
        file_asset_map: Dict[int, FileAsset] = {fa.id: fa for fa in file_assets}

        # -------------------------- 处理每个file_id（含不存在的情况） --------------------------
        # 1. 先处理查不到FileAsset的file_id，返回错误结果
        for file_id in file_ids:
            if file_id not in file_asset_map:
                err_msg = f"文件不存在: file_id={file_id}"
                logger.error(err_msg)
                results.append({
                    "user_id": 0,
                    "file_id": file_id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": {},
                    "success": False,
                    "error_msg": err_msg
                })

        # 2. 异步处理查到的FileAsset（用信号量控制并发）
        async def _bound_enrich(file_asset: FileAsset):
            async with semaphore:
                try:
                    # 直接调用enrich_media_file，传file_asset、language
                    return await self.enrich_media_file(
                        file_asset=file_asset,
                        language=language,
                    )
                except Exception as e:
                    # 在协程内部捕获异常，确保单个任务失败不影响其他任务
                    # 并返回一个标准的错误结果格式
                    logger.error(f"处理文件 {file_asset.id} 时发生内部错误: {e}", exc_info=True)
                    return {
                        "user_id": file_asset.user_id,
                        "file_id": file_asset.id,
                        "contract_type": "",
                        "contract_payload": {},
                        "path_info": {},
                        "success": False,
                        "error_msg": f"内部处理错误: {str(e)}"
                    }


        # 创建任务并执行
        tasks = [asyncio.create_task(_bound_enrich(fa)) for fa in file_asset_map.values()]
        completed_results = await asyncio.gather(*tasks, return_exceptions=True) # <-- 关键改动

        # 处理 gather 返回的结果，因为 return_exceptions=True，结果中可能包含 Exception 对象
        for res in completed_results:
            if isinstance(res, Exception):
                # 这种情况理论上不应该发生，因为我们在 _bound_enrich 中已经捕获了所有异常
                # 但作为最后一道防线，以防万一
                logger.critical(f"未知异常被 gather 捕获: {res}", exc_info=True)
                # 可以选择添加一个通用的错误结果，或者直接忽略
                continue
            else:
                # res 是 MetadataResult 字典
                results.append(res)

        return results

    # region
    # async def enrich_media_file(self, file_id: int) -> MetadataResult:
    #     """
    #     丰富单个媒体文件的元数据

    #     流程：
    #     1. 获取文件信息和存储客户端
    #     2. 解析文件名提取标题、年份、季集信息
    #     3. 搜索元数据并进行类型校正（Movie/TV），支持语言回退
    #     4. 按校正类型获取详情（TV 优先季缓存/单集回退）
    #     5. 将覆盖版 ScraperResult 一次性持久化并绑定版本
    #     6. 入队侧车本地化任务（NFO/Poster/Fanart）
        
    #     req:
    #         file_id: 文件ID
    #         language: 首选语言（默认中文）
    #         storage_id: 存储配置ID（可选）完全不用,file_id查表就可以查到
        
    #     resp:
    #         bool: 是否成功完成元数据丰富

    #     """
       
    #     try:
    #         # 使用同步方式访问数据库
    #         from core.db import get_session as get_db_session
            
    #         with next(get_db_session()) as session:
    #             # 获取媒体文件信息
    #             media_file = session.exec(select(FileAsset).where(FileAsset.id == file_id)).first()
                
    #             # 1. 修复：媒体文件不存在时，返回包含错误信息的字典
    #             if not media_file:
    #                 logger.error(f"媒体文件不存在: {file_id}")
    #                 return {
    #                     "user_id": 0,  # 无用户ID
    #                     "file_id": file_id,  # 保留请求的file_id
    #                     "contract_type": "",  # 空类型
    #                     "contract_payload": {},  # 空 payload
    #                     "path_info": {},  # 空路径信息
    #                     "success": False,  # 新增：标识失败
    #                     "error_msg": "媒体文件不存在"  # 新增：错误描述
    #                 }
                
    #             # 获取存储客户端 - 优先使用传入的storage_id，否则使用文件关联的存储配置ID
    #             # if storage_id:
    #             #     storage_client = await self.storage_service.get_client(storage_id)
    #             #     if not storage_client:
    #             #         logger.error(f"无法获取存储客户端: {storage_id}")
    #             #         return False
    #             # else:
    #             #     # 如果没有提供storage_id，尝试从文件路径推断或使用默认存储
    #             #     logger.warning("未提供storage_id，跳过侧车文件写入")
    #             #     storage_client = None
                
    #             # # 解析文件名（Deep 模式，若快照存在则重用）
    #             # seed_parent = str(Path(media_file.full_path).parent.name) # 父目录名作为种子
              
    #             # seed_title = media_file.filename or Path(media_file.full_path).name
    #             # # seed_year = None
    #             # # seed_season = None
    #             # # seed_episode = None
    #             # # 名称解析器
    #             # out = self.parser.parse(
    #             #     ParseInput(
    #             #         filename_raw=seed_title,
    #             #         parent_hint=seed_parent,
    #             #         grandparent_hint=str(Path(media_file.full_path).parent.parent.name) if Path(media_file.full_path).parent.parent else None,
    #             #         full_path=str(Path(media_file.full_path)),            
    #             #     ),
    #             #     ParserMode.DEEP
    #             # )
    #             # title = out.title or (media_file.filename or Path(media_file.full_path).name)
    #             # year = out.year if out.year is not None else None
    #             # season = out.season_number if out.season_number is not None else None
    #             # episode = out.episode_number if out.episode_number is not None else None
    #             # country =  "CN"  # 强制中国
    #             # language = "zh-CN"  # 强制中文

    #             # 解析文件名（guessit）
    #             path_info = guessit(media_file.full_path)
               
    #             title = path_info.get("title")      
    #             season = path_info.get("season")               
    #             episode = path_info.get("episode")
    #             episode_title = path_info.get("episode_title")
    #             year = path_info.get("year")               
    #             language = path_info.get("language","zh-CN")       
    #             country = path_info.get("country")
    #             corrected_type = MediaType.MOVIE if path_info.get("type") == "movie" else MediaType.TV_EPISODE
                
                

                
    #             # 确定媒体类型(movie or tv)
    #             # corrected_type = self._determine_media_type(media_file, season, episode)
                
    #             # 搜索元数据
    #             # logger.info(f"🔍 开始搜索元数据: '{title}' ({year or '未知年份'}) - 类型: {corrected_type} - 解析信息: {path_info}")
    #             # logger.info(f"🔍 解析信息: {path_info}")

    #             # 统一在启动期初始化插件；此处调用startup具备幂等保障
    #             # 2. 修复：插件启动失败时，返回包含错误信息的字典
    #             try:
    #                 await scraper_manager.startup()
    #             except Exception as e:
    #                 err_msg = f"插件系统启动失败: {str(e)}"
    #                 logger.warning(err_msg)
    #                 return {
    #                     "user_id": media_file.user_id,
    #                     "file_id": file_id,
    #                     "contract_type": "",
    #                     "contract_payload": {},
    #                     "path_info": {},
    #                     "success": False,
    #                     "error_msg": err_msg
    #                 }
                
    #             # 始终使用年份进行搜索（推荐配置）
    #             logger.debug(f"🎯 搜索参数: 标题='{title}', 年份={year }, 语言={language}")
                
    #             search_results = await scraper_manager.search_media_with_policy(
    #                 title=title, 
    #                 year=year, 
    #                 media_type=corrected_type,
    #                 language=language
    #             )
    #             # logger.info(f'搜索结果元数据: {search_results.raw_data}')
    #             logger.debug(f"🔍 搜索结果数量: {len(search_results)}")
                         
                
    #             if not search_results:
    #                 err_msg = f"未找到匹配的元数据: {title} ({year})"
    #                 logger.warning(err_msg)
    #                 return {
    #                     "user_id": media_file.user_id,
    #                     "file_id": file_id,
    #                     "contract_type": "",
    #                     "contract_payload": {},
    #                     "path_info": path_info,  # 保留解析到的路径信息
    #                     "success": False,
    #                     "error_msg": err_msg
    #                 }
                
    #             # 选择最佳匹配
    #             # 1. 整理名称解析器数据为parsed_data
    #             parsed_data = {
    #                 "title": title,  # 解析的名称（必选）
    #                 "year": year,    # 解析的年份（可选，如2020）
    #                 "language": language,  # 解析的语言（可选，如zh-CN）
    #                 "country": country  # 解析的地区（可选，如CN）
    #             }
    #             # 2. 调用get_best_match获取最优结果
    #             best_match = self._get_best_match(search_results, parsed_data)
                
    #             logger.info(f"🏆 选择最佳匹配: {best_match.title} ({best_match.year}) - ID: {getattr(best_match, 'id', None)}")
                
    #             # 获取详情：按校正类型调用新细分接口
    #             contract_type = 'search_result' # 刮削类型, 'movie', 'series', 'episode'
    #             details_obj = None # 刮削到的元数据内容
    #             try:
    #                 plugin = scraper_manager.get_plugin(best_match.provider)
    #                 if plugin and getattr(best_match, 'id', None):
    #                     if corrected_type == MediaType.MOVIE:
    #                         contract_type = 'movie'
    #                         details_obj = await plugin.get_movie_details(best_match.id, language)
    #                         if details_obj:
    #                             logger.debug(f"✅ 电影详细信息获取成功: {details_obj.title}")
    #                     else:
    #                         if season is not None and episode is not None:
    #                             contract_type = 'episode'
    #                             ep = await plugin.get_episode_details(best_match.id, season, episode, language)
    #                             if ep:
    #                                 try:
    #                                     sd = await plugin.get_series_details(best_match.id, language)
    #                                 except Exception:
    #                                     sd = None
    #                                 try:
    #                                     se = await plugin.get_season_details(best_match.id, season, language)
    #                                 except Exception:
    #                                     se = None
    #                                 if sd:
    #                                     ep.series = sd
    #                                 if se:
    #                                     ep.season = se
    #                                 details_obj = ep
    #                                 logger.debug("✅ 单集详细信息获取成功并补充系列/季信息")
    #                         if details_obj is None:
    #                             contract_type = 'series'
    #                             details_obj = await plugin.get_series_details(best_match.id, language)
    #                             if details_obj:
    #                                 logger.debug(f"✅ 只获取到系列详细信息: {details_obj.name}")
    #                 else:
    #                     logger.warning(f"⚠️ 未找到插件或无ID: provider={getattr(best_match, 'provider', None)}")
    #             except Exception as e:
    #                 logger.error(f"❌ 获取详细信息失败: {e}")

    #             # logger.info(f"🎉 元数据丰富完成: 文件ID={media_file.id}, 结果：{asdict(details_obj)}")
    #             # quality = None
    #             # if getattr(out, 'resolution_tags', None):
    #             #     quality = out.resolution_tags[0] if len(out.resolution_tags) > 0 else None
    #             # source = None
    #             # if getattr(out, 'quality_tags', None):
    #             #     qt = [q.lower() for q in out.quality_tags]
    #             #     for s in ['web', 'bluray', 'dvd', 'hdtv']:
    #             #         if any(s in q for q in qt):
    #             #             source = s
    #             #             break

    #             return {
    #                 "user_id": media_file.user_id,
    #                 "file_id": media_file.id,  
    #                 "contract_type": contract_type,
    #                 "contract_payload": asdict(details_obj) if details_obj else asdict(best_match),
    #                 "path_info": path_info,
    #                 "success": True,
    #                 "error_msg": "",

    #                 # "version_context": {
    #                 #     "scope": scope,
    #                 #     "quality": quality,
    #                 #     "source": source
    #                 # },
    #             }
                
    #             # # 入队持久化任务（解耦写库）上一版本的任务队列
    #             # try:
    #             #     from services.task import Task, TaskType, TaskPriority, get_task_queue_service
    #             #     tq = get_task_queue_service()
    #             #     await tq.connect()
    #             #     contract_type = None
    #             #     payload = None
    #             #     if details_obj and hasattr(details_obj, 'movie_id'):
    #             #         contract_type = 'movie'
    #             #         payload = asdict(details_obj)
    #             #         external_key = str(getattr(details_obj, 'movie_id', best_match.id))
    #             #         scope = 'movie_single'
    #             #     elif details_obj and hasattr(details_obj, 'episode_number'):
    #             #         contract_type = 'episode'
    #             #         payload = asdict(details_obj)
    #             #         external_key = str(getattr(details_obj, 'episode_id', f"{best_match.id}:{season}:{episode}"))
    #             #         scope = 'episode_single'
    #             #     elif details_obj and hasattr(details_obj, 'series_id'):
    #             #         contract_type = 'series'
    #             #         payload = asdict(details_obj)
    #             #         external_key = str(getattr(details_obj, 'series_id', best_match.id))
    #             #         scope = 'series_group'
    #             #     else:
    #             #         contract_type = 'series'
    #             #         payload = asdict(best_match)
    #             #         external_key = str(getattr(best_match, 'id', media_file.id))
    #             #         scope = 'series_group'
    #             #     quality = None
    #             #     if getattr(out, 'resolution_tags', None):
    #             #         quality = out.resolution_tags[0] if len(out.resolution_tags) > 0 else None
    #             #     source = None
    #             #     if getattr(out, 'quality_tags', None):
    #             #         qt = [q.lower() for q in out.quality_tags]
    #             #         for s in ['web', 'bluray', 'dvd', 'hdtv']:
    #             #             if any(s in q for q in qt):
    #             #                 source = s
    #             #                 break
    #             #     idempotency_key = f"{media_file.user_id}:{media_file.id}:{best_match.provider}:{contract_type}:{external_key}"
    #             #     persist_task = Task(
    #             #         task_type=TaskType.PERSIST_METADATA,
    #             #         priority=TaskPriority.NORMAL,
    #             #         params={
    #             #             "file_id": media_file.id,
    #             #             "user_id": media_file.user_id,
    #             #             "storage_id": storage_id,
    #             #             "contract_type": contract_type,
    #             #             "contract_payload": payload,
    #             #             "version_context": {
    #             #                 "scope": scope,
    #             #                 "quality": quality,
    #             #                 "source": source
    #             #             },
    #             #             "provider": best_match.provider,
    #             #             "language": language,
    #             #             "idempotency_key": idempotency_key
    #             #         },
    #             #         max_retries=3,
    #             #         retry_delay=300,
    #             #         timeout=3600
    #             #     )
    #             #     ok = await tq.enqueue_task(persist_task)
    #             #     logger.info(f"元数据持久化任务已入队: {persist_task.id}")
    #             #     if not ok:
    #             #         logger.error("持久化任务入队失败")
    #             #         return False
    #             # except Exception as e:
    #             #     logger.error(f"持久化任务入队异常: {e}")
    #             #     return False

    #             # # 异步本地化：入队侧车任务
    #             # try:
    #             #     from services.task import Task, TaskType, TaskPriority, get_task_queue_service
    #             #     from core.config import get_settings
    #             #     settings = get_settings()
    #             #     if not bool(getattr(settings, "SIDE_CAR_LOCALIZATION_ENABLED", True)):
    #             #         logger.info("侧车本地化关闭（env），跳过入队")
    #             #     else:
    #             #         if storage_id is None:
    #             #             logger.error("侧车本地化启用但缺少storage_id，跳过入队")
    #             #         else:
    #             #             tq = get_task_queue_service()
    #             #             await tq.connect()
    #             #             sidecar_task = Task(
    #             #                 task_type=TaskType.SIDECAR_LOCALIZE,
    #             #                 priority=TaskPriority.LOW,
    #             #                 params={
    #             #                     "file_id": media_file.id,
    #             #                     "storage_id": storage_id,
    #             #                     "language": language,
    #             #                     "user_id": media_file.user_id
    #             #                 },
    #             #                 max_retries=3,
    #             #                 retry_delay=300,
    #             #                 timeout=1800
    #             #             )
    #             #             ok2 = await tq.enqueue_task(sidecar_task)
    #             #             if ok2:
    #             #                 logger.info(f"侧车本地化任务已入队: {sidecar_task.id} -> file_id={media_file.id}")
    #             #             else:
    #             #                 logger.error("侧车任务入队失败，跳过本地化")
    #             # except Exception as e:
    #             #     logger.error(f"侧车本地化任务入队异常，跳过本地化: {e}")
                
    #             # return True
                
    #     # 4. 修复：捕获全局异常时，返回包含错误信息的字典（原返回空字典，可优化）
    #     except Exception as e:
    #         logger.exception(f"丰富媒体文件元数据失败: {e}")
    #         return {
    #             "user_id": 0,
    #             "file_id": file_id,
    #             "contract_type": "",
    #             "contract_payload": {},
    #             "path_info": {},
    #             "success": False,
    #             "error_msg": str(e)  # 新增：捕获具体异常信息
    #         } 
           
    # async def enrich_multiple_files(self, file_ids: List[int], 
    #                             language: str = "zh-CN", 
    #                             storage_id: Optional[int] = None,
    #                             max_concurrency: int = 20) -> List[MetadataResult]:
    #     results: List[MetadataResult] = []
    #     semaphore = asyncio.Semaphore(max_concurrency)  # 限制最大并发数
        
    #     async def _bound_enrich(file_id: int):
    #         async with semaphore:
    #             return await self._enrich_single_file_safe(file_id, language, storage_id)
        
    #     tasks = [asyncio.create_task(_bound_enrich(fid)) for fid in file_ids]
    #     completed_results = await asyncio.gather(*tasks)
    #     results.extend(completed_results)
    #     return results
    
    # async def _enrich_single_file_safe(self, file_id: int, language: str, storage_id: Optional[int]) -> MetadataResult:
    #     """
    #     安全地丰富单个文件（修改后返回MetadataResult）
    #     """
    #     try:
    #         return await self.enrich_media_file(file_id, storage_id=storage_id)
    #     except Exception as e:
    #         logger.error(f"丰富文件 {file_id} 异常: {e}")
    #         return {"file_id": file_id, "user_id": 0, "contract_type": "", "contract_payload": {}}
    # endregion   


# 全局元数据丰富器实例
metadata_enricher = MetadataEnricher()



