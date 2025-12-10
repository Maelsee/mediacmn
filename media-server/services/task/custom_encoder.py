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
        # 其他类型沿用默认序列化逻辑（如 dict、int、str 等）
        return super().default(obj)