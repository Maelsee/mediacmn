"""
弹幕业务服务

本模块提供弹幕相关的核心业务逻辑，包括：
- 自动匹配
- 手动搜索
- 弹幕获取
- 弹幕合并
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import hashlib

import logging
logger = logging.getLogger(__name__)


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
    """
    
    # 匹配置信度阈值
    CONFIDENCE_THRESHOLD = 0.7
    
    def __init__(self) -> None:
        """初始化弹幕服务"""
        settings = get_settings()
        self._confidence_threshold = getattr(settings, "DANMU_CONFIDENCE_THRESHOLD", 0.5)
        logger.info(f"DanmuService initialized with confidence threshold: {self._confidence_threshold}")
    
    # ==================== 自动匹配 ====================
    
    async def auto_match(
        self,
        title: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        file_id: Optional[str] = None,
        # file_name: Optional[str] = None,
    ) -> DanmuMatchResult:
        """
        自动匹配弹幕源
        
        根据视频标题、季数、集数等信息自动匹配弹幕源。
        
        Args:
            title: 视频标题
            season: 季数
            episode: 集数
            file_id: 文件 ID（用于检查绑定）
            file_name: 文件名
            
        Returns:
            匹配结果
        """
        file_name = f"{title} S{season}E{episode}" if season is not None and episode is not None else title
        logger.info(f"Auto matching danmu for: {title}, season={season}, episode={episode}, file_name = {file_name}")
        # # 1. 如果有 file_id，先检查是否有绑定
        # if file_id:
        #     binding = await danmu_binding_service.get_binding(file_id)
        #     if binding:
        #         logger.info(f"Found existing binding for file: {file_id}")
        #         return DanmuMatchResult(
        #             is_matched=True,
        #             confidence=1.0,
        #             sources=[{
        #                 "episodeId": binding["episodeId"],
        #                 "animeTitle": binding["animeTitle"],
        #                 "episodeTitle": binding["episodeTitle"],
        #                 "platform": binding["platform"],
        #                 "offset": binding["offset"],
        #                 "isBound": True,
        #             }],
        #             best_match={
        #                 "episodeId": binding["episodeId"],
        #                 "animeTitle": binding["animeTitle"],
        #                 "episodeTitle": binding["episodeTitle"],
        #                 "platform": binding["platform"],
        #                 "offset": binding["offset"],
        #             },
        #         )
        
        # # 2. 检查缓存
        # if file_id:
        #     cached_result = await danmu_cache_service.get_match_result(file_id)
        #     if cached_result:
        #         logger.info(f"Found cached match result for file: {file_id}")
        #         return DanmuMatchResult(
        #             is_matched=cached_result.get("isMatched", False),
        #             confidence=cached_result.get("confidence", 0),
        #             sources=cached_result.get("sources", []),
        #             best_match=cached_result.get("bestMatch"),
        #         )
        
        # 3. 调用 danmu_api 进行匹配
        try:
            match_result = await danmu_api_provider.match(
                title=title,
                season=season,
                episode=episode,
                file_name=file_name,
            )
            
            # 解析匹配结果
            is_matched = match_result.get("isMatched", False)
            matches = match_result.get("matches", [])
            confidence = match_result.get("confidence", 0)
            
            # 构建源列表
            sources = []
            for match in matches:
                source = {
                    "episodeId": match.get("episodeId", 0),
                    "animeId": match.get("animeId", 0),
                    "animeTitle": match.get("animeTitle", ""),
                    "episodeTitle": match.get("episodeTitle", ""),
                    "type": match.get("type", ""),
                    "typeDescription": match.get("typeDescription", ""),
                    "shift": match.get("shift", 0),
                    "imageUrl": match.get("imageUrl", "")
                }
                sources.append(source)
            """
            "episodeId": 10002,
            "animeId": 236379,
            "animeTitle": "生万物(2025)【电视剧】from 360",
            "episodeTitle": "【qiyi】 第1集",
            "type": "电视剧",
            "typeDescription": "电视剧",
            "shift": 0,
            "imageUrl": "https://p.ssl.qhimg.com/d/dy_e6051d436a91031e7d1a1d3297128edc.jpg"
            """
            
            # 确定最佳匹配
            best_match = None
            if sources:
                best_match = sources[0]
                if is_matched and confidence >= self._confidence_threshold:
                    logger.info(f"Auto match succeeded with confidence: {confidence}")
            
            result = DanmuMatchResult(
                is_matched=is_matched and confidence >= self._confidence_threshold,
                confidence=confidence,
                sources=sources,
                best_match=best_match,
            )
            
            # # 缓存结果
            # if file_id:
            #     await danmu_cache_service.set_match_result(file_id, result.to_dict())
            
            return result
            
        except DanmuApiTimeoutError as e:
            logger.error(f"Match request timeout: {e}")
            return DanmuMatchResult(is_matched=False, confidence=0, sources=[])
            
        except DanmuApiUpstreamError as e:
            logger.error(f"Match upstream error: {e}")
            return DanmuMatchResult(is_matched=False, confidence=0, sources=[])
            
        except DanmuApiError as e:
            logger.error(f"Match error: {e}")
            return DanmuMatchResult(is_matched=False, confidence=0, sources=[])
    
    # ==================== 手动搜索 ====================
    async def search(
        self,
        keyword: str,
        search_type: str = "anime",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        手动搜索弹幕源
        
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
    
    # ==================== 弹幕获取 ====================
    
    async def get_danmu(
        self,
        episode_id: str,
        file_id: Optional[str] = None,
        load_mode: str = "segment",
        next_segment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        获取弹幕数据
        
        Args:
            episode_id: 剧集 I
            file_id: 文件 ID（用于获取偏移量）
            load_mode: 加载模式（full/segment）
            next_segment: 下一个分片信息（load_mode=segment 时可选）
            
        Returns:
            分片数据
            弹幕数据
        """
        logger.info(f"Getting danmu for episode: {episode_id}")
        
        # 获取偏移量
        offset = 0.0
        # if file_id:
        #     binding = await danmu_binding_service.get_binding(file_id)
        #     if binding:
        #         offset = binding.get("offset", 0.0)
        
        normalized_mode = load_mode if load_mode in {"full", "segment"} else "full"
        # cacheable = (
        #     normalized_mode == "full"
        #     and from_time is None
        #     and to_time is None
        #     and segment_index is None
        # )

        # # 检查缓存（仅全量模式）
        # if cacheable:
        #     cached = await danmu_cache_service.get_danmu(episode_id)
        #     if cached:
        #         logger.info(f"Found cached danmu for episode: {episode_id}")
        #         cached["episode_id"] = cached.get("episode_id") or cached.get("episodeId") or episode_id
        #         cached["load_mode"] = "full"
        #         if offset != 0:
        #             cached["comments"] = self._apply_offset(cached.get("comments", []), offset)
        #         return cached
        
        # 从 danmu_api 获取
        try:
            if next_segment:
                # result = await danmu_api_provider.get_segment_comment(next_segment) # 请求下一分片数据
                """
                "count": int(result.get("count", len(parsed)) or len(parsed)),
                "comments": parsed,
                "success": bool(result.get("success", True)),
                "errorCode": int(result.get("errorCode", 0) or 0),
                "errorMessage": str(result.get("errorMessage", "") or ""),
                """
            else:
                # 第一次请求弹幕数据，分片模式：所有分片数据+第一分片数据的弹幕；全量模式：所有弹幕数据
                result = await danmu_api_provider.get_danmu(
                    episode_id=episode_id,
                    load_mode=normalized_mode,
                    duration=True,
                    format="json"
                )
                """
                "episodeId": episode_id,
                "videoDuration": video_duration,
                "segmentList": segment_list,
                "count": len(segment_list)/len(comments),
                "comments": [],
                """

            danmu_data = await self._build_danmu_payload(
                source_result=result,
                episode_id=episode_id,
                offset=offset,
                load_mode=normalized_mode
            )
            """
            danmu_data:
            {
                "episode_id": episode_id,
                "segments": Dict[str, Any],
                "count": int,
                "comments": comments,
                "offset": offset,
                "video_duration": video_duration,
                # "load_mode": "full",
            }
            """

            # if cacheable:
            #     await danmu_cache_service.set_danmu(episode_id, danmu_data)

            return danmu_data
            
        except DanmuApiError as e:
            logger.error(f"Get danmu error: {e}")
            return {
                "episode_id": episode_id,
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



    async def get_danmu_from_url(
        self,
        video_url: str,
        file_id: Optional[str] = None,
        load_mode: str = "full",
        segment_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """通过视频 URL 获取弹幕，支持全量与分片模式。"""
        logger.info("Getting danmu from url")
        offset = 0.0
        if file_id:
            binding = await danmu_binding_service.get_binding(file_id)
            if binding:
                offset = binding.get("offset", 0.0)

        normalized_mode = load_mode if load_mode in {"full", "segment"} else "full"
        try:
            result = await danmu_api_provider.get_danmu_from_url(
                video_url=video_url,
                load_mode=normalized_mode,
                duration=True,
            )
            danmu_data = await self._build_danmu_payload(
                source_result=result,
                episode_id="url",
                offset=offset,
                load_mode=normalized_mode,
                segment_index=segment_index,
            )
            danmu_data["source_url"] = video_url
            return danmu_data
        except DanmuApiError as e:
            logger.error(f"Get danmu from url error: {e}")
            return {
                "episode_id": "url",
                "count": 0,
                "comments": [],
                "error": str(e),
                "load_mode": normalized_mode,
                "source_url": video_url,
            }
    
    async def get_danmu_by_file(
        self,
        file_id: str,
        from_time: Optional[int] = None,
        to_time: Optional[int] = None,
        load_mode: str = "full",
        segment_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        根据文件 ID 获取弹幕
        
        先查询绑定关系，再获取弹幕数据。
        
        Args:
            file_id: 文件 ID
            from_time: 开始时间（秒）
            to_time: 结束时间（秒）
            load_mode: 加载模式（full/segment）
            segment_index: 分片索引（load_mode=segment 时可选）
            
        Returns:
            弹幕数据
        """
        logger.info(f"Getting danmu for file: {file_id}")
        
        # 查询绑定
        binding = await danmu_binding_service.get_binding(file_id)
        if not binding:
            return {
                "fileId": file_id,
                "count": 0,
                "comments": [],
                "error": "No binding found for this file",
            }
        
        episode_id = binding["episodeId"]
        offset = binding.get("offset", 0.0)
        
        # 获取弹幕
        danmu_data = await self.get_danmu(
            episode_id=episode_id,
            from_time=from_time,
            to_time=to_time,
            file_id=file_id,
            load_mode=load_mode,
            segment_index=segment_index,
        )
        
        danmu_data["fileId"] = file_id
        danmu_data["binding"] = binding
        
        return danmu_data

    async def _build_danmu_payload(
        self,
        *,
        source_result: Dict[str, Any],
        episode_id: str,
        offset: float,
        load_mode: str
    ) -> Dict[str, Any]:
        """构建统一弹幕返回结构，兼容全量与分片模式。"""
        video_duration = int(source_result.get("videoDuration", 0) or 0)
        
        segment_list = source_result.get("segmentList", []) or []
        comments = source_result.get("comments", []) or []
        payload: Dict[str, Any] = {
            "episode_id": episode_id,
            "count": len(comments),
            "comments": comments,
            "offset": offset,
            "video_duration": video_duration,
            "segment_list": segment_list,
            "load_mode": load_mode,
        }

        return payload

    
    # ==================== 弹幕合并 ====================
    
    async def merge_danmu(
        self,
        episode_ids: List[str],
        from_time: Optional[int] = None,
        to_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        合并多个弹幕源
        
        Args:
            episode_ids: 剧集 ID 列表
            from_time: 开始时间（秒）
            to_time: 结束时间（秒）
            
        Returns:
            合并后的弹幕数据
        """
        logger.info(f"Merging danmu from {len(episode_ids)} sources")
        
        all_comments = []
        sources = []
        
        for episode_id in episode_ids:
            try:
                result = await self.get_danmu(
                    episode_id=episode_id,
                    from_time=from_time,
                    to_time=to_time,
                )
                
                comments = result.get("comments", [])
                all_comments.extend(comments)
                
                sources.append({
                    "episodeId": episode_id,
                    "count": len(comments),
                })
                
            except Exception as e:
                logger.error(f"Failed to get danmu from {episode_id}: {e}")
        
        # 去重
        unique_comments = self._deduplicate_comments(all_comments)
        
        # 按时间排序
        unique_comments.sort(key=lambda x: x.get("time", 0))
        
        return {
            "count": len(unique_comments),
            "comments": unique_comments,
            "sources": sources,
        }
    
    def _deduplicate_comments(
        self,
        comments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        弹幕去重
        
        基于内容和时间进行去重。
        """
        seen = set()
        unique = []
        
        for comment in comments:
            # 使用内容和时间作为去重键
            key = (
                comment.get("content", ""),
                comment.get("time", 0) // 1000,  # 精确到秒
            )
            
            if key not in seen:
                seen.add(key)
                unique.append(comment)
        
        return unique
    
    def _apply_offset(
        self,
        comments: List[Dict[str, Any]],
        offset: float,
    ) -> List[Dict[str, Any]]:
        """
        应用时间偏移量
        
        Args:
            comments: 弹幕列表
            offset: 偏移量（秒）
            
        Returns:
            调整后的弹幕列表
        """
        if offset == 0:
            return comments
        
        offset_ms = int(offset * 1000)
        
        for comment in comments:
            original_time = comment.get("time", 0)
            comment["time"] = max(0, original_time + offset_ms)
        
        return comments
    
    # ==================== 绑定管理 ====================
    
    async def bind(
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
    
    async def get_platforms(self) -> List[Dict[str, Any]]:
        """获取支持的平台列表"""
        return await danmu_api_provider.get_platforms()
    
    async def check_platform_status(self, platform: str) -> Dict[str, Any]:
        """检查平台状态"""
        return await danmu_api_provider.check_platform_status(platform)


# 全局单例
danmu_service = DanmuService()
