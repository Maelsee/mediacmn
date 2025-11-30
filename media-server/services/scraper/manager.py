"""
刮削器插件管理器
"""
import asyncio
import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Type, Tuple

from .base import MediaType, ScraperPlugin, ScraperSearchResult, ScraperMovieDetail, ScraperSeriesDetail

logger = logging.getLogger(__name__)


class ScraperManager:
    """
    刮削器插件管理器
    
    实现插件的注册、加载、配置、测试连接和刮削功能
       
    """
  
    def __init__(self):
        """
        初始化刮削器插件管理器
        
        初始化插件字典、插件类字典、已启用插件列表和插件配置字典
        """
        self._plugins: Dict[str, ScraperPlugin] = {}
        self._plugin_classes: Dict[str, Type[ScraperPlugin]] = {}
        self._enabled_plugins: List[str] = []
        self._plugin_configs: Dict[str, dict] = {}
        self._started: bool = False
    
    def register_plugin(self, plugin_class: Type[ScraperPlugin], 
                         name: Optional[str] = None) -> bool:
        """
        注册插件类
        
        Args:
            plugin_class: 插件类
            name: 插件名称，如果为None则使用plugin_class的name属性
            
        Returns:
            是否注册成功
        """
        try:
            # 创建临时实例来获取插件名称
            temp_instance = plugin_class()
            plugin_name = name or temp_instance.name
            
            # 检查是否已经注册
            if plugin_name in self._plugin_classes:
                logger.warning(f"插件 {plugin_name} 已经注册")
                return False
            
            # 验证插件类
            if not issubclass(plugin_class, ScraperPlugin):
                logger.error(f"插件类 {plugin_class.__name__} 必须继承 ScraperPlugin")
                return False
            
            self._plugin_classes[plugin_name] = plugin_class
            logger.info(f"注册插件类: {plugin_name}")
            return True
            
        except Exception as e:
            logger.error(f"注册插件失败: {e}")
            return False
    
    async def load_plugin(self, name: str, config: Optional[dict] = None) -> bool:
        """
        加载插件实例
        
        Args:
            name: 插件名称
            config: 插件配置
            
        Returns:
            是否加载成功
        """
        try:
            if name not in self._plugin_classes:
                logger.error(f"插件 {name} 未注册")
                return False
            
            plugin_class = self._plugin_classes[name]
            plugin_instance = plugin_class()
            
            # 配置插件
            if config:
                '''
                配置插件实例
                Args:
                    config: 插件配置
                Returns:
                    是否配置成功
                '''
                if not plugin_instance.configure(config):
                    logger.error(f"插件 {name} 配置失败")
                    return False
                self._plugin_configs[name] = config
            
            # 测试连接（在受限网络环境下允许失败但仍注册插件）
            connection_ok = False
            try:
                '''
                测试插件连接
                Returns:
                    是否连接成功
                '''
                connection_ok = await plugin_instance.test_connection()
            except Exception as e:
                logger.warning(f"插件 {name} 连接测试异常: {e}")
            if not connection_ok:
                logger.warning(f"插件 {name} 连接测试失败，仍继续加载（可能为离线环境）")

            self._plugins[name] = plugin_instance
            logger.info(f"加载插件: {name}")
            return True
            
        except Exception as e:
            logger.error(f"加载插件失败: {e}")
            return False
    
    def unload_plugin(self, name: str) -> bool:
        """
        卸载插件
        
        Args:
            name: 插件名称
            
        Returns:
            是否卸载成功
        """
        try:
            if name in self._plugins:
                del self._plugins[name]
                logger.info(f"卸载插件: {name}")
            return True
        except Exception as e:
            logger.error(f"卸载插件失败: {e}")
            return False
    
    def enable_plugin(self, name: str) -> bool:
        """
        启用插件
        
        Args:
            name: 插件名称
            
        Returns:
            是否启用成功
        """
        if name not in self._plugins:
            logger.error(f"插件 {name} 未加载")
            return False
        
        if name not in self._enabled_plugins:
            self._enabled_plugins.append(name)
            logger.info(f"启用插件: {name}")
        return True
    
    def disable_plugin(self, name: str) -> bool:
        """
        禁用插件
        
        Args:
            name: 插件名称
            
        Returns:
            是否禁用成功
        """
        if name in self._enabled_plugins:
            self._enabled_plugins.remove(name)
            logger.info(f"禁用插件: {name}")
        return True
    
    def get_plugin(self, name: str) -> Optional[ScraperPlugin]:
        """
        获取插件实例
        
        Args:
            name: 插件名称
            
        Returns:
            插件实例或None
        """
        return self._plugins.get(name)
    
    def get_loaded_plugins(self) -> List[str]:
        """
        获取已加载的插件列表
        
        Returns:
            插件名称列表
        """
        return list(self._plugins.keys())
    
    def get_enabled_plugins(self) -> List[str]:
        """
        获取已启用的插件列表
        
        Returns:
            插件名称列表
        """
        return self._enabled_plugins.copy()
    
    def get_available_plugins(self) -> List[Dict[str, any]]:
        """
        获取可用插件信息
        
        Returns:
            插件信息列表
        """
        plugins_info = []
        for name, plugin_class in self._plugin_classes.items():
            # 创建临时实例获取信息
            temp_instance = plugin_class()
            plugins_info.append({
                "name": name,
                "version": temp_instance.version,
                "description": temp_instance.description,
                "supported_media_types": [t.value for t in temp_instance.supported_media_types],
                "default_language": temp_instance.default_language,
                "priority": temp_instance.priority,
                "enabled": name in self._enabled_plugins,
                "loaded": name in self._plugins,
                "config_schema": temp_instance.get_config_schema()
            })
        return plugins_info
    
    async def ensure_default_plugins(self) -> None:
        try:
            from core.config import get_settings
            settings = get_settings()
            enabled = set(getattr(settings, 'ENABLE_SCRAPERS', ['tmdb']) or ['tmdb'])
            enabled = {str(x).lower() for x in enabled}
        except Exception:
            enabled = {"tmdb"}

        try:
            from .tmdb import TmdbScraper
        except Exception:
            TmdbScraper = None
        try:
            from .douban import DoubanScraper
        except Exception:
            DoubanScraper = None

        try:
            if TmdbScraper:
                try:
                    self.register_plugin(TmdbScraper)
                except Exception:
                    pass
                if 'tmdb' not in self._plugins:
                    await self.load_plugin('tmdb')
                if 'tmdb' in enabled:
                    self.enable_plugin('tmdb')
            if DoubanScraper:
                try:
                    self.register_plugin(DoubanScraper)
                except Exception:
                    pass
                if 'douban' not in self._plugins:
                    await self.load_plugin('douban')
                if 'douban' in enabled:
                    self.enable_plugin('douban')
        except Exception as e:
            logger.warning(f"默认插件启用失败: {e}")

    async def search_media_with_policy(self, title: str, year: Optional[int] = None,
                                       media_type: MediaType = MediaType.MOVIE,
                                       language: str = 'zh-CN') -> List[ScraperSearchResult]:
        # 调用插件的search方法，根据语言回退策略返回搜索结果
        try:
            results = await self.search_media(title, year, media_type, language)
            if results:
                return results
            try:
                from core.config import get_settings
                settings = get_settings()
                fallback_movie = bool(getattr(settings, 'SCRAPER_FALLBACK_MOVIE', True))
                fallback_series = bool(getattr(settings, 'SCRAPER_FALLBACK_SERIES', False))
                allow_fallback = (media_type == MediaType.MOVIE and fallback_movie) or (media_type in (MediaType.TV_SERIES, MediaType.TV_EPISODE) and fallback_series)
            except Exception:
                allow_fallback = True if media_type == MediaType.MOVIE else False
            if allow_fallback and language.lower() != 'en-us':
                return await self.search_media(title, year, media_type, 'en-US')
            return []
        except Exception as e:
            logger.error(f"策略搜索失败: {e}")
            return []

    async def search_with_type_correction(self, title: str, year: Optional[int], initial_type: MediaType, language: str) -> Tuple[List[ScraperSearchResult], MediaType]:
        try:
            init_results = await self.search_media_with_policy(title, year, initial_type, language)
            alt_type = MediaType.MOVIE if initial_type != MediaType.MOVIE else MediaType.TV_SERIES
            alt_results = await self.search_media_with_policy(title, year, alt_type, language)
            def score(r: ScraperSearchResult) -> float:
                s = float(r.vote_average or 0)
                if year and r.year:
                    if r.year == year:
                        s += 0.5
                    else:
                        diff = abs(r.year - year)
                        if diff <= 2:
                            s += 0.2
                return s
            if init_results and not alt_results:
                return init_results, initial_type
            if alt_results and not init_results:
                return alt_results, alt_type
            if init_results and alt_results:
                init_best = max(init_results, key=score)
                alt_best = max(alt_results, key=score)
                if score(alt_best) > score(init_best):
                    return alt_results, alt_type
                else:
                    return init_results, initial_type
            return [], initial_type
        except Exception:
            return [], initial_type

    def auto_discover_plugins(self, package_path: Optional[str] = None) -> int:
        """
        自动发现插件
        
        Args:
            package_path: 插件包路径，如果为None则使用默认路径
            
        Returns:
            发现的插件数量
        """
        try:
            if package_path is None:
                # 使用当前包路径
                package_path = str(Path(__file__).parent)
            
            discovered = 0
            
            # 扫描插件目录
            plugin_dir = Path(package_path)
            if not plugin_dir.exists():
                logger.warning(f"插件目录不存在: {plugin_dir}")
                return 0
            
            # 查找所有Python文件
            for py_file in plugin_dir.glob("*_scraper.py"):
                try:
                    module_name = py_file.stem
                    # 动态导入模块
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # 查找插件类
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and 
                                issubclass(attr, ScraperPlugin) and 
                                attr != ScraperPlugin):
                                
                                if self.register_plugin(attr):
                                    discovered += 1
                                    
                except Exception as e:
                    logger.error(f"发现插件失败 {py_file}: {e}")
            
            logger.info(f"自动发现插件完成，共发现 {discovered} 个插件")
            return discovered
            
        except Exception as e:
            logger.error(f"自动发现插件失败: {e}")
            return 0
    
    async def search_media(self, title: str, year: Optional[int] = None,
                          media_type: MediaType = MediaType.MOVIE,
                          language: str = "zh-CN") -> List[ScraperSearchResult]:
        """
        搜索媒体信息（使用所有启用的插件）
        
        Args:
            title: 标题
            year: 年份
            media_type: 媒体类型
            language: 语言
            
        Returns:
            合并的搜索结果列表
        """
        all_results = []
        
        # 按优先级排序的插件
        sorted_plugins = sorted(
            [(name, self._plugins[name]) for name in self._enabled_plugins if name in self._plugins],
            key=lambda x: x[1].priority,
            reverse=True
        )
        
        # 并行搜索
        tasks = []
        for name, plugin in sorted_plugins:
            task = asyncio.create_task(
                self._safe_search(plugin, title, year, media_type, language, name)
            )
            tasks.append(task)
        
        # 等待所有搜索完成
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        for results in results_list:
            if isinstance(results, list):
                all_results.extend(results)
        
        # 按评分和年份排序
        all_results.sort(key=lambda x: (x.rating or 0, x.year or 0), reverse=True)
        
        return all_results
    
    async def _safe_search(self, plugin: ScraperPlugin, title: str, year: Optional[int],
                          media_type: MediaType, language: str, plugin_name: str) -> List[ScraperSearchResult]:
        """安全搜索（带异常处理）"""
        try:
            return await plugin.search(title, year, media_type, language)
        except Exception as e:
            logger.error(f"插件 {plugin_name} 搜索失败: {e}")
            return []
    
    async def enrich_with_best_match(self, title: str, year: Optional[int] = None,
                                    media_type: MediaType = MediaType.MOVIE,
                                    language: str = "zh-CN") -> Optional[object]:
        """
        使用最佳匹配结果丰富信息
        
        Args:
            title: 标题
            year: 年份
            media_type: 媒体类型
            language: 语言
            
        Returns:
            最佳匹配结果或None
        """
        results = await self.search_media(title, year, media_type, language)
        
        if not results:
            return None
        
        # 选择第一个结果（已按评分排序）
        best_match = results[0]
        
        # 获取详细信息
        if getattr(best_match, 'id', None):
            try:
                plugin = self._plugins.get(best_match.provider)
                if plugin:
                    if media_type == MediaType.MOVIE:
                        details = await plugin.get_movie_details(best_match.id, language)
                        if details:
                            return details
                    else:
                        details = await plugin.get_series_details(best_match.id, language)
                        if details:
                            return details
            except Exception as e:
                logger.error(f"获取详细信息失败: {e}")
        
        return best_match
    
    def clear(self):
        """清空所有插件"""
        self._plugins.clear()
        self._plugin_classes.clear()
        self._enabled_plugins.clear()
        self._plugin_configs.clear()
        logger.info("清空所有插件")

    async def startup(self) -> None:
        try:
            if self._started:
                return
            await self.ensure_default_plugins()
            for name in self._enabled_plugins:
                try:
                    p = self._plugins.get(name)
                    if p:
                        await p.startup()
                except Exception as e:
                    logger.warning(f"插件 {name} 启动钩子失败: {e}")
            self._started = True
            logger.info("插件系统启动完成")
        except Exception as e:
            logger.error(f"插件系统启动失败: {e}")

    async def shutdown(self) -> None:
        try:
            for name, plugin in list(self._plugins.items()):
                try:
                    await plugin.shutdown()
                except Exception as e:
                    logger.warning(f"插件 {name} 关闭钩子失败: {e}")
            self._started = False
            logger.info("插件系统已关闭")
        except Exception as e:
            logger.error(f"插件系统关闭失败: {e}")


# 全局插件管理器实例
scraper_manager = ScraperManager()
