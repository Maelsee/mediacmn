"""
DanmuApi 服务适配器

本模块封装 danmu_api (https://github.com/huangxd-/danmu_api) 的 API 调用，
提供统一的弹幕获取接口。danmu_api 兼容弹弹play API 规范。

支持的 API 接口：
- GET  /api/v2/search/anime?keyword={keyword} - 搜索动漫
- GET  /api/v2/search/episodes?keyword={keyword} - 搜索剧集
- POST /api/v2/match - 自动匹配
- GET  /api/v2/bangumi/{animeId} - 获取番剧详情
- GET  /api/v2/comment/{episodeId} - 获取弹幕
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum

import aiohttp
from core.logging import logger
from core.config import get_settings


class DanmuApiError(Exception):
    """弹幕 API 基础异常"""
    pass


class DanmuApiConnectionError(DanmuApiError):
    """连接异常"""
    pass


class DanmuApiTimeoutError(DanmuApiError):
    """超时异常"""
    pass


class DanmuApiUpstreamError(DanmuApiError):
    """上游服务异常"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"DanmuApi upstream error: {status_code} {message}")


class DanmuApiNotConfiguredError(DanmuApiError):
    """服务未配置异常"""
    pass


class PlatformType(str, Enum):
    """弹幕平台类型"""
    BILIBILI = "bilibili"
    TENCENT = "tencent"
    IQIYI = "iqiyi"
    YOUKU = "youku"
    MANGGUO = "mangguo"
    MGTV = "mgtv"  # 芒果TV
    DOUBAN = "douban"
    TMDB = "tmdb"


@dataclass(frozen=True)
class DanmuApiConfig:
    """DanmuApi 配置"""
    base_url: str
    token: str
    timeout_seconds: int
    request_timeout: int


class DanmuApiProvider:
    """
    DanmuApi 服务适配器
    
    封装 danmu_api 的所有 API 调用，提供统一的接口。
    支持搜索、匹配、获取弹幕等功能。
    """
    
    # 平台名称映射
    PLATFORM_NAMES = {
        "bilibili": "B站",
        "tencent": "腾讯视频",
        "iqiyi": "爱奇艺",
        "youku": "优酷",
        "mangguo": "芒果TV",
        "mgtv": "芒果TV",
        "douban": "豆瓣",
        "tmdb": "TMDB",
    }
    
    def __init__(self) -> None:
        """初始化 DanmuApi 适配器"""
        settings = get_settings()
        
        # 从配置读取 danmu_api 设置
        self._base_url = getattr(settings, "DANMU_API_URL", "http://127.0.0.1:9321").rstrip("/")
        self._token = getattr(settings, "DANMU_API_TOKEN", "")
        self._timeout_seconds = int(getattr(settings, "DANMU_API_TIMEOUT", 30))
        self._request_timeout = int(getattr(settings, "DANMU_API_REQUEST_TIMEOUT", 10000)) // 1000
        
        # HTTP 客户端会话（延迟初始化）
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"DanmuApiProvider initialized with base_url={self._base_url}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._build_headers(),
            )
        return self._session
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
    
    def _build_url(self, path: str) -> str:
        """
        构建 API URL
        
        danmu_api 的 URL 格式为: {base_url}/{token}/api/v2/...
        或者: {base_url}/api/v2/... (如果不需要 token)
        """
        if self._token:
            return f"{self._base_url}/{self._token}{path}"
        return f"{self._base_url}{path}"
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求
        
        Args:
            method: HTTP 方法 (GET, POST, etc.)
            path: API 路径
            params: URL 参数
            json_data: JSON 请求体
            
        Returns:
            API 响应数据
            
        Raises:
            DanmuApiConnectionError: 连接失败
            DanmuApiTimeoutError: 请求超时
            DanmuApiUpstreamError: 上游服务错误
        """
        session = await self._get_session()
        url = self._build_url(path)
        
        try:
            async with session.request(
                method,
                url,
                params=params,
                json=json_data,
            ) as response:
                if response.status == 401:
                    raise DanmuApiNotConfiguredError("DanmuApi token is invalid or missing")
                
                if response.status == 429:
                    raise DanmuApiUpstreamError(
                        response.status,
                        "Rate limit exceeded, please try again later"
                    )
                
                if response.status >= 500:
                    text = await response.text()
                    raise DanmuApiUpstreamError(response.status, text[:500])
                
                if response.status >= 400:
                    text = await response.text()
                    raise DanmuApiUpstreamError(response.status, text[:500])
                
                data = await response.json()
                return data
                
        except asyncio.TimeoutError as e:
            logger.error(f"DanmuApi request timeout: {url}")
            raise DanmuApiTimeoutError(f"Request to {url} timed out") from e
            
        except aiohttp.ClientError as e:
            logger.error(f"DanmuApi connection error: {url}, error: {e}")
            raise DanmuApiConnectionError(f"Failed to connect to DanmuApi: {e}") from e
    
    # ==================== 搜索接口 ====================
    
    async def search_anime(
        self,
        keyword: str,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        搜索动漫
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            搜索结果，包含动漫列表
        """
        logger.info(f"Searching anime with keyword: {keyword}")
        
        params = {"keyword": keyword}
        if limit:
            params["limit"] = limit
            
        result = await self._request("GET", "/api/v2/search/anime", params=params)
        
        return {
            "keyword": keyword,
            "animes": result.get("animes", []),
            "hasMore": result.get("hasMore", False),
        }
    
    async def search_episodes(
        self,
        keyword: str,
        anime_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        搜索剧集
        
        Args:
            keyword: 搜索关键词
            anime_id: 动漫 ID（可选，用于限定搜索范围）
            limit: 返回结果数量限制
            
        Returns:
            搜索结果，包含剧集列表
        """
        logger.info(f"Searching episodes with keyword: {keyword}")
        
        params = {"keyword": keyword}
        if anime_id:
            params["animeId"] = anime_id
        if limit:
            params["limit"] = limit
            
        result = await self._request("GET", "/api/v2/search/episodes", params=params)
        
        return {
            "keyword": keyword,
            "episodes": result.get("episodes", []),
            "hasMore": result.get("hasMore", False),
        }
    
    # ==================== 匹配接口 ====================
    
    async def match(
        self,
        title: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        file_name: Optional[str] = None,
        file_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        file_duration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        自动匹配弹幕源
        
        根据视频信息自动匹配对应的弹幕源。
        
        Args:
            title: 视频标题
            season: 季数（可选）
            episode: 集数（可选）
            file_name: 文件名（可选）
            file_hash: 文件哈希（可选）
            file_size: 文件大小（可选）
            file_duration: 文件时长（可选）
            
        Returns:
            匹配结果，包含是否匹配成功和候选列表
        """
        logger.info(f"Matching danmu for: {title}, season={season}, episode={episode}")
        
        # 构建匹配请求
        request_data = {
            "title": title,
        }
        
        if season is not None:
            request_data["season"] = season
        if episode is not None:
            request_data["episode"] = episode
        if file_name:
            request_data["fileName"] = file_name
        if file_hash:
            request_data["fileHash"] = file_hash
        if file_size:
            request_data["fileSize"] = file_size
        if file_duration:
            request_data["fileDuration"] = file_duration
        
        result = await self._request("POST", "/api/v2/match", json_data=request_data)
        
        # 解析匹配结果
        is_matched = result.get("isMatched", False)
        matches = result.get("matches", [])
        
        return {
            "isMatched": is_matched,
            "matches": matches,
            "confidence": self._calculate_confidence(is_matched, matches),
        }
    
    def _calculate_confidence(
        self,
        is_matched: bool,
        matches: List[Dict[str, Any]],
    ) -> float:
        """
        计算匹配置信度
        
        Args:
            is_matched: 是否精确匹配
            matches: 匹配结果列表
            
        Returns:
            置信度分数 (0.0 - 1.0)
        """
        if is_matched and len(matches) == 1:
            return 1.0
        
        if not matches:
            return 0.0
        
        # 根据匹配数量和排序计算置信度
        # 第一个匹配项权重最高
        if len(matches) >= 1:
            first_match = matches[0]
            # 如果第一个匹配项有相似度分数，使用它
            if "similarity" in first_match:
                return float(first_match["similarity"])
            
            # 否则根据匹配数量估算
            return max(0.5, 1.0 - (len(matches) - 1) * 0.1)
        
        return 0.3
    
    # ==================== 详情接口 ====================
    
    async def get_bangumi_detail(
        self,
        anime_id: str,
    ) -> Dict[str, Any]:
        """
        获取番剧详情
        
        Args:
            anime_id: 番剧 ID
            
        Returns:
            番剧详情，包含剧集列表
        """
        logger.info(f"Getting bangumi detail: {anime_id}")
        
        result = await self._request("GET", f"/api/v2/bangumi/{anime_id}")
        
        return {
            "animeId": result.get("animeId", anime_id),
            "animeTitle": result.get("animeTitle", ""),
            "type": result.get("type", ""),
            "typeDescription": result.get("typeDescription", ""),
            "imageUrl": result.get("imageUrl", ""),
            "startDate": result.get("startDate", ""),
            "episodeCount": result.get("episodeCount", 0),
            "episodes": result.get("episodes", []),
        }
    
    # ==================== 弹幕获取接口 ====================
    
    async def get_danmu(
        self,
        episode_id: str,
        load_mode: str = "segment",
        duration: bool = True,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        获取弹幕数据
        
        Args:
            episode_id: 剧集 ID
            load_mode: 加载模式（full/segment）
            duration: 是否返回视频时长
            format: 数据格式（json）
            
        Returns:
            弹幕数据
        """
        logger.info(f"Getting danmu for episode: {episode_id}")
        
        params = {}
        params["format"] = format
        params["segmentflag"] = "true" if load_mode == "segment" else "false"
        params["duration"] = "true" if duration else "false"

        result = await self._request("GET", f"/api/v2/comment/{episode_id}", params=params)

        video_duration = int(result.get("videoDuration", 0) or 0)
        comments_data = result.get("comments", [])

        if load_mode == "segment":
            segment_list: List[Dict[str, Any]] = []
            if isinstance(comments_data, dict):
                segment_list = comments_data.get("segmentList", []) or []
            elif isinstance(result.get("segmentList"), list):
                segment_list = result.get("segmentList", [])
            if segment_list:
                comments_data = await self.get_segment_comment(segment_list[0], format=format)
            comments = comments_data.get("comments", []) or []
            return {
                "episodeId": episode_id,
                "videoDuration": video_duration,
                "segmentList": segment_list,
                "count": int(comments_data.get("count", 0) or 0),
                "comments": comments,
            }

        comments: List[Dict[str, Any]] = comments_data if isinstance(comments_data, list) else []
        # parsed = self._parse_comments(comments)
        parsed = comments
        return {
            "episodeId": episode_id,
            "videoDuration": video_duration,
            "count": int(result.get("count", len(parsed)) or len(parsed)),
            "comments": parsed,
        }

    async def get_segment_comment(self, segment_payload: Dict[str, Any], format: str = "json") -> Dict[str, Any]:
        """按分片描述拉取单段弹幕。"""
        result = await self._request(
            "POST",
            "/api/v2/segmentcomment",
            params={"format": format},
            json_data=segment_payload,
        )
        comments = result.get("comments", [])
        # parsed = self._parse_comments(comments if isinstance(comments, list) else [])
        parsed = comments if isinstance(comments, list) else []
        return {
            "count": int(result.get("count", len(parsed)) or len(parsed)),
            "comments": parsed,
            "success": bool(result.get("success", True)),
            "errorCode": int(result.get("errorCode", 0) or 0),
            "errorMessage": str(result.get("errorMessage", "") or ""),
        }

    async def get_danmu_from_url(
        self,
        video_url: str,
        *,
        load_mode: str = "full",
        duration: bool = True,
    ) -> Dict[str, Any]:
        """通过视频 URL 获取弹幕（平台自动识别）。"""
        params: Dict[str, Any] = {
            "url": video_url,
            "format": "json",
            "segmentflag": "true" if load_mode == "segment" else "false",
        }
        if duration:
            params["duration"] = "true"

        result = await self._request("GET", "/api/v2/comment", params=params)
        video_duration = int(result.get("videoDuration", 0) or 0)
        comments_data = result.get("comments", [])

        if load_mode == "segment":
            segment_list: List[Dict[str, Any]] = []
            if isinstance(comments_data, dict):
                segment_list = comments_data.get("segmentList", []) or []
            elif isinstance(result.get("segmentList"), list):
                segment_list = result.get("segmentList", [])
            return {
                "videoDuration": video_duration,
                "segmentList": segment_list,
                "count": len(segment_list),
                "comments": [],
            }

        comments: List[Dict[str, Any]] = comments_data if isinstance(comments_data, list) else []
        # parsed = self._parse_comments(comments)
        parsed = comments
        return {
            "videoDuration": video_duration,
            "count": int(result.get("count", len(parsed)) or len(parsed)),
            "comments": parsed,
        }
    
    def _parse_comments(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        解析弹幕数据为统一格式
        
        danmu_api 返回的弹幕格式：
        {
            "cid": "弹幕ID",
            "p": "时间,类型,颜色,字号,发送者",
            "m": "弹幕内容"
        }
        
        统一格式：
        {
            "id": "弹幕ID",
            "time": 时间(毫秒),
            "content": "弹幕内容",
            "color": "#FFFFFF",
            "type": "scroll|top|bottom",
            "fontSize": 25,
            "source": "平台名称"
        }
        """
        parsed = []
        
        for comment in comments:
            try:
                cid = comment.get("cid", "")
                p = comment.get("p", "").split(",")
                m = comment.get("m", "")
                
                if len(p) < 3:
                    continue
                
                time_seconds = float(p[0])
                danmu_type = int(p[1])
                color = int(p[2])
                font_size = 25
                source_token = ""
                if len(p) >= 4:
                    if p[3].isdigit():
                        font_size = int(p[3])
                        source_token = p[4] if len(p) > 4 else ""
                    else:
                        source_token = p[3]
                if len(p) >= 5 and not source_token:
                    source_token = p[4]

                source = source_token.strip()
                if source.startswith("[") and source.endswith("]"):
                    source = source[1:-1]
                
                # 转换弹幕类型
                type_map = {
                    1: "scroll",   # 滚动弹幕
                    2: "scroll",   # 滚动弹幕
                    3: "scroll",   # 滚动弹幕
                    4: "bottom",   # 底部弹幕
                    5: "top",      # 顶部弹幕
                    6: "scroll",   # 逆向弹幕（当作滚动处理）
                    7: "scroll",   # 精准定位弹幕
                    8: "scroll",   # 高级弹幕
                }
                
                parsed.append({
                    "id": cid,
                    "time": int(time_seconds * 1000),  # 转换为毫秒
                    "content": m,
                    "color": f"#{color:06X}",
                    "type": type_map.get(danmu_type, "scroll"),
                    "font_size": float(font_size),
                    "source": source or comment.get("source", "unknown"),
                })
                
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse comment: {comment}, error: {e}")
                continue
        
        return parsed
    
    # ==================== 平台状态接口 ====================
    
    async def get_platforms(self) -> List[Dict[str, Any]]:
        """
        获取支持的平台列表
        
        Returns:
            平台列表
        """
        platforms = []
        for platform_id, platform_name in self.PLATFORM_NAMES.items():
            platforms.append({
                "id": platform_id,
                "name": platform_name,
                "enabled": True,
            })
        return platforms
    
    async def check_platform_status(self, platform: str) -> Dict[str, Any]:
        """
        检查平台状态
        
        Args:
            platform: 平台 ID
            
        Returns:
            平台状态信息
        """
        # 简单的健康检查，尝试搜索该平台的内容
        try:
            # 使用一个简单的搜索来检查平台是否可用
            result = await self.search_anime("test", limit=1)
            return {
                "platform": platform,
                "available": True,
                "latency": 0,
            }
        except Exception as e:
            return {
                "platform": platform,
                "available": False,
                "error": str(e),
            }
    
    # ==================== 生命周期管理 ====================
    
    async def close(self) -> None:
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("DanmuApiProvider session closed")


# 全局单例
danmu_api_provider = DanmuApiProvider()
