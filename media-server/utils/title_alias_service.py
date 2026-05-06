"""标题别名服务 - 管理中英文标题映射"""
import json
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class TitleAliasService:
    """标题别名服务，用于在搜索失败时尝试替代标题"""

    def __init__(self):
        self._aliases: dict[str, List[str]] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """懒加载别名表"""
        if self._loaded:
            return
        alias_file = Path(__file__).parent / "title_aliases.json"
        if alias_file.exists():
            try:
                with open(alias_file, "r", encoding="utf-8") as f:
                    self._aliases = json.load(f)
                self._loaded = True
                logger.info(f"加载别名表成功，共 {len(self._aliases)} 条映射")
            except Exception as e:
                logger.warning(f"加载别名表失败: {e}")

    def get_aliases(self, title: str) -> List[str]:
        """
        获取标题的别名列表（不包含原标题本身）

        支持正向和反向查找：
        - 正向：中文标题 -> 英文别名
        - 反向：英文标题 -> 中文别名
        """
        self._ensure_loaded()
        aliases: List[str] = []

        # 精确匹配正向映射
        if title in self._aliases:
            aliases.extend(self._aliases[title])

        # 反向映射：检查 title 是否在某个 key 的 values 中
        for key, values in self._aliases.items():
            if title in values and key not in aliases:
                aliases.append(key)

        return aliases


# 全局实例
title_alias_service = TitleAliasService()
