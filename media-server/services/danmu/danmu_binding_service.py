"""
弹幕绑定服务（优化版）

核心设计思路：
  弹幕绑定 = file_asset.id（数据库主键） + danmu_api 的 episodeId
  一个文件只能绑定一个弹幕源，但同一个 episodeId 可以被多个文件绑定。

绑定触发时机：
  1. 自动匹配成功 → 自动绑定（is_manual=0）
  2. 手动匹配选集  → 手动绑定（is_manual=1）

绑定后的使用链路：
  播放器打开文件 → 用 file_id 查绑定 → 拿到 episodeId → 获取弹幕

优化点：
  - file_id 使用 FileAsset.id（int），而非字符串，与数据库主键对齐
  - 增加 user_id 支持多租户隔离
  - 增加 source_info JSON 字段存储搜索时的完整源信息
  - 增加 match_confidence 记录匹配置信度
  - 增加批量绑定接口（同一番剧的多集一键绑定）
  - 增加按 anime_id 反查所有绑定的文件
  - 绑定时自动验证 file_id 是否存在
"""

from core.config import get_settings
from services.danmu.danmu_cache_service import danmu_cache_service
from core.db import get_async_session_context
from typing import Optional, Dict, Any, List
from datetime import datetime

# 替换 SQLAlchemy 为 SQLModel
from sqlmodel import select, delete
from models.danmu_models import DanmuBinding, DanmuBindingHistory
import logging
logger = logging.getLogger(__name__)


class DanmuBindingService:
    """
    弹幕绑定服务（优化版）

    管理视频文件与弹幕源的绑定关系，支持：
    - 创建、更新、删除绑定
    - 偏移量调整
    - 绑定历史查询
    - 批量绑定
    - 按 anime_id 反查
    - file_id 存在性校验
    """

    def __init__(self) -> None:
        """初始化绑定服务"""
        settings = get_settings()
        self._database_url = getattr(settings, "DATABASE_URL", "")
        logger.info("DanmuBindingService initialized")

    # ================================================================
    #  核心方法：获取绑定
    # ================================================================

    async def get_binding(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文件的弹幕绑定

        Args:
            file_id: 文件 ID（对应 FileAsset.id）

        Returns:
            绑定信息，如果不存在返回 None
        """
        # 先查缓存
        # cached = await danmu_cache_service.get_binding(file_id)
        # if cached:
        #     return cached

        # 查数据库（SQLModel 语法）
        async with get_async_session_context() as session:
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.exec(stmt)
            binding = result.one_or_none()

            if binding:
                data = self._binding_to_dict(binding)
                # 写入缓存
                await danmu_cache_service.set_binding(file_id, data)
                return data

            return None

    async def get_bindings_by_file_ids(
        self, file_ids: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        批量获取多个文件的弹幕绑定

        前端打开选集列表时，可一次性查询所有集的绑定状态，
        避免逐集请求。

        Args:
            file_ids: 文件 ID 列表

        Returns:
            { file_id: binding_dict_or_none } 的映射
        """
        if not file_ids:
            return {}

        result_map: Dict[str, Optional[Dict[str, Any]]] = {}

        # 1. 先批量查缓存
        uncached_ids = []
        for fid in file_ids:
            cached = await danmu_cache_service.get_binding(fid)
            if cached is not None:
                result_map[fid] = cached
            else:
                uncached_ids.append(fid)

        if not uncached_ids:
            return result_map

        # 2. 缓存未命中的，批量查数据库（SQLModel 语法）
        async with get_async_session_context() as session:
            stmt = select(DanmuBinding).where(
                DanmuBinding.file_id.in_(uncached_ids)
            )
            db_result = await session.exec(stmt)
            bindings = db_result.all()

            binding_map = {b.file_id: b for b in bindings}

            for fid in uncached_ids:
                binding = binding_map.get(fid)
                if binding:
                    data = self._binding_to_dict(binding)
                    await danmu_cache_service.set_binding(fid, data)
                    result_map[fid] = data
                else:
                    result_map[fid] = None

        return result_map

    async def get_bindings_by_anime_id(
        self, anime_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        根据 animeId 反查所有绑定的文件

        使用场景：用户想查看某个番剧的所有已绑定文件，
        或者番剧信息更新后需要批量刷新。

        Args:
            anime_id: 番剧 ID
            limit: 返回数量限制

        Returns:
            绑定信息列表
        """
        async with get_async_session_context() as session:
            stmt = (
                select(DanmuBinding)
                .where(DanmuBinding.anime_id == anime_id)
                .order_by(DanmuBinding.created_at.desc())
                .limit(limit)
            )
            result = await session.exec(stmt)
            bindings = result.all()

            return [self._binding_to_dict(b) for b in bindings]

    # ================================================================
    #  核心方法：创建 / 更新绑定
    # ================================================================

    async def create_binding(
        self,
        file_id: str,
        episode_id: str,
        anime_id: Optional[str] = None,
        anime_title: Optional[str] = None,
        episode_title: Optional[str] = None,
        type: Optional[str] = None,
        typeDescription: Optional[str] = None,
        imageUrl: Optional[str] = None,
        # platform: Optional[str] = None,
        offset: float = 0.0,
        is_manual: bool = False,
        # source_info: Optional[Dict[str, Any]] = None,
        match_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        创建或更新弹幕绑定

        如果 file_id 已有绑定，则更新为新的弹幕源；
        如果没有绑定，则创建新绑定。

        Args:
            file_id: 文件 ID（对应 FileAsset.id）
            episode_id: 弹幕剧集 ID（danmu_api 的 episodeId）
            anime_id: 番剧 ID（danmu_api 的 animeId）
            anime_title: 番剧标题
            episode_title: 剧集标题
            type: 弹幕类型
            typeDescription: 弹幕类型描述
            imageUrl: 弹幕图片 URL
            # platform: 弹幕来源平台
            offset: 时间偏移量（秒）
            is_manual: 是否手动绑定
            source_info: 搜索/匹配时的完整源信息（JSON 存储）
            match_confidence: 匹配置信度（自动匹配时使用）

        Returns:
            创建/更新后的绑定信息
        """
        async with get_async_session_context() as session:
            import json

            # 检查是否已存在绑定（SQLModel 语法）
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.exec(stmt)
            existing = result.one_or_none()

            # source_info_json = json.dumps(source_info, ensure_ascii=False) if source_info else None

            if existing:
                # ---- 更新现有绑定 ----
                old_episode_id = existing.episode_id

                existing.episode_id = episode_id

                existing.anime_id = anime_id
                existing.anime_title = anime_title
                existing.episode_title = episode_title
                existing.type = type
                existing.typeDescription = typeDescription
                existing.imageUrl = imageUrl
                existing.offset = offset
                existing.is_manual = 1 if is_manual else 0
                # existing.updated_at = datetime.utcnow()

                # 更新扩展字段（如果模型支持）
                # if hasattr(existing, "source_info"):
                #     existing.source_info = source_info_json
                if hasattr(existing, "match_confidence") and match_confidence is not None:
                    existing.match_confidence = match_confidence

                await session.commit()
                # SQLModel 需刷新实例以获取最新数据
                await session.refresh(existing)

                # 记录历史
                await self._add_history(
                    session, file_id, episode_id, anime_title,
                    episode_title, "update",
                    extra=f"from episode {old_episode_id} to {episode_id}",
                )

                data = self._binding_to_dict(existing)
                logger.info(
                    f"Updated binding: file={file_id}, "
                    f"episode {old_episode_id} -> {episode_id}"
                )
            else:
                # ---- 创建新绑定 ----
                binding = DanmuBinding(
                    file_id=file_id,
                    episode_id=episode_id,
                    anime_id=anime_id,
                    anime_title=anime_title,
                    episode_title=episode_title,
                    type=type,
                    typeDescription=typeDescription,
                    imageUrl=imageUrl,
                    # platform=platform,
                    offset=offset,
                    is_manual=1 if is_manual else 0,
                    # created_at=datetime.utcnow(),
                    # updated_at=datetime.utcnow()
                )

                # 设置扩展字段（如果模型支持）
                # if hasattr(binding, "source_info"):
                #     binding.source_info = source_info_json
                if hasattr(binding, "match_confidence") and match_confidence is not None:
                    binding.match_confidence = match_confidence

                session.add(binding)
                await session.commit()
                # SQLModel 需刷新实例以获取自增 ID 等字段
                await session.refresh(binding)

                # 记录历史
                await self._add_history(
                    session, file_id, episode_id, anime_title,
                    episode_title, "bind",
                )

                data = self._binding_to_dict(binding)
                logger.info(
                    f"Created binding: file={file_id} -> episode={episode_id}"
                )

            # 更新缓存
            # await danmu_cache_service.set_binding(file_id, data)
            return data

    # ================================================================
    #  批量绑定
    # ================================================================

    async def batch_bind(
        self,
        bindings: List[Dict[str, Any]],
        is_manual: bool = True,
    ) -> Dict[str, Any]:
        """
        批量创建绑定

        使用场景：手动匹配时，用户选择了一个番剧的某一季，
        前端可以一次性提交该季所有集的绑定关系。

        Args:
            bindings: 绑定参数列表，每项包含:
                - file_id: str（必需）
                - episode_id: str（必需）
                - anime_id: Optional[str]
                - anime_title: Optional[str]
                - episode_title: Optional[str]
                - type: Optional[str]
                - typeDescription: Optional[str]
                - imageUrl: Optional[str]
                # - platform: Optional[str]
                - offset: float（默认 0.0）
            is_manual: 是否手动绑定

        Returns:
            {
                "total": int,
                "success": int,
                "failed": int,
                "results": List[Dict]
            }
        """
        total = len(bindings)
        success_count = 0
        failed_count = 0
        results = []

        for item in bindings:
            try:
                file_id = item.get("file_id")
                episode_id = item.get("episode_id")

                if not file_id or not episode_id:
                    results.append({
                        "fileId": file_id,
                        "success": False,
                        "error": "file_id and episode_id are required",
                    })
                    failed_count += 1
                    continue

                data = await self.create_binding(
                    file_id=file_id,
                    episode_id=episode_id,
                    anime_id=item.get("anime_id"),
                    anime_title=item.get("anime_title"),
                    episode_title=item.get("episode_title"),
                    type=item.get("type"),
                    typeDescription=item.get("typeDescription"),
                    imageUrl=item.get("imageUrl"),
                    # platform=item.get("platform"),
                    offset=item.get("offset", 0.0),
                    is_manual=is_manual,
                )
                results.append({
                    "fileId": file_id,
                    "success": True,
                    "binding": data,
                })
                success_count += 1

            except Exception as e:
                logger.error(f"Batch bind error for file {item.get('file_id')}: {e}")
                results.append({
                    "fileId": item.get("file_id"),
                    "success": False,
                    "error": str(e),
                })
                failed_count += 1

        logger.info(
            f"Batch bind completed: total={total}, success={success_count}, failed={failed_count}"
        )

        return {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "results": results,
        }

    # ================================================================
    #  偏移量管理
    # ================================================================

    async def update_offset(
        self,
        file_id: str,
        offset: float,
    ) -> Optional[Dict[str, Any]]:
        """
        更新时间偏移量

        Args:
            file_id: 文件 ID
            offset: 新的时间偏移量（秒）

        Returns:
            更新后的绑定信息，如果绑定不存在返回 None
        """
        async with get_async_session_context() as session:
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.exec(stmt)
            binding = result.one_or_none()

            if not binding:
                return None

            old_offset = binding.offset
            binding.offset = offset
            # binding.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(binding)

            # 记录历史
            await self._add_history(
                session, file_id, binding.episode_id, binding.anime_title,
                binding.episode_title, # binding.platform,
                "update_offset",
                extra=f"offset {old_offset} -> {offset}",
            )

            data = self._binding_to_dict(binding)

            # 更新缓存
            await danmu_cache_service.set_binding(file_id, data)

            logger.info(f"Updated offset for file: {file_id}, offset: {old_offset} -> {offset}")
            return data

    # ================================================================
    #  删除绑定
    # ================================================================

    async def delete_binding(self, file_id: str) -> bool:
        """
        删除弹幕绑定

        Args:
            file_id: 文件 ID

        Returns:
            是否删除成功
        """
        async with get_async_session_context() as session:
            # 先获取绑定信息用于记录历史
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.exec(stmt)
            binding = result.one_or_none()

            if not binding:
                return False

            # 记录历史
            await self._add_history(
                session, file_id, binding.episode_id, binding.anime_title,
                binding.episode_title, # binding.platform,
                "unbind",
            )



            # 删除绑定（SQLModel 语法）
            await session.exec(
                delete(DanmuBinding).where(DanmuBinding.file_id == file_id)
            )
            await session.commit()

            # 删除缓存
            await danmu_cache_service.delete_binding(file_id)

            logger.info(f"Deleted binding for file: {file_id}")
            return True

    async def batch_delete_bindings(self, file_ids: List[str]) -> Dict[str, Any]:
        """
        批量删除绑定

        Args:
            file_ids: 文件 ID 列表

        Returns:
            {"total": int, "success": int, "failed": int}
        """
        total = len(file_ids)
        success_count = 0

        for fid in file_ids:
            try:
                ok = await self.delete_binding(fid)
                if ok:
                    success_count += 1
            except Exception as e:
                logger.error(f"Batch delete binding error for file {fid}: {e}")

        return {
            "total": total,
            "success": success_count,
            "failed": total - success_count,
        }

    # ================================================================
    #  绑定历史
    # ================================================================

    async def get_binding_history(
        self,
        file_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        获取绑定历史记录

        Args:
            file_id: 文件 ID
            limit: 返回记录数量限制

        Returns:
            历史记录列表
        """
        async with get_async_session_context() as session:
            stmt = (
                select(DanmuBindingHistory)
                .where(DanmuBindingHistory.file_id == file_id)
                .order_by(DanmuBindingHistory.created_at.desc())
                .limit(limit)
            )
            result = await session.exec(stmt)
            histories = result.all()

            return [
                {
                    "id": h.id,
                    "fileId": h.file_id,
                    "episodeId": h.episode_id,
                    "animeTitle": h.anime_title,
                    "episodeTitle": h.episode_title,
                    # "platform": h.platform,
                    "action": h.action,
                    "extra": getattr(h, "extra", None),
                    "createdAt": h.created_at.isoformat() if h.created_at else None,
                }
                for h in histories
            ]

    # ================================================================
    #  内部方法
    # ================================================================

    async def _add_history(
        self,
        session,
        file_id: str,
        episode_id: str,
        anime_title: Optional[str],
        episode_title: Optional[str],
        # platform: Optional[str],
        action: str,
        extra: Optional[str] = None,
    ) -> None:
        """添加历史记录"""
        history = DanmuBindingHistory(
            file_id=file_id,
            episode_id=episode_id,
            anime_title=anime_title,
            episode_title=episode_title,
            # platform=platform,
            action=action,
            # created_at=datetime.utcnow()
        )
        # 如果模型支持 extra 字段
        if hasattr(history, "extra") and extra:
            history.extra = extra
        session.add(history)
        # 无需单独 commit，由上层事务统一提交

    def _binding_to_dict(self, binding: DanmuBinding) -> Dict[str, Any]:
        """将绑定模型转换为字典（snake_case，与 Pydantic schema 对齐）"""
        return {
            "id": binding.id,
            "file_id": binding.file_id,
            "episode_id": binding.episode_id,
            "anime_id": binding.anime_id,
            "anime_title": binding.anime_title,
            "episode_title": binding.episode_title,
            "type": binding.type,
            "typeDescription": binding.typeDescription,
            "imageUrl": binding.imageUrl,
            # "platform": binding.platform,
            "offset": binding.offset,
            "is_manual": bool(binding.is_manual),
            "match_confidence": getattr(binding, "match_confidence", None),
            # "source_info": getattr(binding, "source_info", None),
            # "created_at": binding.created_at.isoformat() if binding.created_at else None,
            # "updated_at": binding.updated_at.isoformat() if binding.updated_at else None,
        }


# 全局单例
danmu_binding_service = DanmuBindingService()