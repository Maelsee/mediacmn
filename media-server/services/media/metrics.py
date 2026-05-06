"""元数据丰富器性能指标收集

收集解析和刮削的准确率/性能指标，存储到 Redis Hash 用于调优。
"""
import time
import logging
from typing import Optional

import redis.asyncio as redis

from core.config import get_settings

logger = logging.getLogger(__name__)

_METRICS_KEY = "enricher:metrics"
_metrics_redis: Optional[redis.Redis] = None


def _get_redis() -> Optional[redis.Redis]:
    global _metrics_redis
    if _metrics_redis is not None:
        return _metrics_redis
    try:
        s = get_settings()
        _metrics_redis = redis.from_url(
            s.REDIS_URL, db=s.REDIS_DB, decode_responses=True
        )
        return _metrics_redis
    except Exception:
        return None


async def record_parse(source: str, title: str, confidence: float, used_ai: bool = False):
    """记录一次解析事件"""
    r = _get_redis()
    if not r:
        return
    try:
        pipe = r.pipeline()
        pipe.hincrby(_METRICS_KEY, "parse:total", 1)
        pipe.hincrby(_METRICS_KEY, f"parse:source:{source}", 1)
        if used_ai:
            pipe.hincrby(_METRICS_KEY, "parse:ai_fallback", 1)
        pipe.hincrbyfloat(_METRICS_KEY, "parse:confidence_sum", confidence)
        await pipe.execute()
    except Exception:
        pass


async def record_search(plugin: str, query: str, hit: bool, latency_ms: float):
    """记录一次搜索事件"""
    r = _get_redis()
    if not r:
        return
    try:
        pipe = r.pipeline()
        pipe.hincrby(_METRICS_KEY, "search:total", 1)
        pipe.hincrby(_METRICS_KEY, f"search:plugin:{plugin}", 1)
        if hit:
            pipe.hincrby(_METRICS_KEY, "search:hit", 1)
        else:
            pipe.hincrby(_METRICS_KEY, "search:miss", 1)
        pipe.hincrbyfloat(_METRICS_KEY, "search:latency_sum_ms", latency_ms)
        await pipe.execute()
    except Exception:
        pass


async def record_cache(level: str, hit: bool):
    """记录一次缓存事件（level: lru/redis）"""
    r = _get_redis()
    if not r:
        return
    try:
        pipe = r.pipeline()
        pipe.hincrby(_METRICS_KEY, f"cache:{level}:total", 1)
        if hit:
            pipe.hincrby(_METRICS_KEY, f"cache:{level}:hit", 1)
        await pipe.execute()
    except Exception:
        pass


async def record_match(title: str, score: float, accepted: bool):
    """记录一次匹配评分事件"""
    r = _get_redis()
    if not r:
        return
    try:
        pipe = r.pipeline()
        pipe.hincrby(_METRICS_KEY, "match:total", 1)
        pipe.hincrbyfloat(_METRICS_KEY, "match:score_sum", score)
        if accepted:
            pipe.hincrby(_METRICS_KEY, "match:accepted", 1)
        else:
            pipe.hincrby(_METRICS_KEY, "match:rejected", 1)
        await pipe.execute()
    except Exception:
        pass


async def record_enrich(success: bool, latency_ms: float):
    """记录一次完整丰富流程"""
    r = _get_redis()
    if not r:
        return
    try:
        pipe = r.pipeline()
        pipe.hincrby(_METRICS_KEY, "enrich:total", 1)
        if success:
            pipe.hincrby(_METRICS_KEY, "enrich:success", 1)
        else:
            pipe.hincrby(_METRICS_KEY, "enrich:fail", 1)
        pipe.hincrbyfloat(_METRICS_KEY, "enrich:latency_sum_ms", latency_ms)
        await pipe.execute()
    except Exception:
        pass


async def get_metrics_summary() -> dict:
    """获取指标汇总（用于 API 展示）"""
    r = _get_redis()
    if not r:
        return {}
    try:
        data = await r.hgetall(_METRICS_KEY)
        # 计算派生指标
        parse_total = int(data.get("parse:total", 0))
        search_total = int(data.get("search:total", 0))
        search_hit = int(data.get("search:hit", 0))
        match_total = int(data.get("match:total", 0))
        match_accepted = int(data.get("match:accepted", 0))
        enrich_total = int(data.get("enrich:total", 0))
        enrich_success = int(data.get("enrich:success", 0))

        return {
            "parse": {
                "total": parse_total,
                "ai_fallback": int(data.get("parse:ai_fallback", 0)),
                "avg_confidence": (
                    round(float(data.get("parse:confidence_sum", 0)) / parse_total, 3)
                    if parse_total > 0 else 0
                ),
            },
            "search": {
                "total": search_total,
                "hit_rate": round(search_hit / search_total, 3) if search_total > 0 else 0,
                "avg_latency_ms": (
                    round(float(data.get("search:latency_sum_ms", 0)) / search_total, 1)
                    if search_total > 0 else 0
                ),
            },
            "match": {
                "total": match_total,
                "accept_rate": round(match_accepted / match_total, 3) if match_total > 0 else 0,
                "avg_score": (
                    round(float(data.get("match:score_sum", 0)) / match_total, 1)
                    if match_total > 0 else 0
                ),
            },
            "enrich": {
                "total": enrich_total,
                "success_rate": round(enrich_success / enrich_total, 3) if enrich_total > 0 else 0,
                "avg_latency_ms": (
                    round(float(data.get("enrich:latency_sum_ms", 0)) / enrich_total, 1)
                    if enrich_total > 0 else 0
                ),
            },
        }
    except Exception:
        return {}
