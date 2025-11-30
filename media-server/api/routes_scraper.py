"""
插件化刮削器API路由
"""
import logging
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_subject
from services.scraper import scraper_manager, MediaType
from services.scraper.tmdb import TmdbScraper
from services.scraper.douban import DoubanScraper
from services.media.metadata_enricher import metadata_enricher
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()
try:
    scraper_manager.register_plugin(TmdbScraper)
    scraper_manager.register_plugin(DoubanScraper)
except Exception:
    pass


class ScraperInfo(BaseModel):
    """刮削器信息"""
    name: str
    version: str
    description: str
    supported_media_types: List[str]
    default_language: str
    priority: int
    enabled: bool
    loaded: bool
    config_schema: Dict[str, Any]


class ScraperSearchRequest(BaseModel):
    """刮削器搜索请求"""
    title: str
    year: Optional[int] = None
    media_type: str = "movie"
    language: str = "zh-CN"


class ScraperEnrichRequest(BaseModel):
    """元数据丰富请求"""
    file_id: int
    language: str = "zh-CN"
    storage_id: Optional[int] = None  # 可选的存储配置ID


class ScraperConfigRequest(BaseModel):
    """刮削器配置请求"""
    config: Dict[str, Any]


@router.get("/plugins", response_model=List[ScraperInfo])
async def get_scraper_plugins(
    current_user: str = Depends(get_current_subject)
):
    """
    获取所有刮削器插件信息
    
    Args:
        current_user: 当前用户
        
    Returns:
        插件信息列表
    """
    try:
        plugins_info = scraper_manager.get_available_plugins()
        return plugins_info
    except Exception as e:
        logger.error(f"获取刮削器插件失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取插件信息失败: {str(e)}")


@router.post("/plugins/{plugin_name}/enable")
async def enable_scraper_plugin(
    plugin_name: str,
    current_user: str = Depends(get_current_subject)
):
    """
    启用刮削器插件
    
    Args:
        plugin_name: 插件名称
        current_user: 当前用户
        
    Returns:
        操作结果
    """
    try:
        await scraper_manager.load_plugin(plugin_name)
        success = scraper_manager.enable_plugin(plugin_name)
        if success:
            return {"success": True, "message": f"插件 {plugin_name} 已启用"}
        else:
            raise HTTPException(status_code=400, detail=f"插件 {plugin_name} 启用失败")
            
    except Exception as e:
        logger.error(f"启用插件失败: {e}")
        raise HTTPException(status_code=500, detail=f"启用插件失败: {str(e)}")


@router.post("/plugins/{plugin_name}/disable")
async def disable_scraper_plugin(
    plugin_name: str,
    current_user: str = Depends(get_current_subject)
):
    """
    禁用刮削器插件
    
    Args:
        plugin_name: 插件名称
        current_user: 当前用户
        
    Returns:
        操作结果
    """
    try:
        success = scraper_manager.disable_plugin(plugin_name)
        if success:
            return {"success": True, "message": f"插件 {plugin_name} 已禁用"}
        else:
            raise HTTPException(status_code=400, detail=f"插件 {plugin_name} 禁用失败")
            
    except Exception as e:
        logger.error(f"禁用插件失败: {e}")
        raise HTTPException(status_code=500, detail=f"禁用插件失败: {str(e)}")


@router.post("/plugins/{plugin_name}/configure")
async def configure_scraper_plugin(
    plugin_name: str,
    request: ScraperConfigRequest,
    current_user: str = Depends(get_current_subject)
):
    """
    配置刮削器插件
    
    Args:
        plugin_name: 插件名称
        request: 配置请求
        current_user: 当前用户
        
    Returns:
        操作结果
    """
    try:
        await scraper_manager.load_plugin(plugin_name, request.config)
        plugin = scraper_manager.get_plugin(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 未找到")
        
        success = plugin.configure(request.config)
        if success:
            return {"success": True, "message": f"插件 {plugin_name} 配置成功"}
        else:
            raise HTTPException(status_code=400, detail=f"插件 {plugin_name} 配置失败")
            
    except Exception as e:
        logger.error(f"配置插件失败: {e}")
        raise HTTPException(status_code=500, detail=f"配置插件失败: {str(e)}")


@router.post("/plugins/{plugin_name}/test")
async def test_scraper_plugin(
    plugin_name: str,
    current_user: str = Depends(get_current_subject)
):
    """
    测试刮削器插件连接
    
    Args:
        plugin_name: 插件名称
        current_user: 当前用户
        
    Returns:
        测试结果
    """
    try:
        await scraper_manager.load_plugin(plugin_name)
        plugin = scraper_manager.get_plugin(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 未找到")
        
        success = await plugin.test_connection()
        return {
            "success": success,
            "message": "连接测试成功" if success else "连接测试失败"
        }
        
    except Exception as e:
        logger.error(f"测试插件失败: {e}")
        raise HTTPException(status_code=500, detail=f"测试插件失败: {str(e)}")


@router.post("/search")
async def search_media(
    request: ScraperSearchRequest,
    current_user: str = Depends(get_current_subject)
):
    """
    搜索媒体信息
    
    Args:
        request: 搜索请求
        current_user: 当前用户
        
    Returns:
        搜索结果
    """
    try:
        logger.info(f"用户 {current_user} 搜索媒体: {request.title} ({request.year})")
        
        # 转换媒体类型
        try:
            media_type = MediaType(request.media_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的媒体类型: {request.media_type}")
        
        # 执行搜索
        results = await scraper_manager.search_media(
            title=request.title,
            year=request.year,
            media_type=media_type,
            language=request.language
        )
        
        # 转换结果为字典格式
        result_dicts = []
        for result in results:
            result_dict = {
                "id": getattr(result, "id", None),
                "title": getattr(result, "title", None),
                "original_name": getattr(result, "original_name", None),
                "original_language": getattr(result, "original_language", None),
                "release_date": getattr(result, "release_date", None),
                "vote_average": getattr(result, "vote_average", None),
                "provider": getattr(result, "provider", None),
                "media_type": getattr(result, "media_type", None),
                "poster_path": getattr(result, "poster_path", None),
                "backdrop_path": getattr(result, "backdrop_path", None),
                "year": getattr(result, "year", None),
                "provider_url": getattr(result, "provider_url", None),
            }
            result_dicts.append(result_dict)
        
        return {
            "success": True,
            "results": result_dicts,
            "count": len(result_dicts)
        }
        
    except Exception as e:
        logger.error(f"搜索媒体失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索媒体失败: {str(e)}")


@router.post("/enrich")
async def enrich_media_file(
    request: ScraperEnrichRequest,
    current_user: str = Depends(get_current_subject)
):
    """
    丰富媒体文件元数据
    
    Args:
        request: 丰富请求
        current_user: 当前用户
        
    Returns:
        操作结果
    """
    try:
        logger.info(f"用户 {current_user} 丰富文件元数据: {request.file_id}")
        
        # 执行丰富
        success = await metadata_enricher.enrich_media_file(
            file_id=request.file_id,
            preferred_language=request.language,
            storage_id=request.storage_id
        )
        
        if success:
            return {
                "success": True,
                "message": f"文件 {request.file_id} 元数据丰富成功"
            }
        else:
            return {
                "success": False,
                "message": f"文件 {request.file_id} 元数据丰富失败"
            }
            
    except Exception as e:
        logger.error(f"丰富媒体文件失败: {e}")
        return {
            "success": False,
            "message": f"异常: {str(e)}"
        }


@router.post("/enrich/batch")
async def enrich_multiple_files(
    file_ids: List[int],
    language: str = Query("zh-CN", description="语言"),
    storage_id: Optional[int] = Query(None, description="存储ID"),
    current_user: str = Depends(get_current_subject)
):
    """
    批量丰富媒体文件元数据
    
    Args:
        file_ids: 文件ID列表
        language: 语言
        current_user: 当前用户
        
    Returns:
        批量操作结果
    """
    try:
        logger.info(f"用户 {current_user} 批量丰富文件元数据: {len(file_ids)} 个文件")
        
        # 执行批量丰富
        results = await metadata_enricher.enrich_multiple_files(
            file_ids=file_ids,
            preferred_language=language,
            storage_id=storage_id
        )
        
        # 统计结果
        success_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - success_count
        
        return {
            "success": True,
            "results": results,
            "total": len(results),
            "success_count": success_count,
            "failed_count": failed_count,
            "message": f"批量丰富完成: 成功 {success_count} 个, 失败 {failed_count} 个"
        }
        
    except Exception as e:
        logger.error(f"批量丰富媒体文件失败: {e}")
        return {
            "success": False,
            "results": {fid: False for fid in file_ids},
            "total": len(file_ids),
            "success_count": 0,
            "failed_count": len(file_ids),
            "message": f"批量丰富异常: {str(e)}"
        }


@router.get("/supported-media-types")
async def get_supported_media_types(
    current_user: str = Depends(get_current_subject)
):
    """
    获取支持的媒体类型
    
    Args:
        current_user: 当前用户
        
    Returns:
        媒体类型列表
    """
    return {
        "success": True,
        "media_types": [
            {"value": "movie", "label": "电影"},
            {"value": "tv_series", "label": "电视剧"},
            {"value": "tv_episode", "label": "电视剧集"}
        ]
    }
