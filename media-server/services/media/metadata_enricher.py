"""
刮削器元数据服务 - 使用插件化架构
"""
import asyncio
import logging
import os
from collections import Counter
from typing import Dict, List, Optional, Any, TypedDict, AsyncIterator
from sqlmodel import select
from utils.media_parser import MediaParser,media_parser
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
        self.media_parser = MediaParser()

    @staticmethod
    def _title_length_ratio(a: str, b: str) -> float:
        """计算两个标题的长度比率，防止短标题匹配长标题"""
        if not a or not b:
            return 0.0
        return min(len(a), len(b)) / max(len(a), len(b))

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
        def _norm_title(text: str) -> str:
            s = (text or "").strip().lower()
            return "".join(ch for ch in s if ch.isalnum() or "一" <= ch <= "鿿")

        parsed_title = parsed_data["title"].strip()
        parsed_title_norm = _norm_title(parsed_title)
        parsed_country = parsed_data.get("country")  # 解析的地区（可选）
        filtered_results = []

        for result in search_results:
            # 1.1 标题相关性过滤：使用归一化后包含关系，增强中英文及符号兼容性
            result_title_candidates = [t for t in [result.title, result.original_name] if t and t.strip()]
            title_matched = False
            for candidate in result_title_candidates:
                cand_norm = _norm_title(candidate)
                if not cand_norm:
                    continue
                if parsed_title_norm == cand_norm:
                    title_matched = True
                    break
                if parsed_title_norm and (parsed_title_norm in cand_norm or cand_norm in parsed_title_norm):
                    # 长度比率检查：防止 "The" 匹配 "The Office"
                    ratio = self._title_length_ratio(parsed_title_norm, cand_norm)
                    if ratio < 0.4:
                        continue  # 长度差异过大，跳过
                    title_matched = True
                    break
            if not title_matched:
                continue

            # 1.2 地区合理性过滤：解析有country时，结果origin_country必须包含该地区（避免海外版本）
            if parsed_country and parsed_country.strip() not in [c.strip() for c in result.origin_country]:
                continue

            # 符合过滤条件，加入候选列表
            filtered_results.append(result)

        # 若过滤后无结果，保留原搜索结果（避免过度过滤导致无匹配）
        # 仅在过滤后完全没有候选时回退，不再因候选数<=2而回退
        if not filtered_results:
            logger.info(f"过滤后无候选结果，保留原搜索结果（共{len(search_results)}条）")
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

            # 2.1 标题精确匹配（权重35：核心维度，使用归一化后的全等匹配）
            title_exact_match = False
            for candidate in [result.title, result.original_name]:
                if not candidate:
                    continue
                if _norm_title(candidate) == parsed_title_norm and parsed_title_norm:
                    title_exact_match = True
                    break
            if title_exact_match:
                score += 35

            # 2.2 年份匹配（权重20：核心维度，区分同名称不同版本，含±1年容差）
            parsed_year = parsed_data.get("year")
            if parsed_year and result_year:
                year_diff = abs(parsed_year - result_year)
                if year_diff == 0:  # 年份完全一致
                    score += 20
                elif year_diff == 1:  # ±1年容差（多季番剧）
                    score += 10

            # 2.3 地区匹配（权重10：辅助维度，优先本地版本）
            if parsed_country and parsed_country.strip() in [c.strip() for c in result.origin_country]:
                score += 10

            # 2.4 语言匹配（权重10：辅助维度，优先原始语言匹配）
            parsed_lang = parsed_data.get("language")
            if parsed_lang and result_lang:
                # 支持前缀匹配（如zh-CN匹配zh，en-US匹配en）
                parsed_lang_prefix = parsed_lang.split("-")[0].strip()
                result_lang_prefix = result_lang.split("-")[0].strip()
                if parsed_lang_prefix == result_lang_prefix:
                    score += 10

            # 2.5 评分与投票数（权重5：可靠性维度，避免低投票高评分的异常结果）
            # 公式：(评分/10)*2.5 + (min(投票数, 100)/100)*2.5 -> 评分和投票各占2.5分，投票数上限100（避免极端值）
            vote_score = (result_vote_avg / 10) * 2.5 + (min(result_vote_count, 100) / 100) * 2.5
            score += round(vote_score, 1)  # 保留1位小数，避免分数膨胀

            # 2.6 流行度（权重5：热度维度，优先高热度结果）
            # 流行度归一化：取0-5分（流行度上限按50计算，超过50按5分算）
            popularity_score = min(result_popularity / 10, 5)  # 50/10=5，适配TMDB流行度范围
            score += round(popularity_score, 1)

            # 记录结果与分数
            scored_results.append((result, round(score, 1)))
            # logger.info(f"结果打分：title={result.title}, id={result.id}, 总分={round(score,1)}")

        # -------------------------- 步骤3：排序并选择最优结果 --------------------------
        # 排序规则：1.总分降序 -> 2.投票数降序（同分下优先高投票） -> 3.流行度降序（再同分优先高热度）
        scored_results.sort(
            key=lambda x: (-x[1], -x[0].vote_count or 0, -x[0].popularity or 0.0)
        )

        # 最低分阈值：低于30分视为无匹配
        if scored_results and scored_results[0][1] < 30:
            logger.info(f"最优匹配分数过低 ({scored_results[0][1]})，视为无匹配")
            try:
                from services.media.metrics import record_match
                asyncio.create_task(record_match(parsed_data.get("title", ""), scored_results[0][1], False))
            except Exception:
                pass
            return None

        # 取排序后的第一个结果作为最优匹配
        best_match = scored_results[0][0]
        logger.info(
            f"最优匹配结果：title={best_match.title}, id={best_match.id}, "
            f"总分={scored_results[0][1]}, 来源={best_match.provider}"
        )
        try:
            from services.media.metrics import record_match
            asyncio.create_task(record_match(parsed_data.get("title", ""), scored_results[0][1], True))
        except Exception:
            pass
        return best_match

    async def _record_failed_parse(self, file_asset: FileAsset, error_message: str):
        """记录失败的解析到数据库，用于后续人工审核"""
        try:
            import json
            from core.db import AsyncSessionLocal
            from models.media_models import FailedParse
            async with AsyncSessionLocal() as session:
                fp = FailedParse(
                    user_id=file_asset.user_id,
                    file_path=file_asset.full_path,
                    file_asset_id=file_asset.id,
                    guessit_result=json.dumps({"path": file_asset.full_path}, ensure_ascii=False),
                    error_message=error_message[:500],
                    search_attempts=1,
                )
                session.add(fp)
                await session.commit()
        except Exception as e:
            logger.error(f"记录失败解析异常: {e}")

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

    async def _try_alias_search(self, title: str, year: Optional[int],
                                 corrected_type: MediaType, language: str
                                 ) -> tuple[List[ScraperSearchResult], str]:
        """尝试通过别名搜索元数据，返回 (搜索结果, 使用的别名标题)"""
        try:
            from utils.title_alias_service import title_alias_service
            aliases = title_alias_service.get_aliases(title)
            for alias_title in aliases:
                alias_results, _ = await scraper_manager.rollback_search_media(
                    title=alias_title,
                    year=year,
                    media_type=corrected_type,
                    language=language,
                )
                if alias_results:
                    logger.info(f"通过别名 '{alias_title}' 找到结果")
                    return alias_results, alias_title
        except Exception as e:
            logger.error(f"别名搜索失败: {e}")
        return [], title

    async def _try_ai_parse(self, file_path: str, path_info: dict,
                             corrected_type: MediaType, language: str,
                             season: Optional[int] = None
                             ) -> tuple[List[ScraperSearchResult], Optional[str], Optional[int], dict]:
        """尝试通过 AI 解析文件路径，返回 (搜索结果, 标题, 年份, AI解析结果)"""
        try:
            from utils.ai_media_parser import ai_media_parser
            ai_result = await ai_media_parser.parse(file_path, path_info)
            if ai_result and ai_result.get("title"):
                logger.info(f"AI 解析结果: {ai_result}")
                ai_title = ai_result["title"]
                ai_year = ai_result.get("year")
                search_results, _ = await scraper_manager.rollback_search_media(
                    title=ai_title,
                    year=ai_year if season and season < 2 else None,
                    media_type=corrected_type,
                    language=language,
                )
                if search_results:
                    return search_results, ai_title, ai_year, ai_result
        except Exception as e:
            logger.error(f"AI 兜底解析失败: {e}")
        return [], None, None, path_info

    async def enrich_media_file(self, file_asset: FileAsset, language: str = '') -> MetadataResult:
        """
        丰富单个媒体文件元数据（参数改为FileAsset）
        不再查询数据库，直接使用传入的file_asset处理
        """
        logger.debug(f'用户语言{language}')
        try:
            strict_episode = self.media_parser.should_force_episode(file_asset.full_path)
            path_info = await asyncio.to_thread(self.media_parser.parse, file_asset.full_path, strict_episode)
            title = path_info.get("title")
            season = path_info.get("season")
            episode = path_info.get("episode")
            year = path_info.get("year")
            country = path_info.get("country")
            corrected_type = MediaType.MOVIE if path_info.get("type") == "movie" else MediaType.TV_EPISODE

            logger.info(f"搜索参数：title='{title}', 年份={year}, 语言={language}, 类型={corrected_type.value},季={season},集={episode}")
            search_results, corrected_type = await scraper_manager.rollback_search_media(
                title=title,
                year=year if season and season<2 else None,
                media_type=corrected_type,
                language=language,
            )

            if corrected_type == MediaType.TV_EPISODE and (season is None or episode is None):
                path_info = await asyncio.to_thread(
                    self.media_parser.parse,
                    file_asset.full_path,
                    True,
                )
                title = path_info.get("title") or title
                season = path_info.get("season") or season
                episode = path_info.get("episode") or episode
                year = path_info.get("year") or year
                country = path_info.get("country") or country

            if not search_results:
                # 尝试别名搜索
                alias_results, alias_title = await self._try_alias_search(
                    title, year, corrected_type, language
                )
                if alias_results:
                    search_results = alias_results
                    title = alias_title

            if not search_results:
                # AI 兜底解析
                ai_results, ai_title, ai_year, ai_path_info = await self._try_ai_parse(
                    file_asset.full_path, path_info, corrected_type, language, season
                )
                if ai_results:
                    search_results = ai_results
                    title = ai_title
                    year = ai_year
                    path_info = ai_path_info

            if not search_results:
                err_msg = f"未找到元数据: title='{title}' 年份={year}"
                logger.warning(err_msg)
                try:
                    from services.media.metrics import record_enrich
                    asyncio.create_task(record_enrich(False, 0))
                    asyncio.create_task(self._record_failed_parse(file_asset, err_msg))
                except Exception:
                    pass
                return {
                    "user_id": file_asset.user_id,
                    "file_id": file_asset.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": err_msg,
                }

            # -------------------------- 3. 选择最优匹配与获取详情 --------------------------
            parsed_data = {"title": title, "year": year, "language": language, "country": country}
            best_match = self._get_best_match(search_results, parsed_data)
            if not best_match:
                err_msg = f"无最优匹配结果: title='{title}' 年份={year}"
                logger.warning(err_msg)
                try:
                    from services.media.metrics import record_enrich
                    asyncio.create_task(record_enrich(False, 0))
                    asyncio.create_task(self._record_failed_parse(file_asset, err_msg))
                except Exception:
                    pass
                return {
                    "user_id": file_asset.user_id,
                    "file_id": file_asset.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_info,
                    "success": False,
                    "error_msg": err_msg
                }

            logger.info(
                "最佳匹配：title='%s', 年份=%s, ID=%s" % (
                    getattr(best_match, "title", None),
                    getattr(best_match, "year", None),
                    getattr(best_match, "id", None),
                )
            )
            # -------------------------- 4. 处理剧集类型 --------------------------
            if corrected_type == MediaType.TV_EPISODE:
                # 剧集类型：获取系列详情
                series_detail: Optional[ScraperSeriesDetail] = await scraper_manager.get_series_details_cached(
                    best_match=best_match,
                    language=language,
                )
                # logger.info(f"组级系列搜索结果：{series_detail}")
                if series_detail and series_detail.number_of_seasons:
                    season = 1 if season > series_detail.number_of_seasons else season
                    logger.info(f"系列搜索最大季数：{series_detail.number_of_seasons}，使用季数：{season}")
                    # 剧集类型：获取季级详情
                    season_detail: Optional[ScraperSeasonDetail] = await scraper_manager.get_season_details_cached(
                        best_match=best_match,
                        language=language,
                        season=season,
                    )
                    # logger.info(f"季级系列搜索结果：{season_detail}")
                    if season_detail and season_detail.episode_count:
                        episode = 1 if episode > season_detail.episode_count else episode
                        logger.info(f"季级系列搜索最大集数：{season_detail.episode_count}，使用集数：{episode}")


            # 获取元数据详情
            contract_type, details_obj = await scraper_manager.get_detail(
                best_match=best_match,
                media_type=corrected_type,
                language=language,
                season=season,
                episode=episode,
            )
            logger.info(f"获取详情成功: contract_type={contract_type},  季={season}, 集={episode}")

            # -------------------------- 4. 返回结果 --------------------------
            try:
                from services.media.metrics import record_enrich
                asyncio.create_task(record_enrich(True, 0))
            except Exception:
                pass
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
            try:
                from services.media.metrics import record_enrich
                asyncio.create_task(record_enrich(False, 0))
                asyncio.create_task(self._record_failed_parse(file_asset, str(e)))
            except Exception:
                pass
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
            strict_episode = self.media_parser.should_force_episode(fa.full_path)
            tasks.append(asyncio.create_task(asyncio.to_thread(self.media_parser.parse, fa.full_path, strict_episode)))
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
        logger.info(f"剧集文件信息: titles={titles}")

        agg_title = self._most_common_non_empty(titles) or titles[0] if titles else None
        agg_year = self._most_common_non_empty(years)
        agg_country = self._most_common_non_empty(countries)
        agg_season = self._most_common_non_empty(seasons)

        corrected_type = MediaType.TV_EPISODE
        logger.info(f"剧集文件信息: agg_title={agg_title}, agg_year={agg_year}, agg_country={agg_country}, agg_season={agg_season}")

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
            f"组级搜索: title='{agg_title}', 年份={agg_year}, 语言={language}, 类型={corrected_type.value}, 组大小={len(episode_files)}"
        )
        search_results, _ = await scraper_manager.rollback_search_media(
            title=agg_title,
            year=agg_year if agg_season and agg_season<2 else None,
            media_type=corrected_type,
            language=language,
        )

        if not search_results:
            # 尝试别名搜索
            alias_results, alias_title = await self._try_alias_search(
                agg_title, agg_year, corrected_type, language
            )
            if alias_results:
                search_results = alias_results
                agg_title = alias_title

        if not search_results:
            # AI 兜底解析（使用第一个文件的路径作为参考）
            first_path = episode_files[0].full_path if episode_files else ""
            ai_results, ai_title, ai_year, _ = await self._try_ai_parse(
                first_path, {"title": agg_title, "year": agg_year}, corrected_type, language, agg_season
            )
            if ai_results:
                search_results = ai_results
                agg_title = ai_title
                agg_year = ai_year

        if not search_results:
            err_msg = f"未找到元数据: title='{agg_title}' 年份={agg_year}"
            logger.warning(err_msg)
            for fa in episode_files:
                results.append({
                    "user_id": fa.user_id,
                    "file_id": fa.id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": path_infos.get(fa.id, {}),
                    "success": False,
                    "error_msg": err_msg,
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
            err_msg = f"无最优匹配结果: title='{agg_title}' 年份={agg_year}"
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
            f"组级最佳匹配：title='{best_match.title}', 年份={best_match.year}, ID={getattr(best_match, 'id', None)}"
        )

        season_number = agg_season or 1
        logger.info(f"组级搜索季数：{season_number}，解析季数：{agg_season}")
        try:
            series_detail: Optional[ScraperSeriesDetail] = await scraper_manager.get_series_details_cached(
                best_match=best_match,
                language=language,
            )
            # logger.info(f"组级系列搜索结果：{series_detail}")
            if series_detail and series_detail.number_of_seasons:
                season_number = 1 if season_number > series_detail.number_of_seasons else season_number
                logger.info(f"组级系列搜索最大季数：{series_detail.number_of_seasons}，使用季数：{season_number}")

            season_detail: Optional[ScraperSeasonDetail] = await scraper_manager.get_season_details_cached(
                best_match=best_match,
                language=language,
                season=season_number,
            )
            # logger.info(f"组级季搜索结果：{season_detail}")
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
            part = path_info.get("part")
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
                        # episode_item.provider = getattr(season_detail, "provider", None)
                        # logger.info(f"匹配到第 {ep_num} 集: {episode_item}")
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

            payload = episode_detail.model_dump()
            if part is not None:
                payload["part"] = part

            results.append({
                "user_id": fa.user_id,
                "file_id": fa.id,
                "contract_type": "episode",
                "contract_payload": payload,
                "path_info": path_info,
                "success": True,
                "error_msg": "",
            })

        return results

    async def iter_enrich_multiple_files(self, file_ids: List[int], user_id: int, max_concurrency: int = 20) -> AsyncIterator[MetadataResult]:
        """
        流式批量丰富元数据，按分组异步产出单条结果
        """
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
                yield {
                    "user_id": user_id,
                    "file_id": file_id,
                    "contract_type": "",
                    "contract_payload": {},
                    "path_info": {},
                    "success": False,
                    "error_msg": err_msg,
                }

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
        for task in asyncio.as_completed(tasks_group):
            try:
                group_res = await task
            except Exception as e:
                logger.critical(f"未知分组异常: {e}", exc_info=True)
                continue
            for item in group_res:
                yield item

    async def enrich_multiple_files(self, file_ids: List[int], user_id: int, max_concurrency: int = 20) -> List[MetadataResult]:
        """
        兼容旧接口：收集流式结果为列表返回
        """
        results: List[MetadataResult] = []
        async for item in self.iter_enrich_multiple_files(file_ids=file_ids, user_id=user_id, max_concurrency=max_concurrency):
            results.append(item)
        return results

# 全局元数据丰富器实例
metadata_enricher = MetadataEnricher()
