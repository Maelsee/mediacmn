# 导入必要依赖（若已导入可跳过）
import json
from enum import Enum
from typing import Any

# 自定义 JSON 编码器：处理 Enum 类型
class DramatiqCustomEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        # 关键：若对象是 Enum 类型（如 ArtworkType），返回其 value 属性（字符串）
        if isinstance(obj, Enum):
            return obj.value
        
        # 处理具有 magnitude 和 units 的对象（BitRate, FrameRate, Size 等）
        if hasattr(obj, 'magnitude') and hasattr(obj, 'units'):
            return f"{obj.magnitude}{obj.units}"  # 返回 "数值+单位" 格式
        
        # 处理 Duration 对象（常见结构）
        if hasattr(obj, 'total_seconds'):
            return obj.total_seconds  # 返回总秒数
        
        # 处理其他自定义对象（使用 __dict__）
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        
        # 处理可字符串化的对象
        try:
            return str(obj)
        except:
            pass
        # 其他类型沿用默认序列化逻辑（如 dict、int、str 等）

        return super().default(obj)