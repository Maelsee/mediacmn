"""
弹幕缓存服务

本模块提供弹幕数据的缓存管理，包括：
- Redis 缓存层
- 缓存键管理
- 缓存预热
- 缓存失效策略
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from core.logging import logger
from core.config import get_settings


class DanmuCacheError(Exception):
    """弹幕缓存异常"""
    pass


class DanmuCacheService:
    """
    弹幕缓存服务
    
    使用 Redis 作为缓存层，提供弹幕数据的缓存管理。
    支持多级缓存策略：
    - 弹幕数据缓存：缓存完整的弹幕数据
    - 匹配结果缓存：缓存匹配结果
    - 搜索结果缓存：缓存搜索结果
    """
    
    # 缓存键前缀
    KEY_PREFIX = "danmu"
    
    # 缓存键模板
    KEYS = {
        "danmu": "{prefix}:danmu:{episode_id}",           # 弹幕数据
        "danmu_segment": "{prefix}:segment:{episode_id}:{from_time}:{to_time}",  # 分段弹幕
        "match": "{prefix}:match:{file_id}",              # 匹配结果
        "search": "{prefix}:search:{keyword_hash}",       # 搜索结果
        "binding": "{prefix}:binding:{file_id}",          # 绑定关系
        "platform_status": "{prefix}:platform:{platform}", # 平台状态
    }
    
    # 默认缓存时间（秒）
    DEFAULT_TTL = {
        "danmu": 86400 * 7,      # 弹幕数据缓存 7 天
        "danmu_segment": 86400,   # 分段弹幕缓存 1 天
        "match": 86400,           # 匹配结果缓存 1 天
        "search": 3600,           # 搜索结果缓存 1 小时
        "binding": 86400 * 30,    # 绑定关系缓存 30 天
        "platform_status": 300,   # 平台状态缓存 5 分钟
    }
    
    def __init__(self) -> None:
        """初始化缓存服务"""
        settings = get_settings()
        
        # Redis 配置
        self._redis_url = getattr(settings, "REDIS_CACHE_URL", "redis://:redis123@localhost:10002/0")
        self._enabled = getattr(settings, "DANMU_CACHE_ENABLED", True)
        self._default_ttl = getattr(settings, "DANMU_CACHE_DEFAULT_TTL", 86400)
        
        # Redis 客户端（延迟初始化）
        self._client: Optional[redis.Redis] = None
        
        logger.info(f"DanmuCacheService initialized, enabled={self._enabled}")
    
    async def _get_client(self) -> redis.Redis:
        """获取或创建 Redis 客户端"""
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client
    
    def _build_key(self, key_type: str, **kwargs) -> str:
        """构建缓存键"""
        template = self.KEYS.get(key_type, "{prefix}:{key_type}")
        return template.format(prefix=self.KEY_PREFIX, key_type=key_type, **kwargs)
    
    # ==================== 弹幕数据缓存 ====================
    
    async def get_danmu(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的弹幕数据
        
        Args:
            episode_id: 剧集 ID
            
        Returns:
            缓存的弹幕数据，如果不存在返回 None
        """
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            key = self._build_key("danmu", episode_id=episode_id)
            data = await client.get(key)
            
            if data:
                logger.debug(f"Cache hit for danmu: {episode_id}")
                return json.loads(data)
            
            logger.debug(f"Cache miss for danmu: {episode_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get danmu from cache: {e}")
            return None
    
    async def set_danmu(
        self,
        episode_id: str,
        danmu_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        缓存弹幕数据
        
        Args:
            episode_id: 剧集 ID
            danmu_data: 弹幕数据
            ttl: 缓存时间（秒），默认使用配置值
            
        Returns:
            是否缓存成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._build_key("danmu", episode_id=episode_id)
            ttl = ttl or self.DEFAULT_TTL["danmu"]
            
            await client.setex(
                key,
                ttl,
                json.dumps(danmu_data, ensure_ascii=False),
            )
            
            logger.debug(f"Cached danmu for episode: {episode_id}, ttl={ttl}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache danmu: {e}")
            return False
    
    async def get_danmu_segment(
        self,
        episode_id: str,
        from_time: int,
        to_time: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的分段弹幕数据
        
        Args:
            episode_id: 剧集 ID
            from_time: 开始时间（秒）
            to_time: 结束时间（秒）
            
        Returns:
            缓存的弹幕列表，如果不存在返回 None
        """
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            key = self._build_key(
                "danmu_segment",
                episode_id=episode_id,
                from_time=from_time,
                to_time=to_time,
            )
            data = await client.get(key)
            
            if data:
                logger.debug(f"Cache hit for danmu segment: {episode_id}[{from_time}-{to_time}]")
                return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get danmu segment from cache: {e}")
            return None
    
    async def set_danmu_segment(
        self,
        episode_id: str,
        from_time: int,
        to_time: int,
        danmu_list: List[Dict[str, Any]],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        缓存分段弹幕数据
        
        Args:
            episode_id: 剧集 ID
            from_time: 开始时间（秒）
            to_time: 结束时间（秒）
            danmu_list: 弹幕列表
            ttl: 缓存时间（秒）
            
        Returns:
            是否缓存成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._build_key(
                "danmu_segment",
                episode_id=episode_id,
                from_time=from_time,
                to_time=to_time,
            )
            ttl = ttl or self.DEFAULT_TTL["danmu_segment"]
            
            await client.setex(
                key,
                ttl,
                json.dumps(danmu_list, ensure_ascii=False),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache danmu segment: {e}")
            return False
    
    # ==================== 匹配结果缓存 ====================
    
    async def get_match_result(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的匹配结果
        
        Args:
            file_id: 文件 ID
            
        Returns:
            缓存的匹配结果，如果不存在返回 None
        """
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            key = self._build_key("match", file_id=file_id)
            data = await client.get(key)
            
            if data:
                logger.debug(f"Cache hit for match result: {file_id}")
                return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get match result from cache: {e}")
            return None
    
    async def set_match_result(
        self,
        file_id: str,
        match_result: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        缓存匹配结果
        
        Args:
            file_id: 文件 ID
            match_result: 匹配结果
            ttl: 缓存时间（秒）
            
        Returns:
            是否缓存成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._build_key("match", file_id=file_id)
            ttl = ttl or self.DEFAULT_TTL["match"]
            
            await client.setex(
                key,
                ttl,
                json.dumps(match_result, ensure_ascii=False),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache match result: {e}")
            return False
    
    # ==================== 搜索结果缓存 ====================
    
    async def get_search_result(self, keyword: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的搜索结果
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            缓存的搜索结果，如果不存在返回 None
        """
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            # 使用关键词的哈希作为键
            keyword_hash = hash(keyword)
            key = self._build_key("search", keyword_hash=keyword_hash)
            data = await client.get(key)
            
            if data:
                logger.debug(f"Cache hit for search: {keyword}")
                return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get search result from cache: {e}")
            return None
    
    async def set_search_result(
        self,
        keyword: str,
        search_result: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        缓存搜索结果
        
        Args:
            keyword: 搜索关键词
            search_result: 搜索结果
            ttl: 缓存时间（秒）
            
        Returns:
            是否缓存成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            keyword_hash = hash(keyword)
            key = self._build_key("search", keyword_hash=keyword_hash)
            ttl = ttl or self.DEFAULT_TTL["search"]
            
            await client.setex(
                key,
                ttl,
                json.dumps(search_result, ensure_ascii=False),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache search result: {e}")
            return False
    
    # ==================== 绑定关系缓存 ====================
    
    async def get_binding(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的绑定关系
        
        Args:
            file_id: 文件 ID
            
        Returns:
            缓存的绑定关系，如果不存在返回 None
        """
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            key = self._build_key("binding", file_id=file_id)
            data = await client.get(key)
            
            if data:
                logger.debug(f"Cache hit for binding: {file_id}")
                return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get binding from cache: {e}")
            return None
    
    async def set_binding(
        self,
        file_id: str,
        binding_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        缓存绑定关系
        
        Args:
            file_id: 文件 ID
            binding_data: 绑定数据
            ttl: 缓存时间（秒）
            
        Returns:
            是否缓存成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._build_key("binding", file_id=file_id)
            ttl = ttl or self.DEFAULT_TTL["binding"]
            
            await client.setex(
                key,
                ttl,
                json.dumps(binding_data, ensure_ascii=False),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache binding: {e}")
            return False
    
    async def delete_binding(self, file_id: str) -> bool:
        """
        删除绑定的缓存
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否删除成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._build_key("binding", file_id=file_id)
            await client.delete(key)
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete binding from cache: {e}")
            return False
    
    # ==================== 缓存管理 ====================
    
    async def invalidate_danmu(self, episode_id: str) -> bool:
        """
        使弹幕缓存失效
        
        Args:
            episode_id: 剧集 ID
            
        Returns:
            是否成功
        """
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            
            # 删除弹幕数据缓存
            key = self._build_key("danmu", episode_id=episode_id)
            await client.delete(key)
            
            # 删除所有相关的分段缓存
            pattern = self._build_key("danmu_segment", episode_id=episode_id, from_time="*", to_time="*")
            keys = await client.keys(pattern.replace(":*:*", ":*"))
            if keys:
                await client.delete(*keys)
            
            logger.info(f"Invalidated danmu cache for episode: {episode_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to invalidate danmu cache: {e}")
            return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        if not self._enabled:
            return {"enabled": False}
        
        try:
            client = await self._get_client()
            info = await client.info("stats")
            
            return {
                "enabled": True,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0),
                ),
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"enabled": True, "error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """计算缓存命中率"""
        total = hits + misses
        if total == 0:
            return 0.0
        return round(hits / total, 4)
    
    # ==================== 生命周期管理 ====================
    
    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("DanmuCacheService connection closed")


# 全局单例
danmu_cache_service = DanmuCacheService()
