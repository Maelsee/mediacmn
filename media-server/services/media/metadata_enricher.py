"""
刮削器元数据服务 - 使用插件化架构
"""
import asyncio
import logging
import os
from collections import Counter
from typing import Dict, List, Optional, Any, TypedDict
from sqlmodel import select
from guessit import guessit
from core.db import AsyncSessionLocal
from models.media_models import FileAsset
from models.user import User
from services.scraper import scraper_manager, MediaType
from services.storage.storage_service import storage_service
from services.scraper.base import (
    ScraperSearchResult,
    ScraperEpisodeDetail,
    ScraperSeasonDetail,
    ScraperSeriesDetail,
    ScraperEpisodeItem,
)

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


class MetadataEnricher:
    """元数据丰富器 - 使用插件化刮削器"""
    
    def __init__(self):

        """
        初始化元数据丰富器
        
        创建存储服务和文件名解析器实例
        """
        self.storage_service = storage_service
    
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

    def _get_parent_dir_key(self, file_asset: FileAsset) -> str:
        """
        计算父目录分组键，统一路径格式，保证同一季或同一电影多版本归为一组
        """
        try:
            full_path = os.path.abspath(file_asset.full_path)
            parent_dir = os.path.dirname(full_path)
            return parent_dir.replace("\\", "/")
        except Exception:
            return f"default_group_{file_asset.user_id}"

    def _most_common_non_empty(self, values: List[Any]) -> Optional[Any]:
        """
        从列表中选出出现次数最多且非空的值
        """
        filtered = [v for v in values if v not in (None, "", [])]
        if not filtered:
            return None
        counter = Counter(filtered)
        return counter.most_common(1)[0][0]

    async def enrich_media_file(self, file_asset: FileAsset, language: str = '') -> MetadataResult:
        """
        丰富单个媒体文件元数据（参数改为FileAsset）
        不再查询数据库，直接使用传入的file_asset处理
        """
        logger.debug(f'用户语言{language}')
        try:
            path_info = await asyncio.to_thread(guessit, file_asset.full_path)
            title = path_info.get("title")
            season = path_info.get("season")
            episode = path_info.get("episode")
            year = path_info.get("year")
            country = path_info.get("country")  
            corrected_type = MediaType.MOVIE if path_info.get("type") == "movie" else MediaType.TV_EPISODE

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
            contract_type, details_obj = await scraper_manager.get_detail(
                best_match=best_match,
                media_type=corrected_type,
                language=language,
                season=season,
                episode=episode,
            )

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

    async def enrich_media_files(self, file_assets: List[FileAsset], language: str) -> List[MetadataResult]:
        """
        处理同一父目录下的一组文件
        - 多文件共同参与名称解析，提升标题/年份等信息的准确度
        - 电影：一次搜索与详情获取，复用到所有版本
        - 剧集：只获取系列与季详情，单集信息从季详情 episodes 中按集数映射
        """
        results: List[MetadataResult] = []
        if not file_assets:
            return results

        path_infos: Dict[int, Dict[str, Any]] = {}
        tasks: List[asyncio.Task] = []
        for fa in file_assets:
            tasks.append(asyncio.create_task(asyncio.to_thread(guessit, fa.full_path)))
        parsed_list = await asyncio.gather(*tasks, return_exceptions=True)
        for fa, parsed in zip(file_assets, parsed_list):
            if isinstance(parsed, Exception):
                logger.error(f"解析文件名失败: file_id={fa.id}, 错误={parsed}")
                path_infos[fa.id] = {}
            else:
                path_infos[fa.id] = parsed or {}

        movie_files: List[FileAsset] = []
        episode_files: List[FileAsset] = []
        for fa in file_assets:
            info = path_infos.get(fa.id, {})
            media_type = info.get("type")
            ep_num = info.get("episode")
            if media_type == "movie" and ep_num is None:
                movie_files.append(fa)
            else:
                episode_files.append(fa)

        if movie_files:
            movie_tasks: List[asyncio.Task] = []
            for fa in movie_files:
                movie_tasks.append(asyncio.create_task(self.enrich_media_file(fa, language)))
            movie_results = await asyncio.gather(*movie_tasks, return_exceptions=True)
            for fa, res in zip(movie_files, movie_results):
                if isinstance(res, Exception):
                    logger.error(f"处理电影文件失败: file_id={fa.id}, 错误={res}", exc_info=True)
                    results.append({
                        "user_id": fa.user_id,
                        "file_id": fa.id,
                        "contract_type": "",
                        "contract_payload": {},
                        "path_info": path_infos.get(fa.id, {}),
                        "success": False,
                        "error_msg": f"处理电影文件失败: {str(res)}",
                    })
                else:
                    results.append(res)

        if not episode_files:
            return results

        episode_infos = [path_infos.get(fa.id, {}) for fa in episode_files]
        titles = [pi.get("title") for pi in episode_infos]
        years = [pi.get("year") for pi in episode_infos]
        countries = [pi.get("country") for pi in episode_infos]
        seasons = [pi.get("season") for pi in episode_infos]

        agg_title = self._most_common_non_empty(titles) or titles[0] if titles else None
        agg_year = self._most_common_non_empty(years)
        agg_country = self._most_common_non_empty(countries)
        agg_season = self._most_common_non_empty(seasons)

        corrected_type = MediaType.TV_EPISODE

        if not agg_title:
            for fa in episode_files:
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_infos.get(fa.id, {}),
                    "success": False,
                    "error_msg": "无法解析有效标题"
                })
            return results

        logger.info(
            f"📦 组级搜索: title='{agg_title}', 年份={agg_year}, 语言={language}, 类型={corrected_type.value}, 组大小={len(episode_files)}"
        )
        search_results = await scraper_manager.search_media(
            title=agg_title,
            year=agg_year,
            media_type=corrected_type,
            language=language,
        )

        if not search_results:
            err_msg = f"未找到元数据: title='{agg_title}' (年份={agg_year})"
            logger.warning(err_msg)
            for fa in episode_files:
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_infos.get(fa.id, {}),
                    "success": False,
                    "error_msg": err_msg
                })
            return results

        parsed_data = {
            "title": agg_title,
            "year": agg_year,
            "language": language,
            "country": agg_country,
        }
        best_match = self._get_best_match(search_results, parsed_data)
        if not best_match:
            err_msg = f"无最优匹配结果: title='{agg_title}' (年份={agg_year})"
            logger.warning(err_msg)
            for fa in episode_files:
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_infos.get(fa.id, {}),
                    "success": False,
                    "error_msg": err_msg
                })
            return results

        logger.info(
            f"🏆 组级最佳匹配：title='{best_match.title}', 年份={best_match.year}, ID={getattr(best_match, 'id', None)}"
        )

        season_number = agg_season or 1
        try:
            series_detail: Optional[ScraperSeriesDetail] = await scraper_manager.get_series_details_cached(
                best_match=best_match,
                language=language,
            )
            season_detail: Optional[ScraperSeasonDetail] = await scraper_manager.get_season_details_cached(
                best_match=best_match,
                language=language,
                season=season_number,
            )
        except Exception as e:
            logger.error(f"获取系列/季详情失败: {e}", exc_info=True)
            series_detail = None
            season_detail = None

        if not season_detail or not season_detail.episodes:
            logger.warning("季详情缺失或无 episodes，回退为逐集详情模式")
            for fa in episode_files:
                path_info = path_infos.get(fa.id, {})
                ep_num = path_info.get("episode")
                if ep_num is None:
                    results.append({
                        "user_id": fa.user_id,
                        "file_id": fa.id,
                        "contract_type": "",
                        "contract_payload": {},
                        "path_info": path_info,
                        "success": False,
                        "error_msg": "剧集文件缺少 episode 编号，无法匹配单集",
                    })
                    continue
                try:
                    contract_type, details_obj = await scraper_manager.get_detail(
                        best_match=best_match,
                        media_type=MediaType.TV_EPISODE,
                        language=language,
                        season=season_number,
                        episode=int(ep_num),
                    )
                    results.append({
                        "user_id": fa.user_id,
                        "file_id": fa.id,
                        "contract_type": contract_type,
                        "contract_payload": details_obj.model_dump() if details_obj else {},
                        "path_info": path_info,
                        "success": bool(details_obj),
                        "error_msg": "" if details_obj else "未获取到单集详情",
                    })
                except Exception as e:
                    logger.error(f"获取单集详情失败: file_id={fa.id}, 错误={e}", exc_info=True)
                    results.append({
                        "user_id": fa.user_id,
                        "file_id": fa.id,
                        "contract_type": "",
                        "contract_payload": {},
                        "path_info": path_info,
                        "success": False,
                        "error_msg": f"获取单集详情失败: {str(e)}",
                    })
            return results

        for fa in episode_files:
            path_info = path_infos.get(fa.id, {})
            ep_num = path_info.get("episode")
            if ep_num is None:
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": "剧集文件缺少 episode 编号，无法匹配单集",
                })
                continue

            episode_item: Optional[ScraperEpisodeItem] = None
            try:
                for item in season_detail.episodes:
                    if item.episode_number == int(ep_num):
                        episode_item = item
                        break
            except Exception as e:
                logger.error(f"遍历季 episodes 失败: {e}", exc_info=True)

            if not episode_item:
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": f"在季详情中未找到第 {ep_num} 集",
                })
                continue

            try:
                episode_detail = ScraperEpisodeDetail(
                    episode_id=episode_item.episode_id,
                    episode_number=episode_item.episode_number,
                    season_number=episode_item.season_number,
                    name=episode_item.name,
                    overview=episode_item.overview,
                    air_date=episode_item.air_date,
                    runtime=episode_item.runtime,
                    still_path=episode_item.still_path,
                    vote_average=episode_item.vote_average,
                    vote_count=episode_item.vote_count,
                    provider=getattr(season_detail, "provider", None),
                    provider_url=getattr(season_detail, "provider_url", None),
                    artworks=getattr(season_detail, "artworks", []),
                    credits=getattr(season_detail, "credits", []),
                    external_ids=getattr(season_detail, "external_ids", []),
                    raw_data=season_detail.raw_data,
                    series=series_detail,
                    season=season_detail,
                    episode_type=None,
                )
            except Exception as e:
                logger.error(f"构造单集详情对象失败: file_id={fa.id}, 错误={e}", exc_info=True)
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": f"构造单集详情失败: {str(e)}",
                })
                continue

            results.append({
                "user_id": fa.user_id,
                "file_id": fa.id,
                "contract_type": "episode",
                "contract_payload": episode_detail.model_dump(),
                "path_info": path_info,
                "success": True,
                "error_msg": "",
            })

        return results

    async def enrich_multiple_files(self, file_ids: List[int], user_id: int, max_concurrency: int = 20) -> List[MetadataResult]:
        """
        批量丰富元数据
        - 一次性查出所有 FileAsset 与用户语言
        - 按父目录路径分组，一组通常为一季的所有集或一个电影的多版本
        - 每组调用 enrich_media_files，充分利用组内信息提升解析准确率
        """
        results: List[MetadataResult] = []
        semaphore = asyncio.Semaphore(max_concurrency)

        async with AsyncSessionLocal() as session:
            stmt = select(FileAsset).where(FileAsset.id.in_(file_ids))
            result = await session.exec(stmt)
            file_assets = result.all()

            user_stmt = select(User).where(User.id == user_id)
            user_result = await session.exec(user_stmt)
            user_obj = user_result.first()
            language = getattr(user_obj, "language", "zh-CN") if user_obj else "zh-CN"

        file_asset_map: Dict[int, FileAsset] = {fa.id: fa for fa in file_assets}

        for file_id in file_ids:
            if file_id not in file_asset_map:
                err_msg = f"文件不存在: file_id={file_id}"
                logger.error(err_msg)
                results.append({
                    "user_id": user_id,
                    "file_id": file_id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": {},
                    "success": False,
                    "error_msg": err_msg,
                })

        grouped: Dict[str, List[FileAsset]] = {}
        for fa in file_assets:
            key = self._get_parent_dir_key(fa)
            grouped.setdefault(key, []).append(fa)

        async def _process_group(group_files: List[FileAsset]) -> List[MetadataResult]:
            async with semaphore:
                try:
                    if len(group_files) == 1:
                        fa = group_files[0]
                        res = await self.enrich_media_file(fa, language)
                        return [res]
                    return await self.enrich_media_files(group_files, language)
                except Exception as e:
                    logger.error(f"处理分组失败: 错误={e}", exc_info=True)
                    group_results: List[MetadataResult] = []
                    for fa in group_files:
                        group_results.append({
                            "user_id": fa.user_id,
                            "file_id": fa.id,
                            "contract_type": "",
                            "contract_payload": {},
                            "path_info": {},
                            "success": False,
                            "error_msg": f"分组处理失败: {str(e)}",
                        })
                    return group_results

        tasks_group = [asyncio.create_task(_process_group(group_files)) for group_files in grouped.values()]
        group_results_list = await asyncio.gather(*tasks_group, return_exceptions=True)

        for group_res in group_results_list:
            if isinstance(group_res, Exception):
                logger.critical(f"未知分组异常: {group_res}", exc_info=True)
                continue
            results.extend(group_res)

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
