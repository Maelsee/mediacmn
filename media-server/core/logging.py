"""结构化日志配置。

使用标准 logging 并输出 JSON 结构，便于集中化采集。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from .config import Settings


class UvicornCompatibleFormatter(logging.Formatter):
    """与 Uvicorn 兼容的日志格式化器。

    使用与 Uvicorn 相同的格式：
    INFO:     2023-07-19 10:30:45,123 - logger.name - message
    """

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        # 使用与 Uvicorn 完全相同的格式
        levelname = record.levelname
        # Uvicorn 实际格式：INFO:     (冒号 + 5个空格，总共8个字符)
        levelname_part = f"{levelname}:"
        # 精确对齐：总共8个字符，冒号占1个，需要7个字符的宽度
        levelname_aligned = f"{levelname_part:<8}"
        
        # 获取当前时间并格式化为毫秒
        import datetime
        ct = datetime.datetime.fromtimestamp(record.created)
        time_str = ct.strftime("%Y-%m-%d %H:%M:%S") + f",{int(record.msecs):03d}"
        
        # 添加颜色支持（可选，与 Uvicorn 保持一致）
        import sys
        if sys.stderr.isatty():  # 如果在终端中运行
            if record.levelno >= logging.ERROR:
                levelname_aligned = f"\033[31m{levelname_aligned}\033[0m"  # 红色
            elif record.levelno >= logging.WARNING:
                levelname_aligned = f"\033[33m{levelname_aligned}\033[0m"  # 黄色
            elif record.levelno >= logging.INFO:
                levelname_aligned = f"\033[32m{levelname_aligned}\033[0m"  # 绿色
        
        # 构建与 Uvicorn 完全相同的格式
        # return f"{levelname_aligned} {time_str} - {record.name} - {record.getMessage()}"
        # 测试用，去掉时间和 logger 名称
        return f"{levelname_aligned}{record.getMessage()}"


logger = logging.getLogger("mediacmn")


def init_logging(settings: Settings) -> None:
    """初始化与 Uvicorn 兼容的日志输出。"""
    handler = logging.StreamHandler()
    handler.setFormatter(UvicornCompatibleFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO )