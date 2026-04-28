"""
弹幕 API 路由

提供弹幕相关的 REST API 接口。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from core.security import get_current_subject
from core.logging import logger
from schemas.danmu_serialization import (
    AutoMatchRequest,
    AutoMatchResponse,
    SearchRequest,
    SearchResponse,
    BindRequest,
    BindResponse,
    UpdateOffsetRequest,
    BindingInfo,
    DanmuData,
    DanmuLoadMode,
    MergeDanmuRequest,
    MergeDanmuResponse,
    PlatformInfo,
    PlatformStatus,
    DanmuSource,
    SuccessResponse,
    NextSegmentInput,
    DanmuFormat,
)
from services.danmu.danmu_service import danmu_service
from services.danmu.danmu_api_provider import DanmuApiError, DanmuApiTimeoutError


router = APIRouter()


# ==================== 匹配接口 ====================


# def _normalize_danmu_source(raw: dict) -> dict:
#     """兼容驼峰字段，转换为响应模型的下划线字段。"""
#     return {
#         "episode_id": str(raw.get("episode_id") or raw.get("episodeId") or ""),
#         "anime_id": (
#             str(raw.get("anime_id") or raw.get("animeId"))
#             if (raw.get("anime_id") is not None or raw.get("animeId") is not None)
#             else None
#         ),
#         "anime_title": raw.get("anime_title") or raw.get("animeTitle"),
#         "episode_title": raw.get("episode_title") or raw.get("episodeTitle"),
#         "platform": raw.get("platform"),
#         "similarity": float(raw.get("similarity") or 0),
#         "count": raw.get("count"),
#         "is_bound": bool(raw.get("is_bound") or raw.get("isBound") or False),
#     }

@router.post(
    "/match/auto",
    response_model=AutoMatchResponse,
    summary="自动匹配弹幕",
    description="根据视频标题、季数、集数等信息自动匹配弹幕源",
)
async def auto_match(
    request: AutoMatchRequest,
    _: str = Depends(get_current_subject),
) -> AutoMatchResponse:
    """
    自动匹配弹幕源
    
    根据视频元数据自动查找对应的弹幕源。
    如果文件已有绑定，直接返回绑定信息。
    """
    try:
        result = await danmu_service.auto_match(
            title=request.title,
            season=request.season,
            episode=request.episode,
            file_id=request.file_id,
            # file_name=request.file_name,
        )
        
        return AutoMatchResponse(
            is_matched=result.is_matched,
            confidence=result.confidence,
            sources=[
                DanmuSource(**source) for source in result.sources
            ],
            best_match=DanmuSource(**result.best_match) if result.best_match else None,
        )
        
    except Exception as e:
        logger.error(f"Auto match error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/match/search",
    response_model=SearchResponse,
    summary="手动搜索弹幕",
    description="根据关键词搜索弹幕源",
)
async def search_danmu(
    request: SearchRequest,
    _: str = Depends(get_current_subject),
) -> SearchResponse:
    """
    手动搜索弹幕源
    
    根据关键词搜索动漫或剧集。
    """
    try:
        result = await danmu_service.search(
            keyword=request.keyword,
            search_type=request.type.value,
            limit=request.limit,
        )
        
        return SearchResponse(
            keyword=result.get("keyword", request.keyword),
            type=request.type,
            items=result.get("items", []),
            has_more=result.get("hasMore", False),
        )
        
    except DanmuApiTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DanmuApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 绑定接口 ====================

@router.post(
    "/match/bind",
    response_model=BindResponse,
    summary="创建弹幕绑定",
    description="将视频文件与弹幕源绑定",
)
async def create_binding(
    request: BindRequest,
    _: str = Depends(get_current_subject),
) -> BindResponse:
    """
    创建弹幕绑定
    
    将视频文件与指定的弹幕源绑定，后续可直接通过文件ID获取弹幕。
    """
    try:
        result = await danmu_service.bind(
            file_id=request.file_id,
            episode_id=request.episode_id,
            anime_id=request.anime_id,
            anime_title=request.anime_title,
            episode_title=request.episode_title,
            platform=request.platform,
            offset=request.offset,
        )
        
        return BindResponse(**result)
        
    except Exception as e:
        logger.error(f"Create binding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/match/bind/{file_id}",
    response_model=BindingInfo,
    summary="获取绑定信息",
    description="获取指定文件的弹幕绑定信息",
)
async def get_binding(
    file_id: str = Path(..., description="文件ID"),
    _: str = Depends(get_current_subject),
) -> BindingInfo:
    """
    获取绑定信息
    
    获取指定文件的弹幕绑定信息。
    """
    from services.danmu.danmu_binding_service import danmu_binding_service
    
    try:
        result = await danmu_binding_service.get_binding(file_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Binding not found")
        
        return BindingInfo(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get binding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/match/bind/{file_id}",
    response_model=SuccessResponse,
    summary="解除绑定",
    description="解除视频文件与弹幕源的绑定",
)
async def delete_binding(
    file_id: str = Path(..., description="文件ID"),
    _: str = Depends(get_current_subject),
) -> SuccessResponse:
    """
    解除绑定
    
    解除视频文件与弹幕源的绑定。
    """
    try:
        success = await danmu_service.unbind(file_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Binding not found")
        
        return SuccessResponse(
            code=0,
            message="Binding deleted successfully",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete binding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/match/bind/{file_id}/offset",
    response_model=BindResponse,
    summary="更新偏移量",
    description="更新弹幕时间偏移量",
)
async def update_offset(
    request: UpdateOffsetRequest,
    file_id: str = Path(..., description="文件ID"),
    _: str = Depends(get_current_subject),
) -> BindResponse:
    """
    更新偏移量
    
    更新弹幕时间偏移量，用于调整弹幕与视频的同步。
    """
    try:
        result = await danmu_service.update_offset(
            file_id=file_id,
            offset=request.offset,
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Binding not found")
        
        return BindResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update offset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 弹幕获取接口 ====================

@router.get(
    "/by-url",
    response_model=DanmuData,
    summary="按 URL 获取弹幕",
    description="根据视频 URL 获取弹幕数据，支持全量或分片模式",
)
async def get_danmu_from_url(
    url: str = Query(..., description="视频页面 URL"),
    file_id: Optional[str] = Query(default=None, description="文件ID(用于获取偏移量)"),
    load_mode: DanmuLoadMode = Query(default=DanmuLoadMode.FULL, description="加载模式"),
    segment_index: Optional[int] = Query(default=None, ge=0, description="分片索引(load_mode=segment 时可选)"),
    _: str = Depends(get_current_subject),
) -> DanmuData:
    """按视频 URL 获取弹幕。"""
    try:
        result = await danmu_service.get_danmu_from_url(
            video_url=url,
            file_id=file_id,
            load_mode=load_mode.value,
            segment_index=segment_index,
        )
        return DanmuData(**result)
    except DanmuApiTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DanmuApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Get danmu from url error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{episode_id}",
    response_model=DanmuData,
    summary="获取弹幕",
    description="获取指定剧集的弹幕数据",
)
async def get_danmu(
    episode_id: str = Path(..., description="剧集ID"),
    # from_time: Optional[int] = Query(default=None, ge=0, description="开始时间(秒)"),
    # to_time: Optional[int] = Query(default=None, ge=0, description="结束时间(秒)"),
    file_id: Optional[str] = Query(default=None, description="文件ID(用于获取偏移量)"),
    load_mode: DanmuLoadMode = Query(default=DanmuLoadMode.SEGMENT, description="加载模式"),
    # segment_index: Optional[int] = Query(default=None, ge=0, description="分片索引(load_mode=segment 时可选)"),
    # next_segment: NextSegmentInput = Query(default_factory=NextSegmentInput, description="获取下一个分片弹幕数据"),
    format: DanmuFormat = Query(default=DanmuFormat.JSON, description="数据格式(json/xml)"),
    _: str = Depends(get_current_subject),
) -> DanmuData:
    """
    获取弹幕
    
    获取指定剧集的弹幕数据，支持分段获取。
    """
    try:
        result = await danmu_service.get_danmu(
            episode_id=episode_id,
            # from_time=from_time,
            # to_time=to_time,
            file_id=file_id,
            load_mode=load_mode.value,
            # next_segment=next_segment,
        )
        
        return DanmuData(**result)
        
    except DanmuApiTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DanmuApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Get danmu error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/next-segment",
    # response_model=NextSegmentInput,
    summary="获取下一个分片弹幕",
    description="根据当前分片获取下一个分片的弹幕数据",
)
async def get_next_segment(
    request: NextSegmentInput,
    format: DanmuFormat = Query(default=DanmuFormat.JSON, description="数据格式(json/xml)"),
    _: str = Depends(get_current_subject),
) -> Dict[str, Any]:
    """
    获取下一个分片弹幕
    
    根据当前分片获取下一个分片的弹幕数据。
    """
    try:
        result = await danmu_service.get_next_segment(
            next_segment=request.model_dump(),
            format=format.value,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Get next segment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/file/{file_id}",
    response_model=DanmuData,
    summary="按文件获取弹幕",
    description="根据文件ID获取弹幕数据",
)
async def get_danmu_by_file(
    file_id: str = Path(..., description="文件ID"),
    from_time: Optional[int] = Query(default=None, ge=0, description="开始时间(秒)"),
    to_time: Optional[int] = Query(default=None, ge=0, description="结束时间(秒)"),
    load_mode: DanmuLoadMode = Query(default=DanmuLoadMode.FULL, description="加载模式"),
    segment_index: Optional[int] = Query(default=None, ge=0, description="分片索引(load_mode=segment 时可选)"),
    _: str = Depends(get_current_subject),
) -> DanmuData:
    """
    按文件获取弹幕
    
    根据文件ID获取弹幕数据，自动使用绑定的弹幕源。
    """
    try:
        result = await danmu_service.get_danmu_by_file(
            file_id=file_id,
            from_time=from_time,
            to_time=to_time,
            load_mode=load_mode.value,
            segment_index=segment_index,
        )
        
        return DanmuData(**result)
        
    except Exception as e:
        logger.error(f"Get danmu by file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/merge",
    response_model=MergeDanmuResponse,
    summary="合并弹幕",
    description="合并多个弹幕源",
)
async def merge_danmu(
    request: MergeDanmuRequest,
    _: str = Depends(get_current_subject),
) -> MergeDanmuResponse:
    """
    合并弹幕
    
    合并多个弹幕源的数据，自动去重和排序。
    """
    try:
        result = await danmu_service.merge_danmu(
            episode_ids=request.episode_ids,
            from_time=request.from_time,
            to_time=request.to_time,
        )
        
        return MergeDanmuResponse(**result)
        
    except Exception as e:
        logger.error(f"Merge danmu error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 平台管理接口 ====================

@router.get(
    "/platforms",
    response_model=list[PlatformInfo],
    summary="获取平台列表",
    description="获取支持的弹幕平台列表",
)
async def get_platforms(
    _: str = Depends(get_current_subject),
) -> list[PlatformInfo]:
    """
    获取平台列表
    
    获取支持的弹幕平台列表。
    """
    try:
        platforms = await danmu_service.get_platforms()
        return [PlatformInfo(**p) for p in platforms]
        
    except Exception as e:
        logger.error(f"Get platforms error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/platforms/{platform}/status",
    response_model=PlatformStatus,
    summary="获取平台状态",
    description="检查指定平台的可用状态",
)
async def get_platform_status(
    platform: str = Path(..., description="平台ID"),
    _: str = Depends(get_current_subject),
) -> PlatformStatus:
    """
    获取平台状态
    
    检查指定弹幕平台的可用状态。
    """
    try:
        result = await danmu_service.check_platform_status(platform)
        return PlatformStatus(**result)
        
    except Exception as e:
        logger.error(f"Get platform status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 健康检查 ====================

@router.get(
    "/health",
    summary="弹幕服务健康检查",
    description="检查弹幕服务的健康状态",
)
async def health_check() -> dict:
    """
    健康检查
    
    检查弹幕服务的健康状态。
    """
    from services.danmu.danmu_cache_service import danmu_cache_service
    
    cache_stats = await danmu_cache_service.get_cache_stats()
    
    return {
        "status": "healthy",
        "cache": cache_stats,
    }
