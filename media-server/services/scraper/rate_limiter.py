"""per-plugin 令牌桶频率限制器"""
import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """令牌桶限速器，为每个插件维护独立的令牌桶"""

    def __init__(self):
        self._buckets: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    def configure(self, plugin_name: str, rate: float, burst: int = 1):
        """配置插件的频率限制。rate=每秒令牌数，burst=桶容量"""
        self._buckets[plugin_name] = {
            "rate": rate,
            "burst": burst,
            "tokens": float(burst),
            "last_refill": time.monotonic(),
        }

    async def acquire(self, plugin_name: str):
        """等待直到获得令牌（无限制时直接通过）"""
        bucket = self._buckets.get(plugin_name)
        if not bucket:
            return  # 未配置限制，直接通过

        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - bucket["last_refill"]
                bucket["tokens"] = min(
                    bucket["burst"],
                    bucket["tokens"] + elapsed * bucket["rate"],
                )
                bucket["last_refill"] = now

                if bucket["tokens"] >= 1.0:
                    bucket["tokens"] -= 1.0
                    return

            # 等待一个令牌刷新周期
            wait = 1.0 / bucket["rate"]
            await asyncio.sleep(wait)
