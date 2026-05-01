
"""
弹幕 API 路由

提供弹幕相关的 REST API 接口。

手动匹配完整流程：
  1. POST /danmaku/search          → 关键词搜索，返回 animeId 列表
  2. GET  /danmaku/bangumi/{animeId} → 根据 animeId 获取番剧详情（含所有集数）
  3. 前端用户选择某一集的 episodeId
  4. POST /danmaku/match/bind       → 绑定 file_id + episodeId
  5. GET  /danmaku/{episodeId}      → 获取弹幕数据
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from core.db import get_async_session
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
    BangumiDetailResponse,
    BangumiSeason,
    BangumiEpisode,
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


@router.post(
    "/match/auto",
    response_model=AutoMatchResponse,
    summary="自动匹配弹幕",
    description="根据视频标题、季数、集数等信息自动匹配弹幕源",
)
async def auto_match(
    request: AutoMatchRequest,
    current_subject: str = Depends(get_current_subject),
) -> AutoMatchResponse:
    """
    自动匹配弹幕源

    支持两种调用方式：
    1. 传 title（可选 season/episode）直接匹配
    2. 传 file_id，后端从数据库自动解析 title/season/episode
    """
    logger.info(f"Auto match request: {request}")

    title = request.title
    season = request.season
    episode = request.episode

    # 如果没有传 title 但传了 file_id，从数据库自动解析
    if not title and request.file_id:
        try:
            user_id = int(current_subject)
            title, season, episode = await danmu_service.get_file_info(
                file_id=request.file_id,
                # current_subject=current_subject,
                user_id=user_id,
            )
            logger.info(f"Auto match resolved from file_id: title={title}, season={season}, episode={episode}")
        except Exception as e:
            logger.error(f"Get file info error: {e}")
            raise HTTPException(status_code=500, detail=f"无法获取文件信息: {e}")

    if not title:
        raise HTTPException(status_code=400, detail="缺少必要参数：title 或 file_id")

    try:
        result = await danmu_service.auto_match(
            title=title,
            season=season,
            episode=episode,
            file_id=request.file_id,
        )
        # logger.info(f"Auto match result: {result}") 
        return AutoMatchResponse(**result)

    except DanmuApiTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DanmuApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Auto match error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 搜索接口 ====================


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="手动搜索弹幕源",
    description="根据关键词搜索番剧，返回匹配的番剧列表（含 animeId）",
)
async def search_danmu(
    request: SearchRequest,
    _: str = Depends(get_current_subject),
) -> SearchResponse:
    """
    手动搜索弹幕源

    前端手动匹配第一步：用户输入关键词搜索番剧。
    返回的每一项都包含 animeId，前端用 animeId 调用 /bangumi/{animeId} 获取集数列表。

    danmu_api 接口: GET /api/v2/search/anime?keyword={keyword}
    返回格式:
    {
        "animes": [
            {
                "animeId": 294046,
                "animeTitle": "哈哈哈哈哈第6季(2026)【综艺】from 360",
                "type": "综艺",
                "episodeCount": 25,
                "source": "360",
                ...
            }
        ]
    }
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
        logger.error(f"Search danmu error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 番剧详情接口 ====================


@router.get(
    "/bangumi/{anime_id}",
    response_model=BangumiDetailResponse,
    summary="获取番剧详情",
    description="根据 animeId 获取番剧详情，包含所有季和剧集列表",
)
async def get_bangumi_detail(
    anime_id: str = Path(..., description="番剧ID (animeId)"),
    _: str = Depends(get_current_subject),
) -> BangumiDetailResponse:
    """
    获取番剧详情

    前端手动匹配第二步：用户选择搜索结果中的某个番剧后，
    用 animeId 调用此接口获取该番剧的所有季和剧集列表。
    前端展示剧集列表供用户选择具体某一集。

    danmu_api 接口: GET /api/v2/bangumi/{animeId}
    返回格式:
    {
        "bangumi": {
            "animeId": 333038,
            "animeTitle": "哈哈哈哈哈第五季",
            "type": "综艺",
            "seasons": [
                { "id": "season-333038", "name": "Season 1", "episodeCount": 38 }
            ],
            "episodes": [
                {
                    "seasonId": "season-333038",
                    "episodeId": 10036,
                    "episodeTitle": "先导片...",
                    "episodeNumber": "1"
                }
            ]
        }
    }

    前端拿到 episodes 列表后，用户选择某一集的 episodeId，
    然后调用 POST /danmaku/match/bind 绑定，再调用 GET /danmaku/{episodeId} 获取弹幕。
    """
    try:
        result = await danmu_service.get_bangumi_detail(anime_id)

        # 解析 seasons
        raw_seasons = result.get("seasons", [])
        seasons = []
        for s in raw_seasons:
            seasons.append(BangumiSeason(
                id=s.get("id", ""),
                airDate=s.get("airDate"),
                name=s.get("name", ""),
                episodeCount=s.get("episodeCount"),
            ))

        # 解析 episodes
        raw_episodes = result.get("episodes", [])
        episodes = []
        for ep in raw_episodes:
            episodes.append(BangumiEpisode(
                seasonId=ep.get("seasonId", ""),
                episodeId=int(ep.get("episodeId", 0)),
                episodeTitle=ep.get("episodeTitle", ""),
                episodeNumber=str(ep.get("episodeNumber", "")),
                airDate=ep.get("airDate"),
            ))

        return BangumiDetailResponse(
            animeId=int(result.get("animeId", anime_id)),
            animeTitle=result.get("animeTitle", ""),
            type=result.get("type"),
            typeDescription=result.get("typeDescription"),
            imageUrl=result.get("imageUrl"),
            episodeCount=result.get("episodeCount"),
            seasons=seasons,
            episodes=episodes,
        )

    except DanmuApiTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DanmuApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Get bangumi detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 弹幕获取接口 ====================


@router.get(
    "/{episode_id}",
    response_model=DanmuData,
    summary="获取弹幕数据",
    description="根据 episodeId 获取弹幕数据，支持全量和分段模式",
)
async def get_danmu(
    episode_id: str = Path(..., description="剧集ID (episodeId)"),
    file_id: Optional[str] = Query(default=None, description="文件ID"),
    load_mode: DanmuLoadMode = Query(default=DanmuLoadMode.SEGMENT, description="加载模式"),
    anime_id: Optional[str] = Query(default=None, description="番剧ID（首次自动绑定时使用）"),
    anime_title: Optional[str] = Query(default=None, description="番剧标题（首次自动绑定时使用）"),
    episode_title: Optional[str] = Query(default=None, description="剧集标题（首次自动绑定时使用）"),
    _: str = Depends(get_current_subject),
) -> DanmuData:
    """
    获取弹幕数据

    传入 file_id 时自动查询或创建绑定关系，无需单独调用 bind 接口。
    首次获取弹幕时可通过 anime_id/anime_title/episode_title 传递绑定元数据。

    load_mode=segment: 返回分片描述列表 + 第一分片弹幕（推荐，性能更好）
    load_mode=full: 返回全部弹幕数据
    """
    try:
        result = await danmu_service.get_danmu(
            episode_id=episode_id,
            file_id=file_id,
            load_mode=load_mode.value,
            anime_id=anime_id,
            anime_title=anime_title,
            episode_title=episode_title,
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
    "/{episode_id}/next-segment",
    summary="获取下一分片弹幕",
    description="根据分片信息获取下一分片的弹幕数据",
)
async def get_next_segment(
    segment: NextSegmentInput,
    episode_id: str = Path(..., description="剧集ID"),
    format: DanmuFormat = Query(default=DanmuFormat.JSON, description="数据格式"),
    _: str = Depends(get_current_subject),
) -> dict:
    """
    获取下一分片弹幕

    当 load_mode=segment 时，前端播放到分片边界时调用此接口获取下一分片弹幕。
    segment 信息来自 get_danmu 返回的 segment_list。
    """
    try:
        result = await danmu_service.get_next_segment(
            next_segment=segment.model_dump(),
            format=format.value,
        )
        return result

    except DanmuApiTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DanmuApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Get next segment error: {e}")
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

    前端手动匹配第三步：用户选择某一集后，调用此接口将 file_id 与 episodeId 绑定。
    绑定后下次播放同一文件时，可直接通过 file_id 获取弹幕。
    """
    try:
        result = await danmu_service.create_binding(
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
    description="获取视频文件的弹幕绑定信息",
)
async def get_binding(
    file_id: str = Path(..., description="文件ID"),
    _: str = Depends(get_current_subject),
) -> BindingInfo:
    """
    获取绑定信息

    播放视频时，先通过 file_id 查询是否已有弹幕绑定。
    如果有绑定，直接用绑定的 episodeId 获取弹幕。
    """
    try:
        result = await danmu_service.get_binding(file_id)

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
    response_model=BindingInfo,
    summary="更新偏移量",
    description="更新弹幕时间偏移量",
)
async def update_offset(
    file_id: str = Path(..., description="文件ID"),
    request: UpdateOffsetRequest = ...,
    _: str = Depends(get_current_subject),
) -> BindingInfo:
    """
    更新偏移量

    当弹幕与视频不同步时，用户可手动调整偏移量。
    """
    try:
        result = await danmu_service.update_offset(file_id, request.offset)

        if not result:
            raise HTTPException(status_code=404, detail="Binding not found")

        return BindingInfo(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update offset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批量获取接口 ====================


@router.post(
    "/batch",
    response_model=MergeDanmuResponse,
    summary="批量获取弹幕",
    description="合并获取多个弹幕源的弹幕数据",
)
async def get_batch_danmu(
    request: MergeDanmuRequest,
    _: str = Depends(get_current_subject),
) -> MergeDanmuResponse:
    """
    批量获取弹幕

    合并多个 episodeId 的弹幕数据。
    """
    try:
        result = await danmu_service.merge_danmu(
            episode_ids=request.episode_ids,
            from_time=request.from_time,
            to_time=request.to_time,
        )
        return MergeDanmuResponse(**result)

    except Exception as e:
        logger.error(f"Get batch danmu error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 平台接口 ====================


# @router.get(
#     "/platforms",
#     response_model=list[PlatformInfo],
#     summary="获取平台列表",
#     description="获取支持的弹幕平台列表",
# )
# async def get_platforms(
#     _: str = Depends(get_current_subject),
# ) -> list[PlatformInfo]:
#     """
#     获取平台列表

#     获取支持的弹幕平台列表。
#     """
#     try:
#         platforms = await danmu_service.get_platforms()
#         return [PlatformInfo(**p) for p in platforms]

#     except Exception as e:
#         logger.error(f"Get platforms error: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get(
#     "/platforms/{platform}/status",
#     response_model=PlatformStatus,
#     summary="获取平台状态",
#     description="检查指定平台的可用状态",
# )
# async def get_platform_status(
#     platform: str = Path(..., description="平台ID"),
#     _: str = Depends(get_current_subject),
# ) -> PlatformStatus:
#     """
#     获取平台状态

#     检查指定弹幕平台的可用状态。
#     """
#     try:
#         result = await danmu_service.check_platform_status(platform)
#         return PlatformStatus(**result)

#     except Exception as e:
#         logger.error(f"Get platform status error: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


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
