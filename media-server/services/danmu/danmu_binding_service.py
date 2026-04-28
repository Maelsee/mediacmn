"""
弹幕绑定服务

本模块管理视频文件与弹幕源的绑定关系，包括：
- 绑定关系持久化
- 偏移量管理
- 绑定历史记录
"""


from core.config import get_settings
from services.danmu.danmu_cache_service import danmu_cache_service
from core.db import get_async_session_context
from typing import Optional, Dict, Any, List
from datetime import datetime

from models.danmu_models import DanmuBinding, DanmuBindingHistory
import logging
logger = logging.getLogger(__name__)

class DanmuBindingService:
    """
    弹幕绑定服务
    
    管理视频文件与弹幕源的绑定关系，支持：
    - 创建、更新、删除绑定
    - 偏移量调整
    - 绑定历史查询
    """
    
    def __init__(self) -> None:
        """初始化绑定服务"""
        settings = get_settings()
        self._database_url = getattr(settings, "DATABASE_URL", "")
        logger.info("DanmuBindingService initialized")
    
    async def get_binding(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文件的弹幕绑定
        
        Args:
            file_id: 文件 ID
            
        Returns:
            绑定信息，如果不存在返回 None
        """
        # 先查缓存
        cached = await danmu_cache_service.get_binding(file_id)
        if cached:
            return cached
        
        # 查数据库
        async with get_async_session_context() as session:
            from sqlalchemy import select
            
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.execute(stmt)
            binding = result.scalar_one_or_none()
            
            if binding:
                data = self._binding_to_dict(binding)
                # 写入缓存
                await danmu_cache_service.set_binding(file_id, data)
                return data
            
            return None
    
    async def create_binding(
        self,
        file_id: str,
        episode_id: str,
        anime_id: Optional[str] = None,
        anime_title: Optional[str] = None,
        episode_title: Optional[str] = None,
        platform: Optional[str] = None,
        offset: float = 0.0,
        is_manual: bool = False,
    ) -> Dict[str, Any]:
        """
        创建弹幕绑定
        
        Args:
            file_id: 文件 ID
            episode_id: 剧集 ID
            anime_id: 番剧 ID
            anime_title: 番剧标题
            episode_title: 剧集标题
            platform: 弹幕平台
            offset: 时间偏移量（秒）
            is_manual: 是否手动绑定
            
        Returns:
            创建的绑定信息
        """
        async with get_async_session_context() as session:
            # 检查是否已存在绑定
            from sqlalchemy import select, delete
            
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # 更新现有绑定
                existing.episode_id = episode_id
                existing.anime_id = anime_id
                existing.anime_title = anime_title
                existing.episode_title = episode_title
                existing.platform = platform
                existing.offset = offset
                existing.is_manual = 1 if is_manual else 0
                existing.updated_at = datetime.utcnow()
                
                await session.commit()
                
                # 记录历史
                await self._add_history(
                    session, file_id, episode_id, anime_title,
                    episode_title, platform, "update"
                )
                
                data = self._binding_to_dict(existing)
            else:
                # 创建新绑定
                binding = DanmuBinding(
                    file_id=file_id,
                    episode_id=episode_id,
                    anime_id=anime_id,
                    anime_title=anime_title,
                    episode_title=episode_title,
                    platform=platform,
                    offset=offset,
                    is_manual=1 if is_manual else 0,
                )
                session.add(binding)
                
                await session.commit()
                
                # 记录历史
                await self._add_history(
                    session, file_id, episode_id, anime_title,
                    episode_title, platform, "bind"
                )
                
                data = self._binding_to_dict(binding)
            
            # 更新缓存
            await danmu_cache_service.set_binding(file_id, data)
            
            logger.info(f"Created/Updated binding for file: {file_id} -> episode: {episode_id}")
            return data
    
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
            from sqlalchemy import select
            
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.execute(stmt)
            binding = result.scalar_one_or_none()
            
            if not binding:
                return None
            
            binding.offset = offset
            binding.updated_at = datetime.utcnow()
            
            await session.commit()
            
            # 记录历史
            await self._add_history(
                session, file_id, binding.episode_id, binding.anime_title,
                binding.episode_title, binding.platform, "update"
            )
            
            data = self._binding_to_dict(binding)
            
            # 更新缓存
            await danmu_cache_service.set_binding(file_id, data)
            
            logger.info(f"Updated offset for file: {file_id}, offset: {offset}")
            return data
    
    async def delete_binding(self, file_id: str) -> bool:
        """
        删除弹幕绑定
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否删除成功
        """
        async with get_async_session_context() as session:
            from sqlalchemy import select, delete
            
            # 先获取绑定信息用于记录历史
            stmt = select(DanmuBinding).where(DanmuBinding.file_id == file_id)
            result = await session.execute(stmt)
            binding = result.scalar_one_or_none()
            
            if not binding:
                return False
            
            # 记录历史
            await self._add_history(
                session, file_id, binding.episode_id, binding.anime_title,
                binding.episode_title, binding.platform, "unbind"
            )
            
            # 删除绑定
            await session.execute(
                delete(DanmuBinding).where(DanmuBinding.file_id == file_id)
            )
            await session.commit()
            
            # 删除缓存
            await danmu_cache_service.delete_binding(file_id)
            
            logger.info(f"Deleted binding for file: {file_id}")
            return True
    
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
            from sqlalchemy import select
            
            stmt = (
                select(DanmuBindingHistory)
                .where(DanmuBindingHistory.file_id == file_id)
                .order_by(DanmuBindingHistory.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            histories = result.scalars().all()
            
            return [
                {
                    "id": h.id,
                    "fileId": h.file_id,
                    "episodeId": h.episode_id,
                    "animeTitle": h.anime_title,
                    "episodeTitle": h.episode_title,
                    "platform": h.platform,
                    "action": h.action,
                    "createdAt": h.created_at.isoformat() if h.created_at else None,
                }
                for h in histories
            ]
    
    async def _add_history(
        self,
        session,
        file_id: str,
        episode_id: str,
        anime_title: Optional[str],
        episode_title: Optional[str],
        platform: Optional[str],
        action: str,
    ) -> None:
        """添加历史记录"""
        history = DanmuBindingHistory(
            file_id=file_id,
            episode_id=episode_id,
            anime_title=anime_title,
            episode_title=episode_title,
            platform=platform,
            action=action,
        )
        session.add(history)
    
    def _binding_to_dict(self, binding: DanmuBinding) -> Dict[str, Any]:
        """将绑定模型转换为字典"""
        return {
            "id": binding.id,
            "fileId": binding.file_id,
            "episodeId": binding.episode_id,
            "animeId": binding.anime_id,
            "animeTitle": binding.anime_title,
            "episodeTitle": binding.episode_title,
            "platform": binding.platform,
            "offset": binding.offset,
            "isManual": bool(binding.is_manual),
            "createdAt": binding.created_at.isoformat() if binding.created_at else None,
            "updatedAt": binding.updated_at.isoformat() if binding.updated_at else None,
        }


# 全局单例
danmu_binding_service = DanmuBindingService()
