"""
电影合集相关API路由
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session, select, func
from sqlmodel import and_

from core.db import get_session
from core.security import get_current_subject
from models.media_models import Collection, MovieExt, MediaCore

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def list_collections(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    获取用户的电影合集列表
    
    Returns:
        包含合集列表、总数和分页信息的字典
    """
    user_id = int(current_subject)
    
    try:
        # 查询用户有电影的合集
        query = (
            select(Collection)
            .join(MovieExt, Collection.id == MovieExt.collection_id)
            .join(MediaCore, MovieExt.core_id == MediaCore.id)
            .where(MediaCore.user_id == user_id)
            .distinct()
        )
        
        # 获取总数
        total_query = (
            select(func.count(Collection.id))
            .join(MovieExt, Collection.id == MovieExt.collection_id)
            .join(MediaCore, MovieExt.core_id == MediaCore.id)
            .where(MediaCore.user_id == user_id)
            .distinct()
        )
        total = db.exec(total_query).one()
        
        # 分页查询
        collections = db.exec(
            query.offset((page - 1) * page_size).limit(page_size)
        ).all()
        
        # 获取每个合集中的电影数量
        collections_with_count = []
        for collection in collections:
            movie_count_query = (
                select(func.count(MovieExt.id))
                .join(MediaCore, MovieExt.core_id == MediaCore.id)
                .where(
                    and_(
                        MovieExt.collection_id == collection.id,
                        MediaCore.user_id == user_id
                    )
                )
            )
            movie_count = db.exec(movie_count_query).one()
            
            collections_with_count.append({
                "id": collection.id,
                "name": collection.name,
                "poster_path": collection.poster_path,
                "backdrop_path": collection.backdrop_path,
                "overview": collection.overview,
                "movie_count": movie_count,
                "created_at": collection.created_at,
                "updated_at": collection.updated_at
            })
        
        return {
            "ok": True,
            "collections": collections_with_count,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
        
    except Exception as e:
        logger.error(f"获取合集列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取合集列表失败: {str(e)}")


@router.get("/{collection_id}")
def get_collection_detail(
    collection_id: int,
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    获取合集详细信息
    
    Args:
        collection_id: 合集ID
        
    Returns:
        合集详细信息
    """
    user_id = int(current_subject)
    
    try:
        # 查询合集
        collection = db.exec(
            select(Collection).where(Collection.id == collection_id)
        ).first()
        
        if not collection:
            raise HTTPException(status_code=404, detail="合集不存在")
        
        # 验证用户是否有权限访问此合集（通过检查是否有该合集的电影）
        has_access = db.exec(
            select(MovieExt)
            .join(MediaCore, MovieExt.core_id == MediaCore.id)
            .where(
                and_(
                    MovieExt.collection_id == collection_id,
                    MediaCore.user_id == user_id
                )
            )
        ).first()
        
        if not has_access:
            raise HTTPException(status_code=403, detail="无权访问此合集")
        
        # 获取合集中的电影数量
        movie_count = db.exec(
            select(func.count(MovieExt.id))
            .join(MediaCore, MovieExt.core_id == MediaCore.id)
            .where(
                and_(
                    MovieExt.collection_id == collection_id,
                    MediaCore.user_id == user_id
                )
            )
        ).one()
        
        return {
            "ok": True,
            "collection": {
                "id": collection.id,
                "name": collection.name,
                "poster_path": collection.poster_path,
                "backdrop_path": collection.backdrop_path,
                "overview": collection.overview,
                "movie_count": movie_count,
                "created_at": collection.created_at,
                "updated_at": collection.updated_at
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取合集详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取合集详情失败: {str(e)}")


@router.get("/{collection_id}/movies")
def get_collection_movies(
    collection_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_subject: str = Depends(get_current_subject),
    db: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    获取合集中的电影列表
    
    Args:
        collection_id: 合集ID
        page: 页码
        page_size: 每页数量
        
    Returns:
        包含电影列表和分页信息的字典
    """
    user_id = int(current_subject)
    
    try:
        # 验证合集存在且用户有权限访问
        collection = db.exec(
            select(Collection).where(Collection.id == collection_id)
        ).first()
        
        if not collection:
            raise HTTPException(status_code=404, detail="合集不存在")
        
        # 验证用户权限
        has_access = db.exec(
            select(MovieExt)
            .join(MediaCore, MovieExt.core_id == MediaCore.id)
            .where(
                and_(
                    MovieExt.collection_id == collection_id,
                    MediaCore.user_id == user_id
                )
            )
        ).first()
        
        if not has_access:
            raise HTTPException(status_code=403, detail="无权访问此合集")
        
        # 查询合集中的电影
        query = (
            select(MediaCore, MovieExt)
            .join(MovieExt, MediaCore.id == MovieExt.core_id)
            .where(
                and_(
                    MovieExt.collection_id == collection_id,
                    MediaCore.user_id == user_id
                )
            )
            .order_by(MediaCore.year, MediaCore.title)
        )
        
        # 获取总数
        total_query = (
            select(func.count(MediaCore.id))
            .join(MovieExt, MediaCore.id == MovieExt.core_id)
            .where(
                and_(
                    MovieExt.collection_id == collection_id,
                    MediaCore.user_id == user_id
                )
            )
        )
        total = db.exec(total_query).one()
        
        # 分页查询
        results = db.exec(
            query.offset((page - 1) * page_size).limit(page_size)
        ).all()
        
        movies = []
        for media_core, movie_ext in results:
            movies.append({
                "id": media_core.id,
                "title": media_core.title,
                "original_title": media_core.original_title,
                "year": media_core.year,
                "plot": media_core.plot,
                "tagline": movie_ext.tagline,
                "collection_id": movie_ext.collection_id
            })
        
        return {
            "ok": True,
            "collection_name": collection.name,
            "movies": movies,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取合集电影列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取合集电影列表失败: {str(e)}")
