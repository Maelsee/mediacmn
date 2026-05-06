"""存储客户端连接池 - per-storage_id 池化复用"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
from contextlib import asynccontextmanager

from .storage_client import StorageClient

logger = logging.getLogger(__name__)


@dataclass
class PooledClient:
    """池化客户端条目"""
    client: StorageClient
    user_id: int
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    in_use: bool = False
    use_count: int = 0


class StorageClientPool:
    """per-storage_id 的客户端连接池，带 TTL 和健康检查

    设计要点：
    - 同一 storage_id 同时只有一个活跃客户端（in_use 时复用）
    - 空闲超过 max_idle_seconds 的客户端自动回收
    - 健康检查通过 client.is_alive() 同步判断
    - 池满时优先淘汰空闲且过期的客户端
    """

    def __init__(self, max_idle_seconds: int = 300, max_clients: int = 50):
        self._pool: dict[int, PooledClient] = {}
        self._lock = asyncio.Lock()
        self._max_idle = max_idle_seconds
        self._max_clients = max_clients

    @asynccontextmanager
    async def acquire(self, storage_id: int, user_id: int, client_factory: Callable[[], Awaitable[StorageClient]]):
        """
        获取或创建客户端。上下文管理器自动归还。

        Args:
            storage_id: 存储配置 ID
            user_id: 用户 ID（用于校验归属）
            client_factory: 异步工厂函数，返回已连接的 StorageClient
        """
        pooled = None
        async with self._lock:
            pooled = self._pool.get(storage_id)
            if pooled and not pooled.in_use:
                # 健康检查：连接仍有效且归属正确
                if pooled.client.is_alive() and pooled.user_id == user_id:
                    pooled.in_use = True
                    pooled.last_used = time.time()
                    pooled.use_count += 1
                    logger.debug(f"连接池命中: storage_id={storage_id}, 累计使用 {pooled.use_count} 次")
                else:
                    # 连接已失效或归属不匹配，移除旧条目
                    logger.debug(f"连接池条目过期或归属不匹配: storage_id={storage_id}")
                    try:
                        await pooled.client.disconnect()
                    except Exception:
                        pass
                    del self._pool[storage_id]
                    pooled = None
            elif pooled and pooled.in_use:
                # 客户端正忙，创建临时客户端（不入池）
                logger.debug(f"连接池客户端正忙，创建临时客户端: storage_id={storage_id}")
                pooled = None

        if pooled is None:
            # 创建新客户端
            client = await client_factory()
            async with self._lock:
                # 池满时淘汰过期条目
                if len(self._pool) >= self._max_clients:
                    await self._evict_stale()
                pooled = PooledClient(client=client, user_id=user_id, in_use=True, use_count=1)
                self._pool[storage_id] = pooled
                logger.debug(f"连接池新增: storage_id={storage_id}, 当前池大小 {len(self._pool)}")

        try:
            yield pooled.client
        finally:
            async with self._lock:
                pooled.in_use = False
                pooled.last_used = time.time()

    async def close(self, storage_id: int):
        """关闭并移除指定 storage_id 的客户端"""
        async with self._lock:
            pooled = self._pool.pop(storage_id, None)
        if pooled:
            try:
                await pooled.client.disconnect()
            except Exception:
                pass
            logger.debug(f"连接池已关闭: storage_id={storage_id}")

    async def close_all(self):
        """关闭并移除所有客户端"""
        async with self._lock:
            clients = list(self._pool.values())
            self._pool.clear()
        for pooled in clients:
            try:
                await pooled.client.disconnect()
            except Exception:
                pass
        logger.debug("连接池已全部关闭")

    async def _evict_stale(self):
        """淘汰过期或失效的条目（调用方需持有 _lock）"""
        now = time.time()
        stale_ids = [
            sid for sid, p in self._pool.items()
            if not p.in_use and (now - p.last_used > self._max_idle or not p.client.is_alive())
        ]
        for sid in stale_ids:
            pooled = self._pool.pop(sid, None)
            if pooled:
                try:
                    await pooled.client.disconnect()
                except Exception:
                    pass
                logger.debug(f"连接池淘汰过期条目: storage_id={sid}")


# 全局单例
_client_pool = StorageClientPool()


def get_client_pool() -> StorageClientPool:
    """获取全局连接池实例"""
    return _client_pool
