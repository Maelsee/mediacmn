import asyncio
from dramatiq import set_broker, Middleware  # 新增：全局注册 Broker
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import TimeLimit, Retries,AsyncIO

from core.config import get_settings
# from services.scraper.manager import scraper_manager  # 确保导入路径正确
import logging
logger = logging.getLogger(__name__)

# # --- 新增：插件系统初始化中间件 ---
# class ScraperInitializerMiddleware(Middleware):
#     """
#     专门用于在 Worker 进程启动时初始化插件系统的中间件
#     """
#     def before_worker_boot(self, broker, worker):
#         logger.info("⚙️ [Worker Boot] 正在为当前进程初始化 ScraperManager...")
#         try:
#             # 获取或创建事件循环来执行异步的 startup
#             try:
#                 loop = asyncio.get_event_loop()
#             except RuntimeError:
#                 loop = asyncio.new_event_loop()
#                 asyncio.set_event_loop(loop)
            
#             # 运行插件系统启动逻辑
#             loop.run_until_complete(scraper_manager.startup())
#             logger.info("✅ [Worker Boot] ScraperManager 进程初始化成功")
#         except Exception as e:
#             logger.error(f"❌ [Worker Boot] ScraperManager 初始化失败: {e}", exc_info=True)




# 全局配置
DEAD_LETTER_QUEUE = "dead_letter"  # 死信队列名称（统一存储所有重试失败的任务）
DEFAULT_MAX_RETRIES = 3  # 全局默认重试次数
DEFAULT_MIN_BACKOFF = 5000  # 重试最小间隔（毫秒）
DEFAULT_MAX_BACKOFF = 60000  # 重试最大间隔（毫秒）

_broker_instance = None


def get_broker() -> RedisBroker:
    global _broker_instance
    if _broker_instance is None:
        s = get_settings()
        
        # 实例化我们的自定义中间件
        # scraper_middleware = ScraperInitializerMiddleware()
        
        # 1. 初始化 Broker（保持你的配置）
        _broker_instance = RedisBroker(
            url=f"{s.REDIS_URL}/{s.REDIS_DB}",
            # 2. 配置核心中间件（移除 AsyncIO 相关，兼容 Dramatiq 2.0.0）
            middleware=[
                TimeLimit(time_limit=360000), 
                Retries(
                    max_retries=DEFAULT_MAX_RETRIES,
                    min_backoff=DEFAULT_MIN_BACKOFF,
                    max_backoff=DEFAULT_MAX_BACKOFF,
                     # 只对特定异常重试（可选，避免无意义重试）
                    retry_when=lambda e: isinstance(e, (ConnectionError, TimeoutError))
                ), 
                AsyncIO(),
                # 3. 将自定义中间件添加到列表末尾
                # scraper_middleware
                ]
        )

        # 声明所有队列（确保生产者和消费者都能识别）
        for queue in ["scan", "metadata", "persist", "delete", "localize"]:
            _broker_instance.declare_queue(queue)

        # 关键：全局注册 Broker，让所有 Actor 默认使用这个实例
        set_broker(_broker_instance)
    return _broker_instance

# 初始化时自动创建并注册 Broker（避免导入时未初始化）
broker = get_broker()

