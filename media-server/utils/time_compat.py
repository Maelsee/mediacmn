"""
时间工具模块 - 处理Python 3.12+中datetime.utcnow的弃用问题
"""
from datetime import datetime, timezone
from typing import Callable


def get_utc_now() -> datetime:
    """
    获取当前UTC时间，兼容Python 3.12+
    
    Python 3.12+中datetime.utcnow()被弃用，推荐使用datetime.now(timezone.utc)
    此函数提供统一的兼容性接口
    
    Returns:
        datetime: 当前UTC时间
    """
    return datetime.now(timezone.utc)


def get_utc_now_factory() -> Callable[[], datetime]:
    """
    获取UTC时间工厂函数，用于SQLModel的default_factory
    
    Returns:
        Callable[[], datetime]: 返回当前UTC时间的函数
    """
    return get_utc_now