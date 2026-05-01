
"""
弹幕业务服务

本模块提供弹幕相关的核心业务逻辑，包括：
- 自动匹配
- 手动搜索
- 番剧详情获取
- 弹幕获取
- 弹幕合并
- 绑定管理
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib

import logging
logger = logging.getLogger(__name__)

from core.db import get_async_session_context
# from core.security import get_user_id

from core.config import get_settings
from services.danmu.danmu_api_provider import (
    DanmuApiProvider,
    DanmuApiError,
    DanmuApiTimeoutError,
    DanmuApiUpstreamError,
    danmu_api_provider,
)
from services.danmu.danmu_cache_service import danmu_cache_service
from services.danmu.danmu_binding_service import danmu_binding_service
from models.media_models import MediaCore
from models.media_models import SeriesExt, SeasonExt, EpisodeExt
from models.media_models import FileAsset

class DanmuServiceError(Exception):
    """弹幕服务异常"""
    pass


class DanmuMatchResult:
    """匹配结果"""

    def __init__(
        self,
        is_matched: bool,
        confidence: float,
        sources: List[Dict[str, Any]],
        best_match: Optional[Dict[str, Any]] = None,
    ):
        self.is_matched = is_matched
        self.confidence = confidence
        self.sources = sources
        self.best_match = best_match

    def to_dict(self) -> Dict[str, Any]:
        return {
            "isMatched": self.is_matched,
            "confidence": self.confidence,
            "sources": self.sources,
            "bestMatch": self.best_match,
        }


class DanmuService:
    """
    弹幕业务服务

    提供弹幕相关的核心业务逻辑，整合 DanmuApiProvider、缓存服务和绑定服务。

    手动匹配完整流程：
    ┌──────────────────────────────────────────────────────────────────┐
    │  Step 1: search(keyword)                                        │
    │    → 返回 animeId 列表                                           │
    │                                                                  │
    │  Step 2: get_bangumi_detail(animeId)                            │
    │    → 返回 seasons + episodes 列表                                │
    │    → 前端展示剧集列表供用户选择                                    │
    │                                                                  │
    │  Step 3: create_binding(fileId, episodeId, ...)                 │
    │    → 绑定文件与弹幕源                                            │
    │                                                                  │
    │  Step 4: get_danmu(episodeId)                                   │
    │    → 获取弹幕数据                                                │
    └──────────────────────────────────────────────────────────────────┘
    """

    # 匹配置信度阈值
    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self) -> None:
        """初始化弹幕服务"""
        settings = get_settings()
        self._confidence_threshold = getattr(
            settings, "DANMU_CONFIDENCE_THRESHOLD", self.CONFIDENCE_THRESHOLD
        )
        logger.info(f"DanmuService initialized (confidence_threshold={self._confidence_threshold})")

    # ==================== 自动匹配 ====================

    async def auto_match(
        self,
        title: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        file_id: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        自动匹配弹幕源

        优先检查已有绑定，然后调用 danmu_api 的 match 接口。

        Args:
            title: 视频标题
            season: 季数
            episode: 集数
            file_id: 文件 ID
            file_name: 文件名

        Returns:
            匹配结果字典，包含 is_matched、confidence、sources、 best_match、binding、danmu_data(get_danmu返回的弹幕数据)
        """
        logger.info(f"Auto matching danmu for: {title} S{season or '?'}E{episode or '?'}")

        # 1. 检查已有绑定
        # if file_id:
        #     binding = await danmu_binding_service.get_binding(file_id)
        #     if binding:
        #         logger.info(f"Found existing binding for file: {file_id}")
        #         return {
        #             "is_matched": True,
        #             "confidence": 1.0,
        #             "sources": [{
        #                 "episodeId": binding.get("episode_id"),
        #                 "animeId": binding.get("anime_id"),
        #                 "animeTitle": binding.get("anime_title"),
        #                 "episodeTitle": binding.get("episode_title"),
        #                 "type": binding.get("type", ""),
        #                 "typeDescription": binding.get("typeDescription", ""),
        #                 "shift": binding.get("offset", 0),
        #                 "imageUrl": binding.get("imageUrl", ""),
        #             }],
        #             "best_match": {
        #                 "episodeId": binding.get("episode_id"),
        #                 "animeId": binding.get("anime_id"),
        #                 "animeTitle": binding.get("anime_title"),
        #                 "episodeTitle": binding.get("episode_title"),
        #                 "type": binding.get("type", ""),
        #                 "typeDescription": binding.get("typeDescription", ""),
        #                 "shift": binding.get("offset", 0),
        #                 "imageUrl": binding.get("imageUrl", ""),
        #             },
        #         }

        # 2. 构造匹配用的文件名
        match_name = title or ""
        if season is not None:
            match_name += f" S{season:02d}"
        if episode is not None:
            match_name += f"E{episode:02d}"
        # match_name += ".mp4"
        logger.info(f"file_name:{match_name}")

        # 3. 检查缓存
        # cache_key = hashlib.md5(match_name.encode()).hexdigest()
        # cached = await danmu_cache_service.get_match_result(cache_key)
        # if cached:
        #     logger.info(f"Found cached match result for: {match_name}")
        #     return cached

        # 4. 调用 danmu_api match 接口
        try:
            result = await danmu_api_provider.match(
                title=title,
                file_name=match_name,
            )

            is_matched = result.get("isMatched", False)
            raw_matches = result.get("matches", [])
            sources = []
            for m in raw_matches:
                sources.append({
                    "episodeId": m.get("episodeId"),
                    "animeId": m.get("animeId"),
                    "animeTitle": m.get("animeTitle"),
                    "episodeTitle": m.get("episodeTitle"),
                    "type": m.get("type", ""),
                    "typeDescription": m.get("typeDescription", ""),
                    "shift": m.get("shift", 0),
                    "imageUrl": m.get("imageUrl", ""),
                })

            best_match = sources[0] if sources else None
            confidence = 1.0 if is_matched else (0.8 if sources else 0.0)

            match_result = {
                "is_matched": is_matched,
                "confidence": confidence,
                "sources": sources,
                "best_match": best_match,
            }

            # 缓存结果
            # await danmu_cache_service.set_match_result(cache_key, match_result)

            # 高置信度 + 有 file_id → 自动绑定 + 获取弹幕（一步到位）
            if is_matched and confidence >= self._confidence_threshold and file_id and best_match:
                episode_id = str(best_match.get("episodeId", ""))
                if episode_id:
                    try:
                        binding = await danmu_binding_service.create_binding(
                            file_id=file_id,
                            episode_id=episode_id,
                            anime_id=str(best_match.get("animeId", "")),
                            anime_title=best_match.get("animeTitle", ""),
                            episode_title=best_match.get("episodeTitle", ""),
                            type=best_match.get("type", ""),
                            typeDescription=best_match.get("typeDescription", ""),
                            imageUrl=best_match.get("imageUrl", ""),
                            # platform=best_match.get("platform", ""),
                            is_manual=False,
                            match_confidence=confidence,
                            # source_info=best_match,  # 保存完整匹配信息（type/imageUrl/shift等）
                        )
                        logger.info(f"Auto match: bounding={binding}")
                        match_result["binding"] = binding

                        # 直接获取弹幕数据
                        danmu_data = await self.get_danmu(
                            episode_id=episode_id,
                            file_id=file_id,
                            load_mode="segment",
                        )
                        match_result["danmu_data"] = danmu_data
                        logger.info(
                            f"Auto match: auto-bound file={file_id} -> episode={episode_id}, "
                            f"danmu loaded ({danmu_data.get('count', 0)} comments)"
                        )
                    except Exception as e:
                        logger.warning(f"Auto match: auto-bind failed, returning match only: {e}")

            return match_result
            """
            match_result结构：

            
            """

        except DanmuApiError as e:
            logger.error(f"Auto match error: {e}")
            return {
                "is_matched": False,
                "confidence": 0.0,
                "sources": [],
                "best_match": None,
            }

    # ==================== 获取文件信息 ====================
    async def get_file_info(
        self,
        file_id: str,
        # current_subject: str,
        user_id: int
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """
        根据file_id获取文件对应的媒体信息（标题、季数、集数）

        表关系：
          电视剧：
            FileAsset(core_id) → MediaCore(episode)
              → EpisodeExt(series_core_id, season_number, episode_number)
                → MediaCore(series, title)
          电影：
            FileAsset(core_id) → MediaCore(movie, title)

        Args:
            file_id: 文件资源 ID（file_asset.id 的字符串形式）
            current_subject: 当前用户

        Returns:
            (标题, 季数, 集数) — 找不到时对应字段为 None
            - movie: (movie_title, None, None)
            - episode: (series_title, season_number, episode_number)
        """
        logger.info(f"Get file info request: {file_id}, user_id={user_id}")
        try:
            # user_id = get_user_id(current_subject)
            file_asset_id = int(file_id)

            async with get_async_session_context() as session:
                from sqlmodel import select

                # 1. FileAsset(id=file_id, user_id) → core_id
                file_stmt = select(FileAsset).where(
                    FileAsset.id == file_asset_id,
                    FileAsset.user_id == user_id,
                )
                file_asset = (await session.exec(file_stmt)).first()
                if not file_asset or not file_asset.core_id:
                    return None, None, None

                # 2. MediaCore(core_id, user_id) → 根据 kind 区分 movie / episode
                core_stmt = select(MediaCore).where(
                    MediaCore.id == file_asset.core_id,
                    MediaCore.user_id == user_id,
                )
                media_core = (await session.exec(core_stmt)).first()
                if not media_core:
                    return None, None, None

                # 电影：只有标题，没有季集信息
                if media_core.kind == "movie":
                    return media_core.title, None, None

                # 剧集：继续走 EpisodeExt → Series 标题链路
                if media_core.kind != "episode":
                    # 非 movie / episode 的类型做兜底，至少返回标题
                    return media_core.title, None, None

                # 3. EpisodeExt(core_id, user_id) → series_core_id, season_number, episode_number
                ep_stmt = select(EpisodeExt).where(
                    EpisodeExt.core_id == media_core.id,
                    EpisodeExt.user_id == user_id,
                )
                episode_ext = (await session.exec(ep_stmt)).first()
                if not episode_ext:
                    return media_core.title, None, None

                # 4. MediaCore(series_core_id, user_id) → 系列标题
                series_stmt = select(MediaCore).where(
                    MediaCore.id == episode_ext.series_core_id,
                    MediaCore.user_id == user_id,
                )
                series_core = (await session.exec(series_stmt)).first()
                series_title = series_core.title if series_core else None

                return series_title, episode_ext.season_number, episode_ext.episode_number
        except (ValueError, TypeError) as e:
            logger.error(f"Get file info invalid args: file_id={file_id}, subject={current_subject}, error={e}")
            return None, None, None
        except Exception as e:
            logger.error(f"Get file info error: {e}")
            return None, None, None
            

    # ==================== 手动搜索 ====================

    async def search(
        self,
        keyword: str,
        search_type: str = "anime",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        手动搜索弹幕源

        前端手动匹配 Step 1：用户输入关键词搜索番剧。
        返回的每一项包含 animeId，前端用 animeId 调用 get_bangumi_detail 获取集数。

        Args:
            keyword: 搜索关键词
            search_type: 搜索类型 (anime/episodes)
            limit: 返回结果数量限制

        Returns:
            搜索结果
        """
        logger.info(f"Searching danmu with keyword: {keyword}, type: {search_type}")

        # 检查缓存
        cached = await danmu_cache_service.get_search_result(keyword)
        if cached:
            logger.info(f"Found cached search result for: {keyword}")
            return cached

        try:
            if search_type == "anime":
                result = await danmu_api_provider.search_anime(keyword, limit)
                items = result.get("animes", [])
            else:
                result = await danmu_api_provider.search_episodes(keyword, limit=limit)
                items = result.get("episodes", [])

            search_result = {
                "keyword": keyword,
                "type": search_type,
                "items": items,
                "hasMore": result.get("hasMore", False),
            }

            # 缓存结果
            await danmu_cache_service.set_search_result(keyword, search_result)

            return search_result

        except DanmuApiError as e:
            logger.error(f"Search error: {e}")
            return {
                "keyword": keyword,
                "type": search_type,
                "items": [],
                "hasMore": False,
                "error": str(e),
            }

    # ==================== 番剧详情 ====================

    async def get_bangumi_detail(
        self,
        anime_id: str,
    ) -> Dict[str, Any]:
        """
        获取番剧详情（含所有季和剧集列表）

        前端手动匹配 Step 2：用户选择搜索结果中的某个番剧后，
        用 animeId 调用此方法获取该番剧的所有季和剧集列表。

        danmu_api 接口: GET /api/v2/bangumi/{animeId}
        返回格式:
        {
            "bangumi": {
                "animeId": 333038,
                "animeTitle": "哈哈哈哈哈第五季",
                "type": "综艺",
                "seasons": [
                    { "id": "season-333038", "name": "Season 1", "episodeCount": 38 }
                ],
                "episodes": [
                    {
                        "seasonId": "season-333038",
                        "episodeId": 10036,
                        "episodeTitle": "先导片...",
                        "episodeNumber": "1"
                    }
                ]
            }
        }

        Args:
            anime_id: 番剧 ID (animeId)

        Returns:
            番剧详情，包含 seasons 和 episodes
        """
        logger.info(f"Getting bangumi detail for animeId: {anime_id}")

        # 检查缓存
        # cached = await danmu_cache_service.get_bangumi_detail(anime_id)
        # if cached:
        #     logger.info(f"Found cached bangumi detail for: {anime_id}")
        #     return cached

        try:
            result = await danmu_api_provider.get_bangumi_detail(anime_id)

            detail = {
                "animeId": result.get("animeId", anime_id),
                "animeTitle": result.get("animeTitle", ""),
                "type": result.get("type", ""),
                "typeDescription": result.get("typeDescription", ""),
                "imageUrl": result.get("imageUrl", ""),
                "episodeCount": result.get("episodeCount", 0),
                "seasons": result.get("seasons", []),
                "episodes": result.get("episodes", []),
            }

            # 缓存结果
            # await danmu_cache_service.set_bangumi_detail(anime_id, detail)

            return detail

        except DanmuApiError as e:
            logger.error(f"Get bangumi detail error: {e}")
            raise

    # ==================== 弹幕获取 ====================

    async def get_danmu(
        self,
        episode_id: str,
        file_id: Optional[str] = None,
        load_mode: str = "segment",
        next_segment: Optional[Dict[str, Any]] = None,
        anime_id: Optional[str] = None,
        anime_title: Optional[str] = None,
        episode_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取弹幕数据

        如果传入 file_id，会自动查询或创建绑定关系（一步到位）。
        首次获取弹幕时无需单独调用 bind 接口。

        Args:
            episode_id: 剧集 ID
            file_id: 文件 ID（用于获取偏移量，同时自动创建绑定）
            load_mode: 加载模式（full/segment）
            next_segment: 下一个分片信息（load_mode=segment 时可选）
            anime_id: 番剧 ID（首次绑定时使用）
            anime_title: 番剧标题（首次绑定时使用）
            episode_title: 剧集标题（首次绑定时使用）

        Returns:
            弹幕数据
        """
        logger.info(f"Getting danmu for episode: {episode_id}")

        # 获取偏移量，无绑定时自动创建
        offset = 0.0
        created_binding = None
        if file_id:
            binding = await danmu_binding_service.get_binding(file_id)
            if binding:
                offset = binding.get("offset", 0.0)
            else:
                # 自动创建绑定（无需前端单独调用 bind 接口）
                try:
                    created_binding = await danmu_binding_service.create_binding(
                        file_id=file_id,
                        episode_id=episode_id,
                        anime_id=anime_id,
                        anime_title=anime_title,
                        episode_title=episode_title,
                        is_manual=anime_id is not None,  # 有元数据说明是手动选择的
                    )
                    logger.info(f"Auto-created binding: file={file_id} -> episode={episode_id}")
                except Exception as e:
                    logger.warning(f"Auto-create binding failed: {e}")


        normalized_mode = load_mode if load_mode in {"full", "segment"} else "full"

        try:
            # 第一次请求弹幕数据
            # segment 模式：返回所有分片描述 + 第一分片弹幕
            # full 模式：返回全部弹幕
            result = await danmu_api_provider.get_danmu(
                episode_id=episode_id,
                load_mode=normalized_mode,
                duration=True,
                format="json",
            )

            danmu_data = await self._build_danmu_payload(
                source_result=result,
                episode_id=episode_id,
                offset=offset,
                load_mode=normalized_mode,
                is_next_segment=bool(next_segment),
            )

            # 首次自动创建的绑定信息附加到返回数据中
            if created_binding:
                danmu_data["binding"] = created_binding

            # 缓存结果
            await danmu_cache_service.set_binding(file_id, danmu_data)

            return danmu_data

        except DanmuApiError as e:
            logger.error(f"Get danmu error: {e}")
            return {
                "episode_id": int(episode_id),
                "count": 0,
                "comments": [],
                "error": str(e),
                "load_mode": normalized_mode,
            }

    async def get_next_segment(
        self,
        next_segment: Dict[str, Any],
        format: str = "json",
    ) -> Dict[str, Any]:
        """获取下一个分片弹幕"""
        return await danmu_api_provider.get_segment_comment(next_segment, format=format)

    async def _build_danmu_payload(
        self,
        source_result: Dict[str, Any],
        episode_id: str,
        offset: float,
        load_mode: str,
        is_next_segment: bool = False,
    ) -> Dict[str, Any]:
        """
        构建弹幕响应数据

        将 danmu_api 返回的原始数据转换为前端需要的格式。
        """
        if is_next_segment:
            # 下一分片数据
            comments = source_result.get("comments", [])
            # parsed = self._parse_comments(comments)
            parsed = comments
            return {
                "episode_id": int(episode_id),
                "count": len(parsed),
                "comments": parsed,
                "offset": offset,
                "load_mode": load_mode,
            }

        # 首次请求数据
        video_duration = int(source_result.get("videoDuration", 0) or 0)
        comments = source_result.get("comments", [])
        segment_list = source_result.get("segmentList", [])

        if load_mode == "segment" and isinstance(comments, dict):
            # segment 模式：comments 是一个 dict，key 是分片索引
            # 取第一个分片的弹幕
            first_segment_comments = []
            for key in sorted(comments.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                first_segment_comments = comments[key]
                break
            # parsed = self._parse_comments(first_segment_comments)
            parsed = first_segment_comments
        else:
            # full 模式：comments 是列表
            # parsed = self._parse_comments(comments)
            parsed = comments

        # 应用偏移量
        # if offset != 0:
            # parsed = self._apply_offset(parsed, offset)

        return {
            "episode_id": int(episode_id),
            "count": source_result.get("count", len(parsed)),
            "comments": parsed,
            "offset": offset,
            "video_duration": video_duration,
            "load_mode": load_mode,
            "segment_list": segment_list,
        }

    # def _parse_comments(self, raw_comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    #     """
    #     解析弹幕数据

    #     danmu_api 返回的弹幕格式:
    #     { "p": "12.5,1,25,16777215,0,0,xxxx", "m": "弹幕内容" }
    #     或
    #     { "time": 12.5, "type": 1, "color": "#FFFFFF", "content": "弹幕内容" }

    #     转换为前端统一格式:
    #     { "id": "xxx", "time": 12500, "content": "弹幕内容", "color": "#FFFFFF", "type": "scroll" }
    #     """
    #     parsed = []
    #     for i, c in enumerate(raw_comments):
    #         if not isinstance(c, dict):
    #             continue

    #         # 格式1: p 字段格式 (弹弹play 标准格式)
    #         p_str = c.get("p", "")
    #         if p_str and isinstance(p_str, str):
    #             parts = p_str.split(",")
    #             if len(parts) >= 4:
    #                 time_ms = int(float(parts[0]) * 1000)
    #                 danmu_type_int = int(parts[1])
    #                 color_int = int(parts[3])

    #                 # 类型映射: 1=滚动, 4=底部, 5=顶部
    #                 type_map = {1: "scroll", 4: "bottom", 5: "top"}
    #                 danmu_type = type_map.get(danmu_type_int, "scroll")

    #                 # 颜色转换
    #                 color = f"#{color_int:06X}"

    #                 parsed.append({
    #                     "id": c.get("cid", f"{i}"),
    #                     "time": time_ms,
    #                     "content": c.get("m", ""),
    #                     "color": color,
    #                     "type": danmu_type,
    #                 })
    #                 continue

    #         # 格式2: 直接字段格式
    #         time_val = c.get("time", 0)
    #         if isinstance(time_val, (int, float)):
    #             time_ms = int(time_val * 1000) if time_val < 100000 else int(time_val)
    #         else:
    #             time_ms = 0

    #         type_val = c.get("type", 1)
    #         if isinstance(type_val, int):
    #             type_map = {1: "scroll", 4: "bottom", 5: "top"}
    #             danmu_type = type_map.get(type_val, "scroll")
    #         else:
    #             danmu_type = str(type_val) if type_val else "scroll"

    #         parsed.append({
    #             "id": c.get("id", c.get("cid", f"{i}")),
    #             "time": time_ms,
    #             "content": c.get("content", c.get("m", c.get("text", ""))),
    #             "color": c.get("color", "#FFFFFF"),
    #             "type": danmu_type,
    #         })

    #     return parsed

    # def _apply_offset(self, comments: List[Dict[str, Any]], offset: float) -> List[Dict[str, Any]]:
    #     """应用时间偏移量"""
    #     if not offset:
    #         return comments
    #     offset_ms = int(offset * 1000)
    #     for c in comments:
    #         c["time"] = max(0, c.get("time", 0) + offset_ms)
    #     return comments

    # ==================== 弹幕合并 ====================

    async def merge_danmu(
        self,
        episode_ids: List[str],
        from_time: Optional[int] = None,
        to_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        合并多个弹幕源的弹幕

        Args:
            episode_ids: 剧集 ID 列表
            from_time: 开始时间(秒)
            to_time: 结束时间(秒)

        Returns:
            合并后的弹幕数据
        """
        logger.info(f"Merging danmu from {len(episode_ids)} sources")

        all_comments = []
        sources = []

        for eid in episode_ids:
            try:
                result = await danmu_api_provider.get_danmu(
                    episode_id=eid,
                    load_mode="full",
                    duration=False,
                    format="json",
                )
                comments = result.get("comments", [])
                # parsed = self._parse_comments(comments)
                parsed = comments

                # 时间过滤
                if from_time is not None or to_time is not None:
                    from_ms = (from_time or 0) * 1000
                    to_ms = (to_time or 999999) * 1000
                    parsed = [c for c in parsed if from_ms <= c.get("time", 0) <= to_ms]

                all_comments.extend(parsed)
                sources.append({
                    "episodeId": eid,
                    "count": len(parsed),
                })

            except DanmuApiError as e:
                logger.warning(f"Failed to get danmu for episode {eid}: {e}")
                sources.append({
                    "episodeId": eid,
                    "count": 0,
                    "error": str(e),
                })

        # 按时间排序
        all_comments.sort(key=lambda x: x.get("time", 0))

        return {
            "count": len(all_comments),
            "comments": all_comments,
            "sources": sources,
        }

    # ==================== 绑定管理 ====================

    async def get_binding(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文件的弹幕绑定

        Args:
            file_id: 文件 ID

        Returns:
            绑定信息，如果不存在返回 None
        """
        return await danmu_binding_service.get_binding(file_id)

    async def create_binding(
        self,
        file_id: str,
        episode_id: str,
        anime_id: Optional[str] = None,
        anime_title: Optional[str] = None,
        episode_title: Optional[str] = None,
        platform: Optional[str] = None,
        offset: float = 0.0,
    ) -> Dict[str, Any]:
        """
        创建绑定

        Args:
            file_id: 文件 ID
            episode_id: 剧集 ID
            anime_id: 番剧 ID
            anime_title: 番剧标题
            episode_title: 剧集标题
            platform: 弹幕平台
            offset: 时间偏移量

        Returns:
            绑定信息
        """
        return await danmu_binding_service.create_binding(
            file_id=file_id,
            episode_id=episode_id,
            anime_id=anime_id,
            anime_title=anime_title,
            episode_title=episode_title,
            platform=platform,
            offset=offset,
            is_manual=True,
        )

    async def unbind(self, file_id: str) -> bool:
        """
        解除绑定

        Args:
            file_id: 文件 ID

        Returns:
            是否成功
        """
        return await danmu_binding_service.delete_binding(file_id)

    async def update_offset(
        self,
        file_id: str,
        offset: float,
    ) -> Optional[Dict[str, Any]]:
        """
        更新偏移量

        Args:
            file_id: 文件 ID
            offset: 新的偏移量

        Returns:
            更新后的绑定信息
        """
        return await danmu_binding_service.update_offset(file_id, offset)
        

    # ==================== 平台管理 ====================

    # async def get_platforms(self) -> List[Dict[str, Any]]:
    #     """获取支持的平台列表"""
    #     return await danmu_api_provider.get_platforms()

    # async def check_platform_status(self, platform: str) -> Dict[str, Any]:
    #     """检查平台状态"""
    #     return await danmu_api_provider.check_platform_status(platform)


# 全局单例
danmu_service = DanmuService()
