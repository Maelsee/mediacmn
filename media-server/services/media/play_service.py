"""播放相关服务

从 media_service.py 拆出的播放 URL 组装、字幕列表、剧集列表等方法。
"""
from __future__ import annotations

import base64
from typing import Optional, Dict, Any, List

from sqlmodel import select, and_
from sqlmodel.ext.asyncio.session import AsyncSession

import logging
logger = logging.getLogger(__name__)

from models.media_models import MediaCore, FileAsset, MediaVersion, EpisodeExt
from models.storage_models import StorageConfig, WebdavStorageConfig
from services.storage.storage_service import storage_service


class PlayService:
    """播放相关服务"""

    def __init__(self, media_service):
        """
        参数:
            media_service: MediaService 实例，用于访问 _to_human_size、_get_storage_info 等辅助方法
        """
        self._ms = media_service

    async def get_file_subtitles(
        self,
        db: AsyncSession,
        user_id: int,
        asset: FileAsset,
    ) -> Dict[str, Any]:
        """获取文件关联的字幕列表"""
        subtitles: List[Dict[str, Any]] = []
        if not asset.storage_id or not asset.full_path:
            return {"file_id": asset.id, "items": subtitles}

        path = asset.full_path
        parent_path = "/"
        try:
            normalized = path.replace("\\", "/")
            if "/" in normalized:
                parent_path = normalized.rsplit("/", 1)[0] or "/"
        except Exception:
            parent_path = "/"

        source_type = None
        base_url = None
        headers: Optional[Dict[str, str]] = None
        try:
            sc = (
                await db.exec(
                    select(StorageConfig).where(
                        StorageConfig.id == asset.storage_id
                    )
                )
            ).first()
            source_type = getattr(sc, "storage_type", None)
            if source_type == "webdav" and sc:
                wc = (
                    await db.exec(
                        select(WebdavStorageConfig).where(
                            WebdavStorageConfig.storage_config_id == sc.id
                        )
                    )
                ).first()
                head = (getattr(wc, "hostname", "") or "").rstrip("/") if wc else ""
                try:
                    if head.startswith("`") and head.endswith("`"):
                        head = head[1:-1].strip()
                except Exception:
                    pass
                base_url = head or None

                try:
                    if (
                        wc
                        and getattr(wc, "login", None)
                        and getattr(wc, "password", None)
                    ):
                        token = base64.b64encode(
                            f"{wc.login}:{wc.password}".encode("utf-8")
                        ).decode("utf-8")
                        headers = {"Authorization": f"Basic {token}"}
                except Exception:
                    headers = None
        except Exception:
            base_url = None
            headers = None

        try:
            entries = await storage_service.list_directory(
                asset.storage_id, parent_path, depth=1
            )
        except Exception:
            entries = []

        exts = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
        logger.info(f"扫描列表结果{entries}")
        for entry in entries:
            if entry.is_dir:
                continue
            name = entry.name or ""
            lower = name.lower()
            matched = False
            for ext in exts:
                if lower.endswith(ext):
                    matched = True
                    break
            if not matched:
                continue

            size_text = self._ms._to_human_size(entry.size) if entry.size else None
            language = None
            try:
                parts = name.rsplit(".", 2)
                if len(parts) == 3:
                    language = parts[1]
            except Exception:
                language = None

            url = None
            if base_url:
                sub_path = entry.path or ""
                try:
                    if sub_path.startswith("`") and sub_path.endswith("`"):
                        sub_path = sub_path[1:-1].strip()
                except Exception:
                    pass
                sub_path = "/" + sub_path.lstrip("/")
                try:
                    from urllib.parse import quote
                    sub_path = quote(sub_path, safe="/") if sub_path else sub_path
                except Exception:
                    pass
                if sub_path:
                    url = f"{base_url}{sub_path}"

            subtitles.append(
                {
                    "id": entry.path,
                    "name": name,
                    "path": entry.path,
                    "size": entry.size,
                    "size_text": size_text,
                    "language": language,
                    "url": url,
                    "headers": headers,
                    "storage_type": source_type,
                }
            )

        return {"file_id": asset.id, "items": subtitles}

    async def download_subtitle_content(
        self,
        db: AsyncSession,
        user_id: int,
        asset: FileAsset,
        subtitle_path: str,
    ) -> str:
        """下载字幕文件内容"""
        if not asset.storage_id or not subtitle_path:
            raise ValueError("字幕路径或存储配置无效")

        storage_id = asset.storage_id

        client = await storage_service.get_client(storage_id)
        async with client:
            try:
                from services.storage.storage_client import StoragePermissionError, StorageNotFoundError
            except Exception:
                StoragePermissionError = Exception
                StorageNotFoundError = Exception

            try:
                chunks = []
                async for chunk in client.download_iter(subtitle_path, 64 * 1024):
                    chunks.append(chunk)
                data = b"".join(chunks)
            except StorageNotFoundError as e:
                logger.error(f"字幕文件不存在: {subtitle_path} - {e}")
                raise
            except StoragePermissionError as e:
                logger.error(f"读取字幕权限不足: {subtitle_path} - {e}")
                raise

        text: str
        try:
            text = data.decode("utf-8")
        except Exception:
            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception:
                text = data.decode("latin-1", errors="ignore")

        return text

    async def get_file_episode_list(
        self,
        db: AsyncSession,
        user_id: int,
        asset: FileAsset,
    ) -> Dict[str, Any]:
        """获取文件所属季版本的剧集列表"""
        if not asset.season_version_id:
            return {"file_id": asset.id, "season_version_id": None, "episodes": []}

        season_version_id = asset.season_version_id

        season_version = (
            await db.exec(
                select(MediaVersion).where(
                    and_(
                        MediaVersion.id == season_version_id,
                        MediaVersion.user_id == user_id,
                    )
                )
            )
        ).first()
        if not season_version:
            return {"file_id": asset.id, "season_version_id": None, "episodes": []}

        episode_versions = (
            await db.exec(
                select(MediaVersion).where(
                    and_(
                        MediaVersion.user_id == user_id,
                        MediaVersion.parent_version_id == season_version_id,
                        MediaVersion.scope == "episode_child",
                    )
                )
            )
        ).all()
        if not episode_versions:
            return {
                "file_id": asset.id,
                "season_version_id": season_version_id,
                "episodes": [],
            }

        ep_version_ids = [v.id for v in episode_versions]

        episode_cores = (
            await db.exec(
                select(MediaCore, EpisodeExt)
                .join(EpisodeExt, EpisodeExt.core_id == MediaCore.id)
                .where(
                    and_(
                        MediaCore.user_id == user_id,
                        MediaCore.id.in_([v.core_id for v in episode_versions]),
                    )
                )
            )
        ).all()
        core_map = {c.id: (c, e) for c, e in episode_cores}

        assets = (
            await db.exec(
                select(FileAsset).where(
                    and_(
                        FileAsset.user_id == user_id,
                        FileAsset.version_id.in_(ep_version_ids),
                        FileAsset.season_version_id == season_version_id,
                    )
                )
            )
        ).all()

        assets_by_version: Dict[int, List[FileAsset]] = {}
        for a in assets:
            assets_by_version.setdefault(a.version_id, []).append(a)

        episodes: List[Dict[str, Any]] = []
        for v in episode_versions:
            core_ext = core_map.get(v.core_id)
            if not core_ext:
                continue
            core, ext = core_ext
            current_assets = assets_by_version.get(v.id, [])
            asset_items: List[Dict[str, Any]] = []
            for fa in current_assets:
                asset_items.append(
                    {
                        "file_id": fa.id,
                        "path": fa.full_path,
                        "size": fa.size,
                        "size_text": self._ms._to_human_size(fa.size),
                        "language": getattr(fa, "language", None),
                    }
                )
            episodes.append(
                {
                    "id": core.id,
                    "episode_number": ext.episode_number,
                    "title": core.title,
                    "still_path": getattr(ext, "still_path", None),
                    "assets": asset_items,
                }
            )

        episodes.sort(key=lambda x: x["episode_number"])

        return {
            "file_id": asset.id,
            "season_version_id": season_version_id,
            "episodes": episodes,
        }
