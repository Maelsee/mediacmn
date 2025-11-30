#!/usr/bin/env python3
"""
统一任务执行器启动脚本

用于启动异步任务执行器，处理扫描和元数据任务队列
"""

import asyncio
import argparse
import logging
import signal
import sys
from typing import Optional
import os

# 彩色日志支持
try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    class ColoredFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': Fore.CYAN,
            'INFO': Fore.GREEN,
            'WARNING': Fore.YELLOW,
            'ERROR': Fore.RED,
            'CRITICAL': Fore.MAGENTA + Style.BRIGHT,
        }
        def format(self, record):
            log_color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
            return super().format(record)
    USE_COLOR = True
except ImportError:
    class ColoredFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': "\033[36m",
            'INFO': "\033[32m",
            'WARNING': "\033[33m",
            'ERROR': "\033[31m",
            'CRITICAL': "\033[35;1m",
        }
        def format(self, record):
            log_color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{log_color}{record.levelname}\033[0m"
            return super().format(record)
    USE_COLOR = True

os.makedirs('logs', exist_ok=True)

# 配置日志格式
log_format = (
    # "%(asctime)s | %(levelname)8s | %(name)30s | %(filename)20s:%(lineno)4d | %(message)s"
    "%(levelname)8s | %(filename)20s:%(lineno)4d | %(message)s"
)
date_format = "%Y-%m-%d %H:%M:%S"

# 创建格式化器
if USE_COLOR:
    console_formatter = ColoredFormatter(log_format, datefmt=date_format)
else:
    console_formatter = logging.Formatter(log_format, datefmt=date_format)

file_formatter = logging.Formatter(log_format, datefmt=date_format)

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 清除现有的处理器
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# 控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# 文件处理器
file_handler = logging.FileHandler('logs/task_executor.log', encoding='utf-8')
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

# 为关键模块设置日志级别
logging.getLogger('services.scraper.tmdb').setLevel(logging.INFO)
logging.getLogger('services.media.metadata_enricher').setLevel(logging.INFO)
logging.getLogger('services.task.unified_task_scheduler').setLevel(logging.INFO)
logging.getLogger('services.task.unified_task_executor').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


class TaskExecutorService:
    """任务执行器服务"""
    
    def __init__(self, worker_count: int = 2):
        self.worker_count = worker_count
        self.executor_manager: Optional['TaskExecutorManager'] = None
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """启动服务"""
        try:
            # 显示启动横幅
            self._print_banner()
            
            logger.info(f"🚀 启动任务执行器服务，工作进程数: {self.worker_count}")
            
            # 导入任务执行器管理器
            from services.task import get_task_executor_manager
            
            self.executor_manager = await get_task_executor_manager()
            
            # 启动执行器
            await self.executor_manager.start_executors(self.worker_count)
            
            logger.info("✅ 任务执行器服务启动完成")
            logger.info("📋 正在等待任务队列中的任务...")
            
            # 等待关闭信号
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"❌ 任务执行器服务启动失败: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """停止服务"""
        if self.executor_manager:
            logger.info("停止任务执行器服务")
            await self.executor_manager.stop_executors()
            logger.info("任务执行器服务已停止")
    
    def _print_banner(self):
        """打印启动横幅"""
        banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🎬 MediaCMN 任务执行器服务 🎬                             ║
║                                                                              ║
║  处理任务类型: 扫描任务 | 元数据获取 | 删除同步 | 文件处理                   ║
║  日志文件: logs/task_executor.log                                            ║
║  按 Ctrl+C 安全关闭服务                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
        """
        print(banner)
    
    def shutdown(self, signum: Optional[int] = None):
        """关闭服务"""
        if signum:
            logger.info(f"🛑 接收到信号 {signum}，开始关闭服务")
        else:
            logger.info("🛑 开始关闭服务")
        
        self._shutdown_event.set()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="统一任务执行器")
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=2,
        help="工作进程数 (默认: 2)"
    )
    parser.add_argument(
        "--log-level", "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)"
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # 创建服务
    service = TaskExecutorService(worker_count=args.workers)
    
    # 设置信号处理器
    def signal_handler(signum, frame):
        service.shutdown(signum)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 启动服务
        await service.start()
    except KeyboardInterrupt:
        logger.info("用户中断，正在关闭服务...")
        service.shutdown()
    except Exception as e:
        logger.error(f"服务运行错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 确保日志目录存在
    import os
    os.makedirs('logs', exist_ok=True)
    
    # 运行主函数
    asyncio.run(main())
