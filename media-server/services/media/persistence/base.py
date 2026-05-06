"""持久化服务基础工具

提供 _DictWrapper、_get_attr、_parse_dt 等公共辅助函数。
"""
from __future__ import annotations

import hashlib
import os
import random
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from models.media_models import FileAsset, MediaCore, MediaVersion
from models.storage_models import StorageConfig


class _DictWrapper:
    """包装器，使 dict 可以通过 getattr 访问，并递归处理嵌套结构"""
    def __init__(self, data: Dict):
        self._data = data if isinstance(data, dict) else {}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        value = self._data.get(name)
        return self._wrap_value(value)

    def __getitem__(self, index: int):
        """支持列表索引访问"""
        if isinstance(self._data, list):
            return self._wrap_value(self._data[index])
        raise TypeError(f"'{type(self).__name__}' object is not subscriptable")

    def _wrap_value(self, value):
        """递归包装嵌套的 dict 和 list"""
        if isinstance(value, dict):
            return _DictWrapper(value)
        elif isinstance(value, list):
            return [self._wrap_value(item) for item in value]
        else:
            return value


def _get_attr(obj, key: str, default=None):
    """
    统一的属性访问方法，同时支持 dict 和 dataclass 对象
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    else:
        return getattr(obj, key, default)


def _parse_dt(v) -> tuple[Optional[datetime], Optional[int]]:
    """
    将日期值解析为 datetime 对象
    返回: (datetime, year) 或 (None, None)
    """
    if not v:
        return None, None
    try:
        from datetime import datetime as _dt
        if isinstance(v, _dt):
            return v, v.year
        if isinstance(v, str) and v:
            return _dt.strptime(v[:10], "%Y-%m-%d"), _dt.strptime(v[:10], "%Y-%m-%d").year
    except Exception:
        return None, None
    return None, None


def _get_version_tags_and_fingerprint(
    media_file: FileAsset, core: MediaCore, scope: str
) -> tuple[str, str]:
    """生成版本标签与指纹"""
    file_full_path = media_file.full_path or "unknown"
    filesize = media_file.size or 0
    filename_hash = hashlib.sha256(file_full_path.encode("utf-8")).hexdigest()[:16]
    tags = f"{scope}_{core.id}_{filename_hash}_{filesize}"
    fingerprint_str = f"{file_full_path}_{filesize}_{core.id}_{media_file.user_id}"
    fingerprint_str_hash = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()
    return tags, fingerprint_str_hash


def _get_quality_level(media_file: FileAsset) -> Optional[str]:
    """根据分辨率映射质量"""
    resolution = media_file.resolution or None
    example = ["4k", "2160p", "1080p"]
    return resolution if resolution else example[random.randint(0, len(example) - 1)]


def _get_file_source(session: Session, media_file: FileAsset) -> str:
    """文件来源存储类型（从存储配置中提取）"""
    import logging
    logger = logging.getLogger(__name__)

    storage_id = media_file.storage_id
    storage_type = None
    try:
        sc = session.exec(select(StorageConfig).where(StorageConfig.id == storage_id)).first() if storage_id else None
        storage_type = getattr(sc, 'storage_type', None)
    except Exception as e:
        logger.error(f"获取存储配置失败：{str(e)}")
        storage_type = None
    return storage_type or "unknown"


def _get_season_version_path(media_file: FileAsset) -> str:
    """提取单集文件的父文件夹路径作为季版本的唯一标识"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        full_path = os.path.abspath(media_file.full_path)
        parent_dir = os.path.dirname(full_path)
        return parent_dir.replace("\\", "/")
    except Exception as e:
        logger.error(f"提取父文件夹路径失败：{str(e)}", exc_info=True)
        return f"default_season_path_{media_file.filename}"


def _generate_season_version_tags(season_version_path: str, season_core: MediaCore) -> str:
    """生成季版本的标签"""
    path_hash = hashlib.sha256(season_version_path.encode("utf-8")).hexdigest()[:16]
    return f"season_group_{season_core.id}_{path_hash}"
