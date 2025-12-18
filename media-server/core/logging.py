"""结构化日志配置。

使用标准 logging 并输出 JSON 结构，便于集中化采集。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

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


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        data: Dict[str, Any] = {
            "ts": int(record.created * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)  # type: ignore[arg-type]
        if record.stack_info:
            data["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(data, ensure_ascii=False)


logger = logging.getLogger("mediacmn")


def init_logging(settings: Settings) -> None:
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(UvicornCompatibleFormatter())

    app_file_handler = TimedRotatingFileHandler(
        filename=str(log_dir / "app.log"),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(app_file_handler)
    root.setLevel(logging.INFO)

    dramatiq_logger = logging.getLogger("dramatiq")
    dramatiq_file_handler = TimedRotatingFileHandler(
        filename=str(log_dir / "dramatiq.log"),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    dramatiq_file_handler.setFormatter(JSONFormatter())
    dramatiq_logger.handlers.clear()
    dramatiq_logger.addHandler(dramatiq_file_handler)
    dramatiq_logger.setLevel(logging.INFO)
    dramatiq_logger.propagate = False
