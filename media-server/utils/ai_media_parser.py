"""AI 路径解析器 - 当 GuessIt 置信度低时用 AI 兜底

使用阿里百炼 Qwen3.6-Flash 免费模型，通过 OpenAI 兼容接口调用。
"""
import asyncio
import hashlib
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个媒体文件路径解析器。分析文件路径，提取媒体元数据。

规则：
1. 从路径中识别标题、年份、季数、集数、类型
2. 文件夹名包含标题和季信息，文件名包含集信息
3. 忽略分辨率（1080p/4K）、编码（x265/HEVC）、字幕等技术标签
4. 只返回 JSON，不要其他文字
5. 无法确定的字段设为 null"""

USER_PROMPT_TEMPLATE = """路径: {file_path}

GuessIt 解析结果（可能有误）: {guessit}

返回 JSON：
{{"title": "标题", "year": null, "season": null, "episode": null, "type": "movie 或 tv_episode"}}"""


class AIMediaParser:
    """AI 路径解析器，用于 GuessIt 低置信度时的兜底解析"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    async def parse(self, file_path: str, guessit_result: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        用 AI 解析文件路径，提取媒体信息

        返回格式与 GuessIt 一致：{title, year, season, episode, type}
        返回 None 表示 AI 无法解析
        """
        cache_key = hashlib.md5(file_path.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            result = await self._call_ai(file_path, guessit_result)
            if result:
                self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"AI 路径解析失败: {e}")
            return None

    async def _call_ai(self, file_path: str, guessit_result: Optional[Dict]) -> Optional[Dict]:
        """调用阿里百炼 Qwen（OpenAI 兼容接口）解析路径"""
        from core.config import get_settings

        settings = get_settings()
        api_key = getattr(settings, 'DASHSCOPE_API_KEY', None)
        if not api_key:
            logger.warning("未配置 DASHSCOPE_API_KEY，跳过 AI 解析")
            return None

        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.warning("openai 库未安装，跳过 AI 解析")
            return None

        user_content = USER_PROMPT_TEMPLATE.format(
            file_path=file_path,
            guessit=json.dumps(guessit_result or {}, ensure_ascii=False),
        )

        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            response = await client.chat.completions.create(
                model="qwen3.6-flash",
                max_tokens=512,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )

            text = response.choices[0].message.content.strip()
            return self._parse_json_response(text)

        except json.JSONDecodeError:
            logger.warning(f"AI 返回非 JSON: {text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Qwen 调用失败: {e}")
            return None

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """从 AI 回复中提取 JSON"""
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                text = text[start:end + 1]

        result = json.loads(text)

        title = result.get("title")
        if not isinstance(title, str) or not title.strip():
            return None

        def _to_int(v):
            if v is None:
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        return {
            "title": title.strip(),
            "year": _to_int(result.get("year")),
            "season": _to_int(result.get("season")),
            "episode": _to_int(result.get("episode")),
            "type": result.get("type", "movie"),
            "source": "ai",
        }


# 全局实例
ai_media_parser = AIMediaParser()
