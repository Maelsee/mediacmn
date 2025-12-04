from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict


class ParserMode(str, Enum):
    LIGHT = "light"
    DEEP = "deep"


@dataclass
class ParseInput:
    filename_raw: str
    parent_hint: Optional[str] = None
    grandparent_hint: Optional[str] = None
    full_path: Optional[str] = None
    language_pref: str = "zh-CN"
    site_plugins: Optional[List[str]] = None
    


@dataclass
class ParseOutput:
    mode: ParserMode
    filename_normalized: Optional[str] = None
    extension: Optional[str] = None
    media_type_coarse: Optional[str] = None
    season_hint: Optional[int] = None
    episode_hint: Optional[int] = None
    year_hint: Optional[int] = None
    quality_tags: Optional[List[str]] = None
    parser_version: Optional[str] = None
    parser_confidence: Optional[int] = None
    name_hash: Optional[str] = None
    title: Optional[str] = None
    original_title: Optional[str] = None
    year: Optional[int] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    edition_tags: Optional[List[str]] = None
    resolution_tags: Optional[List[str]] = None
    aliases: Optional[List[str]] = None
    parser_version_final: Optional[str] = None
    confidence_final: Optional[int] = None
    parse_trace: Optional[Dict] = None


class FilenameParser:
    def __init__(self, version: str = "1.0.0"):
        self.version = version

    def parse(self, input: ParseInput, mode: ParserMode) -> ParseOutput:
        import re, os, unicodedata

        def norm(s: str) -> str:
            s = unicodedata.normalize('NFKD', s or '')
            s = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s)
            s = re.sub(r'[\[\]{}()]+', ' ', s)
            s = re.sub(r'[._\-]+', ' ', s)
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        fn = input.filename_raw or ''
        # 根据 full_path 自动补齐父/祖父目录线索
        if input.full_path and (not input.parent_hint or not input.grandparent_hint):
            try:
                parent = os.path.basename(os.path.dirname(input.full_path))
                grand = os.path.basename(os.path.dirname(os.path.dirname(input.full_path)))
                input.parent_hint = input.parent_hint or parent
                input.grandparent_hint = input.grandparent_hint or grand
            except Exception:
                pass
        base = os.path.splitext(fn)[0]
        normalized = norm(base)
        ext = os.path.splitext(fn)[1].lower().lstrip('.') or None

        media_type_coarse = None
        if ext in { 'mp4','mkv','avi','mov','wmv','flv','webm','m4v' }:
            media_type_coarse = 'video'
        elif ext in { 'mp3','flac','wav','aac','ogg','wma','m4a' }:
            media_type_coarse = 'audio'
        elif ext in { 'jpg','jpeg','png','gif','bmp','webp','tiff','svg' }:
            media_type_coarse = 'image'
        else:
            media_type_coarse = 'other'

        year_hint = None
        m_year = re.search(r'\b(19|20)\d{2}\b', normalized)
        if m_year:
            y = int(m_year.group(0))
            from datetime import datetime
            if 1900 <= y <= datetime.now().year + 2:
                year_hint = y

        res_tags = []
        for tag in ['2160p','4k','1080p','720p','480p']:
            if re.search(tag, normalized, re.IGNORECASE):
                res_tags.append(tag.lower())

        quality_tags = []
        for pat in ['web\s?-?dl','webrip','web','bluray','bdrip','brrip','dvd','dvdrip','hdtv','pdtv','h265','x265','hevc','h264','x264','ddp\d+(?:\.\d+)?','dts\d+(?:\.\d+)?','atmos']:
            if re.search(pat, normalized, re.IGNORECASE):
                quality_tags.append(pat)

        def season_episode_from_text(text: str):
            m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', text)
            if m:
                return int(m.group(1)), int(m.group(2))
            m = re.search(r'(\d{1,2})x(\d{1,3})', text)
            if m:
                return int(m.group(1)), int(m.group(2))
            m = re.search(r'第(\d{1,2})[季]', text)
            n = re.search(r'第(\d{1,3})[集话]', text)
            if m and n:
                return int(m.group(1)), int(n.group(1))
            return None, None

        season_hint, episode_hint = season_episode_from_text(normalized)
        if (season_hint is None or episode_hint is None) and input.parent_hint:
            ps, pe = season_episode_from_text(norm(input.parent_hint))
            season_hint = season_hint or ps
            episode_hint = episode_hint or pe

        if mode == ParserMode.LIGHT:
            score = 50
            if season_hint is not None and episode_hint is not None:
                score += 30
            elif season_hint is not None or episode_hint is not None:
                score += 20
            score += min(15, 5 * len(res_tags))
            parser_confidence = score
            return ParseOutput(
                mode=mode,
                filename_normalized=normalized,
                extension=ext,
                media_type_coarse=media_type_coarse,
                season_hint=season_hint,
                episode_hint=episode_hint,
                year_hint=year_hint,
                resolution_tags=res_tags,
                quality_tags=quality_tags,
                parser_version=self.version,
                parser_confidence=parser_confidence,
            )

        title_clean = normalized
        blacklist_tags = [
            r'\b(2160p|1080p|720p|480p|4k)\b',
            r'\b(web\s?-?dl|webrip|web)\b',
            r'\b(blu[-\s]?ray|bdrip|brrip)\b',
            r'\b(h265|x265|hevc|h264|x264)\b',
            r'\b(ddp[\d\.]+|dts[\d\.]+|atmos)\b',
            # 发行/平台/站点黑名单（常见）
            r'\b(iq|blacktv|pandaqt|panda)\b',
            r'\b(amzn|amazon|nf|netflix|disney\+|disney|appletv\+|appletv|paramount|hbo|max|hulu)\b',
            r'\b(remux|dvdrip|cam|ts|tc|r5)\b',
            r'\b(hdr|dolby\s?vision)\b',
            r'\b(hdr|dolby\s?vision|fps|60fps|120fps)\b',
            r'[Ss]\d{1,2}[Ee]\d{1,3}',
            r'第\d+[季集].*第\d+[集话]',
            r'\b\d+x\d+\b',
        ]
        for pat in blacklist_tags:
            title_clean = re.sub(pat, ' ', title_clean, flags=re.IGNORECASE)
        # 去除年份（不保留到标题）
        title_clean = re.sub(r'\b(19|20)\d{2}\b', ' ', title_clean)
        title_clean = re.sub(r'\b[a-zA-Z]\b', ' ', title_clean)
        # 简单分词，移除纯数字token（保留大于4位可能是年份的已在上一步清理）
        tokens = [t for t in re.split(r'\s+', title_clean) if t]
        tokens = [t for t in tokens if not re.fullmatch(r'\d{1,3}', t)]
        title_clean = ' '.join(tokens).strip()
        title_clean = re.sub(r'\s+', ' ', title_clean).strip()

        # 基于路径选择更可靠的剧名
        generic_dirs = {"test", "sample", "samples", "temp", "tmp", "下载", "新建文件夹"}
        def usable_dir(name: str) -> Optional[str]:
            n = norm(name)
            if not n:
                return None
            if n.lower() in generic_dirs:
                return None
            # 去除季/发布组标识
            n2 = re.sub(r'[Ss]\d{1,2}|第\d+季', ' ', n)
            n2 = re.sub(r'\b(iq|blacktv|pandaqt|panda|amzn|amazon|nf|netflix|disney\+|disney|appletv\+|appletv|paramount|hbo|max|hulu)\b', ' ', n2, flags=re.IGNORECASE)
            n2 = re.sub(r'\b(19|20)\d{2}\b', ' ', n2)
            n2 = re.sub(r'\s+', ' ', n2).strip()
            return n2 or None

        parent_title = usable_dir(input.parent_hint or '')
        grand_title = usable_dir(input.grandparent_hint or '')
        # 优先中文主标题（避免被英文与发布组污染）
        cn_parts = re.findall(r'[\u4e00-\u9fff]+', normalized)
        if cn_parts:
            title_clean = max(cn_parts, key=len)
        # 剧集场景：优先使用父/祖父目录作为剧名
        if season_hint is not None or episode_hint is not None:
            candidate = parent_title or grand_title
            if candidate:
                cn_cand = re.findall(r'[\u4e00-\u9fff]+', candidate)
                title_clean = (max(cn_cand, key=len) if cn_cand else candidate)
        # 兜底：若标题为空，使用父/祖父目录或规范化文件名
        if not title_clean:
            title_clean = parent_title or grand_title or normalized

        season_number = season_hint
        episode_number = episode_hint
        confidence_final = 70
        if season_number is not None and episode_number is not None:
            confidence_final += 10
        if input.parent_hint:
            confidence_final += 5

        # 解析发布组（如: ...-BlackTV）
        release_group = None
        try:
            base_name = os.path.splitext(fn)[0]
            m_rg = re.search(r'-(\w+)$', base_name)
            if m_rg:
                release_group = m_rg.group(1)
        except Exception:
            release_group = None

        # 构建别名与原始英文标题（在剧名前切掉季集与常见标签）
        aliases = []
        if parent_title and parent_title != title_clean:
            aliases.append(parent_title)
        if grand_title and grand_title not in aliases:
            aliases.append(grand_title)
        original_title = None
        try:
            eng_head = re.split(r'[Ss]\d{1,2}[Ee]\d{1,3}', normalized)[0]
            for pat in blacklist_tags:
                eng_head = re.sub(pat, ' ', eng_head, flags=re.IGNORECASE)
            eng_head = re.sub(r'\b(19|20)\d{2}\b', ' ', eng_head)
            eng_head = re.sub(r'\s+', ' ', eng_head).strip()
            original_title = eng_head or None
        except Exception:
            original_title = None

        edition_tags = []
        if release_group:
            edition_tags.append(release_group)

        return ParseOutput(
            mode=mode,
            filename_normalized=normalized,
            extension=ext,
            media_type_coarse=media_type_coarse,
            year=year_hint,
            season_number=season_number,
            episode_number=episode_number,
            resolution_tags=res_tags,
            quality_tags=quality_tags,
            title=title_clean or normalized,
            original_title=original_title,
            edition_tags=edition_tags or None,
            aliases=aliases or None,
            parser_version_final=self.version,
            confidence_final=confidence_final,
            parse_trace={
                'used_parent_hint': bool(input.parent_hint),
                'res_tags': res_tags,
                'quality_tags': quality_tags
            }
        )