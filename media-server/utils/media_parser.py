import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from guessit import guessit

class MediaParser:
    """
    封装的媒体文件名称解析器。
    解决中文环境、路径干扰、非标准命名（第X话）等问题。
    """
    def __init__(self, custom_config_path=None):
        """
        初始化解析器。
        :param custom_config_path: 可选，指定自定义的 options.json 路径。
                                如果不传，默认使用 utils/options.json
        """
        self.config_path: Optional[Path] = None
        if custom_config_path:
            p = Path(custom_config_path)
            if p.exists():
                self.config_path = p
        if self.config_path is None:
            default_path = Path(__file__).resolve().parent / "options.json"
            if default_path.exists():
                self.config_path = default_path

        self._ignore_dir_names = {
            "dav",
            "综艺",
            "动画",
            "电影",
            "剧集",
            "电视剧",
            "外语",
            "华语",
        }

        self._ignore_title_tokens = {
            "高清",
            "sd",
            "sdr",
            "hdr",
            "webrip",
            "webdl",
            "web-dl",
            "bluray",
            "bdrip",
            "x265",
            "h265",
            "hevc",
            "x264",
            "h264",
            "aac",
            "ddp",
            "dd",
            "ac3",
            "eac3",
            "mp4",
            "mkv",
            "avi",
            "1080p",
            "2160p",
            "720p",
            "4k",
        }

    def should_force_episode(self, filepath: str) -> bool:
        """根据路径与文件名快速判断是否应强制按剧集解析。"""
        s = str(filepath)
        if re.search(r"S\d{1,2}E\d{1,4}", s, flags=re.IGNORECASE):
            return True
        if re.search(r"第\s*\d+\s*[话集]", s):
            return True
        if re.search(r"\bE\d{1,4}\b", s, flags=re.IGNORECASE):
            return True
        parts = re.split(r"[\\/]+", s)
        for p in parts:
            if p.lower() in ("动画","anime", "综艺","variety", "剧集","tv", "电视剧"):
                return True
        return False

    def _guessit_options(self, strict_episode: bool, expected_title: Optional[str]) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "no_user_config": True,
            "single_value": True,
            "name_only": True,
        }
        if self.config_path:
            options["config"] = [str(self.config_path)]
        if strict_episode:
            options["type"] = "episode"
            options["episode_prefer_number"] = True
        if expected_title:
            options["expected_title"] = [expected_title]
        return options

    def _is_ignorable_segment(self, segment: str) -> bool:
        if not segment:
            return True
        s = segment.strip()
        if not s:
            return True

        norm = s.lower()
        if norm in self._ignore_dir_names or norm in self._ignore_title_tokens:
            return True

        if s in self._ignore_dir_names:
            return True
        if re.fullmatch(r"\d+", s):
            return True
        if re.fullmatch(r"\d+[~-]\d+", s):
            return True
        if re.fullmatch(r"S\d{1,2}", s, flags=re.IGNORECASE):
            return True
        if re.fullmatch(r"Season\s*\d+", s, flags=re.IGNORECASE):
            return True
        if re.fullmatch(r"第\s*\d+\s*季", s):
            return True
        if re.fullmatch(r"第\s*\d+\s*季\s*\d+\s*集", s):
            return True
        if re.fullmatch(r"\d+[~-]\d+.*", s):
            return True
        if re.fullmatch(r"\d{3,4}p", s, flags=re.IGNORECASE):
            return True
        return False

    def _extract_title_hint(self, filepath: str) -> Optional[str]:
        path = str(filepath)
        parts = [p for p in re.split(r"[\\/]+", path) if p]
        if len(parts) >= 2:
            for seg in reversed(parts[:-1]):
                seg = seg.strip()
                if self._is_ignorable_segment(seg):
                    continue
                cleaned = seg
                m = re.search(r"([\u4e00-\u9fffA-Za-z0-9·\s]+)[(（](?:19|20)\d{2}[)）]", cleaned)
                if m:
                    cleaned = m.group(1).strip()

                cn_parts = re.findall(r"[\u4e00-\u9fff]{2,}", cleaned)
                if cn_parts:
                    cleaned = max(cn_parts, key=len)

                if re.search(r"[\u4e00-\u9fff]", cleaned):
                    return cleaned
                if re.search(r"[A-Za-z]", cleaned) and len(cleaned) >= 2:
                    return cleaned

        name = os.path.basename(path)
        base = re.sub(r"\.[^.]+$", "", name)
        candidates = re.findall(r"[\u4e00-\u9fff]{2,}", base)
        if candidates:
            candidates.sort(key=len, reverse=True)
            return candidates[0]
        return None

    def _extract_season_episode_hints(self, filepath: str) -> Tuple[Optional[int], Optional[int]]:
        s = str(filepath)

        m = re.search(r"S(?P<s>\d{1,2})E(?P<e>\d{1,4})", s, flags=re.IGNORECASE)
        if m:
            return int(m.group("s")), int(m.group("e"))

        m = re.search(r"第\s*(?P<s>\d+)\s*季", s)
        season = int(m.group("s")) if m else None

        m = re.search(r"第\s*(?P<e>\d+)\s*[话集]", s)
        episode = int(m.group("e")) if m else None

        if episode is None:
            m = re.search(r"\bE(?P<e>\d{1,4})\b", s, flags=re.IGNORECASE)
            if m:
                episode = int(m.group("e"))

        if season is None:
            m = re.search(r"S(?P<s>\d{1,2})(?!\d)", s, flags=re.IGNORECASE)
            if m:
                season = int(m.group("s"))

        return season, episode

    def _extract_year_hint_from_path(self, filepath: str) -> Optional[int]:
        s = str(filepath)
        years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", s)]
        if not years:
            return None
        for y in reversed(years):
            if 1900 <= y <= 2100:
                return y
        return None

    def _preprocess_name(self, raw_name):
        """
        内部方法：对文件名进行清洗和标准化。
        解决：dav.302...前缀、101~200干扰、第149话格式不标准等问题。
        """
        filename = os.path.basename(str(raw_name))
        ext = ""
        if "." in filename:
            base, ext = filename.rsplit(".", 1)
            ext = "." + ext
        else:
            base = filename

        base = re.sub(r"\d+~\d+", " ", base)
        base = re.sub(r"\(高清SDR\)", " SDR ", base)
        base = re.sub(r"\b\d+\s*Audios?\b", " ", base, flags=re.IGNORECASE)

        base = re.sub(r"第\s*(\d+)\s*季", lambda m: f"S{int(m.group(1)):02d}", base)
        base = re.sub(r"第\s*(\d+)\s*[话集]", lambda m: f"E{int(m.group(1))}", base)
        base = re.sub(r"第\s*(\d+)\s*期", lambda m: f"E{int(m.group(1))}", base)

        base = re.sub(r"\s+", " ", base).strip()
        return base + ext

    def parse(self, filepath, strict_episode=False):
        """
        主解析函数。
        :param filepath: 文件路径或文件名。
        :param strict_episode: 是否强制按“剧集”模式解析。
                                     如果为 True，即使没有 S 标记，也会尝试提取 season/episode，
                                     并且默认 season 为 1。
        :return: 解析后的字典 (GuessIt 格式)
        """
        raw_path = str(filepath)
        season_hint, episode_hint = self._extract_season_episode_hints(raw_path)
        title_hint = self._extract_title_hint(raw_path)
        year_hint = self._extract_year_hint_from_path(raw_path)
        clean_name = self._preprocess_name(raw_path)

        if title_hint and title_hint in clean_name:
            if "." in clean_name:
                tokens = [t for t in clean_name.split(".") if t]
                idx = None
                for i, t in enumerate(tokens):
                    if title_hint in t:
                        idx = i
                        break
                if idx is not None and idx > 0:
                    clean_name = ".".join(tokens[idx:])

        if title_hint and title_hint not in clean_name:
            clean_name = f"{title_hint}.{clean_name}"

        options = self._guessit_options(strict_episode, title_hint)
        try:
            info = dict(guessit(clean_name, options))
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                "GuessIt 解析失败，降级为默认配置",
                extra={
                    "error": str(e),
                    "clean_name": clean_name,
                    "config_path": str(self.config_path) if self.config_path else None,
                },
            )
            fallback_options = {k: v for k, v in options.items() if k != "config"}
            try:
                info = dict(guessit(clean_name, fallback_options))
            except Exception as e2:
                logger.error(
                    "GuessIt 在默认配置下仍然失败，返回空结果",
                    extra={"error": str(e2), "clean_name": clean_name},
                )
                info = {}

        if strict_episode:
            if info.get("type") != "episode":
                info["type"] = "episode"
            if season_hint is not None:
                info["season"] = season_hint or 1
            elif not info.get("season") or info.get("season") == 0:
                info["season"] = 1
            if info.get("episode") is None and episode_hint is not None:
                info["episode"] = episode_hint

        if year_hint is not None and not info.get("year"):
            info["year"] = year_hint

        season_val = info.get("season")
        if season_val is not None and isinstance(season_val, int) and season_val >= 1900:
            info["season"] = season_hint or 1

        if title_hint:
            title = info.get("title")
            if not title:
                info["title"] = title_hint
            else:
                t = str(title).strip()
                if t.lower() in self._ignore_title_tokens:
                    info["title"] = title_hint

        title_final = info.get("title")
        if title_final:
            cn_parts_final = re.findall(r"[\u4e00-\u9fff]{2,}", str(title_final))
            if cn_parts_final:
                info["title"] = max(cn_parts_final, key=len)

        texts = []
        ep_title = info.get("episode_title")
        if isinstance(ep_title, str) and ep_title:
            texts.append(ep_title)
        base_name = os.path.basename(raw_path)
        if base_name:
            texts.append(base_name)
        texts.append(raw_path)

        if info.get("episode") is None:
            for text in texts:
                m = re.search(r"第\s*(\d+)\s*期", text)
                if m:
                    info["episode"] = int(m.group(1))
                    break
            if info.get("episode") is None:
                for text in texts:
                    m = re.search(r"第\s*(\d+)\s*[话集]", text)
                    if m:
                        info["episode"] = int(m.group(1))
                        break

        part = info.get("part")
        if part is None:
            for text in texts:
                m = re.search(r"[Pp]art\s*(\d+)", text)
                if m:
                    part = int(m.group(1))
                    break
        if part is None and "综艺" in raw_path:
            for text in texts:
                if re.search(r"第\s*\d+\s*期上", text):
                    part = 1
                    break
                if re.search(r"第\s*\d+\s*期中", text):
                    part = 2
                    break
                if re.search(r"第\s*\d+\s*期下", text):
                    part = 3
                    break

        if part is not None:
            info["part"] = part

        return info
media_parser = MediaParser()
