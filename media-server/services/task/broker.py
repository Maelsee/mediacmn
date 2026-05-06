from dramatiq import set_broker
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import TimeLimit, Retries,AsyncIO
from core.config import get_settings
import logging
logger = logging.getLogger(__name__)



# 全局配置
DEAD_LETTER_QUEUE = "dead_letter"  # 死信队列名称（统一存储所有重试失败的任务）
DEFAULT_MAX_RETRIES = 5  # 全局默认重试次数
DEFAULT_MIN_BACKOFF = 10000  # 重试最小间隔（毫秒）
DEFAULT_MAX_BACKOFF = 300000  # 重试最大间隔（毫秒）

_broker_instance = None


def get_broker() -> RedisBroker:
    global _broker_instance
    if _broker_instance is None:
        s = get_settings()       
        # 1. 初始化 Broker（保持你的配置）
        _broker_instance = RedisBroker(
            url=f"{s.REDIS_URL}/{s.REDIS_DB}",
            # 2. 配置核心中间件（AsyncIO 中间件支持异步 actor）
            middleware=[
                TimeLimit(time_limit=7200000),  # 2小时（大库扫描需要更长时间）
                Retries(
                    max_retries=DEFAULT_MAX_RETRIES,
                    min_backoff=DEFAULT_MIN_BACKOFF,
                    max_backoff=DEFAULT_MAX_BACKOFF,
                     # 只对特定异常重试（可选，避免无意义重试）
                    retry_when=lambda e: isinstance(e, (ConnectionError, TimeoutError))
                ), 
                AsyncIO(),
                ]
        )

        # 声明所有队列（确保生产者和消费者都能识别）
        for queue in ["scan", "metadata", "persist", "persist_batch", "delete", "localize"]:
            _broker_instance.declare_queue(queue)

        # 关键：全局注册 Broker，让所有 Actor 默认使用这个实例
        set_broker(_broker_instance)
    return _broker_instance

# 初始化时自动创建并注册 Broker（避免导入时未初始化）
broker = get_broker()

