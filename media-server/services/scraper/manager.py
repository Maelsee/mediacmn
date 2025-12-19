# """
# 刮削器插件管理器
# """
# import asyncio
# import importlib
# import logging
# import pkgutil
# from pathlib import Path
# from typing import Dict, List, Optional, Type, Tuple

# from .base import MediaType, ScraperPlugin, ScraperSearchResult, ScraperMovieDetail, ScraperSeriesDetail

# logger = logging.getLogger(__name__)


# class ScraperManager:
#     """
#     刮削器插件管理器
    
#     实现插件的注册、加载、配置、测试连接和刮削功能
       
#     """
  
#     def __init__(self):
#         """
#         初始化刮削器插件管理器
        
#         初始化插件字典、插件类字典、已启用插件列表和插件配置字典
#         """
#         self._plugins: Dict[str, ScraperPlugin] = {}
#         self._plugin_classes: Dict[str, Type[ScraperPlugin]] = {}
#         self._enabled_plugins: List[str] = []
#         self._plugin_configs: Dict[str, dict] = {}
#         self._started: bool = False
#         self._op_lock: asyncio.Lock = asyncio.Lock()
    
#     def register_plugin(self, plugin_class: Type[ScraperPlugin], 
#                          name: Optional[str] = None) -> bool:
#         """
#         注册插件类
        
#         Args:
#             plugin_class: 插件类
#             name: 插件名称，如果为None则使用plugin_class的name属性
            
#         Returns:
#             是否注册成功
#         """
#         try:
#             # 创建临时实例来获取插件名称
#             temp_instance = plugin_class()
#             plugin_name = name or temp_instance.name
            
#             # 检查是否已经注册
#             if plugin_name in self._plugin_classes:
#                 logger.debug(f"插件 {plugin_name} 已经注册")
#                 return False
            
#             # 验证插件类
#             if not issubclass(plugin_class, ScraperPlugin):
#                 logger.error(f"插件类 {plugin_class.__name__} 必须继承 ScraperPlugin")
#                 return False
            
#             self._plugin_classes[plugin_name] = plugin_class
#             logger.info(f"注册插件类: {plugin_name}")
#             return True
            
#         except Exception as e:
#             logger.error(f"注册插件失败: {e}")
#             return False
    
#     async def load_plugin(self, name: str, config: Optional[dict] = None) -> bool:
#         """
#         加载插件实例
        
#         Args:
#             name: 插件名称
#             config: 插件配置
            
#         Returns:
#             是否加载成功
#         """
#         try:
#             async with self._op_lock:
#                 if name not in self._plugin_classes:
#                     logger.error(f"插件 {name} 未注册")
#                     return False
                
#                 # 已加载则直接复用实例；如提供新配置则应用到现有实例
#                 existing = self._plugins.get(name)
#                 if existing:
#                     if config:
#                         try:
#                             ok = existing.configure(config)
#                             if not ok:
#                                 logger.error(f"插件 {name} 配置失败")
#                                 return False
#                             self._plugin_configs[name] = config
#                         except Exception as e:
#                             logger.error(f"插件 {name} 配置异常: {e}")
#                             return False
#                     return True

#                 plugin_class = self._plugin_classes[name]
#                 plugin_instance = plugin_class()
                
#                 # 配置插件（首次加载）
#                 if config:
#                     try:
#                         ok = plugin_instance.configure(config)
#                         if not ok:
#                             logger.error(f"插件 {name} 配置失败")
#                             return False
#                         self._plugin_configs[name] = config
#                     except Exception as e:
#                         logger.error(f"插件 {name} 配置异常: {e}")
#                         return False
                
#                 # 测试连接（在受限网络环境下允许失败但仍注册插件）
#                 connection_ok = False
#                 try:
#                     connection_ok = await plugin_instance.test_connection()
#                 except Exception as e:
#                     logger.warning(f"插件 {name} 连接测试异常: {e}")
#                 if not connection_ok:
#                     logger.warning(f"插件 {name} 连接测试失败，仍继续加载（可能为离线环境）")

#                 self._plugins[name] = plugin_instance
#                 logger.info(f"加载插件: {name}")
#                 return True
#         except Exception as e:
#             logger.error(f"加载插件失败: {e}")
#             return False
    
#     def unload_plugin(self, name: str) -> bool:
#         """
#         卸载插件
        
#         Args:
#             name: 插件名称
            
#         Returns:
#             是否卸载成功
#         """
#         try:
#             if name in self._plugins:
#                 del self._plugins[name]
#                 logger.info(f"卸载插件: {name}")
#             return True
#         except Exception as e:
#             logger.error(f"卸载插件失败: {e}")
#             return False
    
#     def enable_plugin(self, name: str) -> bool:
#         """
#         启用插件
        
#         Args:
#             name: 插件名称
            
#         Returns:
#             是否启用成功
#         """
#         if name not in self._plugins:
#             logger.error(f"插件 {name} 未加载")
#             return False
        
#         if name not in self._enabled_plugins:
#             self._enabled_plugins.append(name)
#             logger.info(f"启用插件: {name}")
#         return True
    
#     def disable_plugin(self, name: str) -> bool:
#         """
#         禁用插件
        
#         Args:
#             name: 插件名称
            
#         Returns:
#             是否禁用成功
#         """
#         if name in self._enabled_plugins:
#             self._enabled_plugins.remove(name)
#             logger.info(f"禁用插件: {name}")
#         return True
    
#     def get_plugin(self, name: str) -> Optional[ScraperPlugin]:
#         """
#         获取插件实例
        
#         Args:
#             name: 插件名称
            
#         Returns:
#             插件实例或None
#         """
#         return self._plugins.get(name)
    
#     def get_loaded_plugins(self) -> List[str]:
#         """
#         获取已加载的插件列表
        
#         Returns:
#             插件名称列表
#         """
#         return list(self._plugins.keys())
    
#     def get_enabled_plugins(self) -> List[str]:
#         """
#         获取已启用的插件列表
        
#         Returns:
#             插件名称列表
#         """
#         return self._enabled_plugins.copy()
    
#     def get_available_plugins(self) -> List[Dict[str, any]]:
#         """
#         获取可用插件信息
        
#         Returns:
#             插件信息列表
#         """
#         plugins_info = []
#         for name, plugin_class in self._plugin_classes.items():
#             # 创建临时实例获取信息
#             temp_instance = plugin_class()
#             plugins_info.append({
#                 "name": name,
#                 "version": temp_instance.version,
#                 "description": temp_instance.description,
#                 "supported_media_types": [t.value for t in temp_instance.supported_media_types],
#                 "default_language": temp_instance.default_language,
#                 "priority": temp_instance.priority,
#                 "enabled": name in self._enabled_plugins,
#                 "loaded": name in self._plugins,
#                 "config_schema": temp_instance.get_config_schema()
#             })
#         return plugins_info
    
#     async def ensure_default_plugins(self) -> None:
#         try:
#             from core.config import get_settings
#             settings = get_settings()
#             enabled = set(getattr(settings, 'ENABLE_SCRAPERS', ['tmdb']) or ['tmdb'])
#             enabled = {str(x).lower() for x in enabled}
#         except Exception:
#             enabled = {"tmdb"}

#         try:
#             from .tmdb import TmdbScraper
#         except Exception:
#             TmdbScraper = None
#         try:
#             from .douban import DoubanScraper
#         except Exception:
#             DoubanScraper = None

#         try:
#             if TmdbScraper:
#                 try:
#                     self.register_plugin(TmdbScraper)
#                 except Exception:
#                     pass
#                 if 'tmdb' not in self._plugins:
#                     await self.load_plugin('tmdb')
#                 if 'tmdb' in enabled:
#                     self.enable_plugin('tmdb')
#             if DoubanScraper:
#                 try:
#                     self.register_plugin(DoubanScraper)
#                 except Exception:
#                     pass
#                 if 'douban' not in self._plugins:
#                     await self.load_plugin('douban')
#                 if 'douban' in enabled:
#                     self.enable_plugin('douban')
#         except Exception as e:
#             logger.warning(f"默认插件启用失败: {e}")
#     # region
#     # async def search_media_with_policy(self, title: str, year: Optional[int],
#     #                                    media_type: MediaType,
#     #                                    language: str) -> List[ScraperSearchResult]:
#     #     # 调用插件的search方法，根据语言回退策略返回搜索结果
#     #     try:
#     #         results = await self.search_media(title, year, media_type, language)
#     #         if results:
#     #             return results
#     #         try:
#     #             from core.config import get_settings
#     #             settings = get_settings()
#     #             fallback_movie = bool(getattr(settings, 'SCRAPER_FALLBACK_MOVIE', True))
#     #             fallback_series = bool(getattr(settings, 'SCRAPER_FALLBACK_SERIES', False))
#     #             allow_fallback = (media_type == MediaType.MOVIE and fallback_movie) or (media_type in (MediaType.TV_SERIES, MediaType.TV_EPISODE) and fallback_series)
#     #         except Exception:
#     #             allow_fallback = True if media_type == MediaType.MOVIE else False
#     #         if allow_fallback and language.lower() != 'en-us':
#     #             return await self.search_media(title, year, media_type, 'en-US')
#     #         return []
#     #     except Exception as e:
#     #         logger.error(f"策略搜索失败: {e}")
#     #         return []

#     # async def search_with_type_correction(self, title: str, year: Optional[int], initial_type: MediaType, language: str) -> Tuple[List[ScraperSearchResult], MediaType]:
#     #     try:
#     #         init_results = await self.search_media_with_policy(title, year, initial_type, language)
#     #         alt_type = MediaType.MOVIE if initial_type != MediaType.MOVIE else MediaType.TV_SERIES
#     #         alt_results = await self.search_media_with_policy(title, year, alt_type, language)
#     #         def score(r: ScraperSearchResult) -> float:
#     #             s = float(r.vote_average or 0)
#     #             if year and r.year:
#     #                 if r.year == year:
#     #                     s += 0.5
#     #                 else:
#     #                     diff = abs(r.year - year)
#     #                     if diff <= 2:
#     #                         s += 0.2
#     #             return s
#     #         if init_results and not alt_results:
#     #             return init_results, initial_type
#     #         if alt_results and not init_results:
#     #             return alt_results, alt_type
#     #         if init_results and alt_results:
#     #             init_best = max(init_results, key=score)
#     #             alt_best = max(alt_results, key=score)
#     #             if score(alt_best) > score(init_best):
#     #                 return alt_results, alt_type
#     #             else:
#     #                 return init_results, initial_type
#     #         return [], initial_type
#     #     except Exception:
#     #         return [], initial_type
#     # endregion
#     def auto_discover_plugins(self, package_path: Optional[str] = None) -> int:
#         """
#         自动发现插件
        
#         Args:
#             package_path: 插件包路径，如果为None则使用默认路径
            
#         Returns:
#             发现的插件数量
#         """
#         try:
#             if package_path is None:
#                 # 使用当前包路径
#                 package_path = str(Path(__file__).parent)
            
#             discovered = 0
            
#             # 扫描插件目录
#             plugin_dir = Path(package_path)
#             if not plugin_dir.exists():
#                 logger.warning(f"插件目录不存在: {plugin_dir}")
#                 return 0
            
#             # 查找所有Python文件
#             for py_file in plugin_dir.glob("*_scraper.py"):
#                 try:
#                     module_name = py_file.stem
#                     # 动态导入模块
#                     spec = importlib.util.spec_from_file_location(module_name, py_file)
#                     if spec and spec.loader:
#                         module = importlib.util.module_from_spec(spec)
#                         spec.loader.exec_module(module)
                        
#                         # 查找插件类
#                         for attr_name in dir(module):
#                             attr = getattr(module, attr_name)
#                             if (isinstance(attr, type) and 
#                                 issubclass(attr, ScraperPlugin) and 
#                                 attr != ScraperPlugin):
                                
#                                 if self.register_plugin(attr):
#                                     discovered += 1
                                    
#                 except Exception as e:
#                     logger.error(f"发现插件失败 {py_file}: {e}")
            
#             logger.info(f"自动发现插件完成，共发现 {discovered} 个插件")
#             return discovered
            
#         except Exception as e:
#             logger.error(f"自动发现插件失败: {e}")
#             return 0
    
#     async def search_media(self, title: str, year: Optional[int] ,
#                           media_type: MediaType ,
#                           language: str) -> List[ScraperSearchResult]:
#         """
#         搜索媒体信息（使用所有启用的插件）
        
#         Args:
#             title: 标题
#             year: 年份
#             media_type: 媒体类型
#             language: 语言
            
#         Returns:
#             合并的搜索结果列表
#         """
#         all_results = []
        
#         # 按优先级排序的插件
#         sorted_plugins = sorted(
#             [(name, self._plugins[name]) for name in self._enabled_plugins if name in self._plugins],
#             key=lambda x: x[1].priority,
#             reverse=True
#         )
        
#         # 并行搜索
#         tasks = []
#         for name, plugin in sorted_plugins:
#             task = asyncio.create_task(
#                 self._safe_search(plugin, title, year, media_type, language, name)
#             )
#             tasks.append(task)
        
#         # 等待所有搜索完成
#         results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
#         # 合并结果
#         for results in results_list:
#             if isinstance(results, list):
#                 all_results.extend(results)
        
#         # 按评分和年份排序
#         # all_results.sort(key=lambda x: (x.rating or 0, x.year or 0), reverse=True)
        
#         return all_results
    
#     async def _safe_search(self, plugin: ScraperPlugin, title: str, year: Optional[int],
#                           media_type: MediaType, language: str, plugin_name: str) -> List[ScraperSearchResult]:
#         """安全搜索（带异常处理）"""
#         try:
#             return await plugin.search(title, year, media_type, language)
#         except Exception as e:
#             logger.error(f"插件 {plugin_name} 搜索失败: {e}")
#             return []
    
#     async def enrich_with_best_match(self, title: str, year: Optional[int] = None,
#                                     media_type: MediaType = MediaType.MOVIE,
#                                     language: str = '') -> Optional[object]:
#         """
#         使用最佳匹配结果丰富信息
        
#         Args:
#             title: 标题
#             year: 年份
#             media_type: 媒体类型
#             language: 语言
            
#         Returns:
#             最佳匹配结果或None
#         """
#         results = await self.search_media(title, year, media_type, language)
        
#         if not results:
#             return None
        
#         # 选择第一个结果（已按评分排序）
#         best_match = results[0]
        
#         # 获取详细信息
#         if getattr(best_match, 'id', None):
#             try:
#                 plugin = self._plugins.get(best_match.provider)
#                 if plugin:
#                     if media_type == MediaType.MOVIE:
#                         details = await plugin.get_movie_details(best_match.id, language)
#                         if details:
#                             return details
#                     else:
#                         details = await plugin.get_series_details(best_match.id, language)
#                         if details:
#                             return details
#             except Exception as e:
#                 logger.error(f"获取详细信息失败: {e}")
        
#         return best_match
    
#     def clear(self):
#         """清空所有插件"""
#         self._plugins.clear()
#         self._plugin_classes.clear()
#         self._enabled_plugins.clear()
#         self._plugin_configs.clear()
#         logger.info("清空所有插件")

#     async def startup(self) -> None:
#         try:
#             if self._started:
#                 return
#             await self.ensure_default_plugins()
#             for name in self._enabled_plugins:
#                 try:
#                     p = self._plugins.get(name)
#                     if p:
#                         await p.startup()
#                 except Exception as e:
#                     logger.warning(f"插件 {name} 启动钩子失败: {e}")
#             self._started = True
#             logger.info("插件系统启动完成")
#         except Exception as e:
#             logger.error(f"插件系统启动失败: {e}")

#     async def shutdown(self) -> None:
#         try:
#             for name, plugin in list(self._plugins.items()):
#                 try:
#                     await plugin.shutdown()
#                 except Exception as e:
#                     logger.warning(f"插件 {name} 关闭钩子失败: {e}")
#             self._started = False
#             logger.info("插件系统已关闭")
#         except Exception as e:
#             logger.error(f"插件系统关闭失败: {e}")


# # 全局插件管理器实例
# scraper_manager = ScraperManager()

"""
刮削器插件管理器 - Optimized
"""
import asyncio
import importlib
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type,  Any

# 假设这些基类存在于 .base 中
from .base import MediaType, ScraperPlugin, ScraperSearchResult, ScraperMovieDetail, ScraperSeriesDetail
from .scraper_plugins.tmdb_scraper import TmdbScraper # 直接导入核心插件
logger = logging.getLogger(__name__)

class ScraperManager:
    """
    刮削器插件管理器 (单例模式)
    核心逻辑：保底注册核心插件 -> 自动发现扩展插件 -> 按需加载实例
    """
    
    _instance: Optional['ScraperManager'] = None
    _init_done: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ScraperManager._init_done:
            return
            
        self._plugins: Dict[str, Any] = {}  # 已加载的插件实例
        self._plugin_classes: Dict[str, Type] = {}  # 已注册的插件类
        self._enabled_plugins: List[str] = []
        self._plugin_configs: Dict[str, dict] = {}
        self._started: bool = False
        self._op_lock: asyncio.Lock = asyncio.Lock()
        
        ScraperManager._init_done = True
    
    @property
    def is_running(self) -> bool:
        return self._started
    
    def _ensure_started(self):
        """卫语句：如果未启动直接抛出异常，由调用方（丰富化流程）捕获"""
        if not self._started:
            raise RuntimeError("ScraperManager 尚未启动，请检查应用启动钩子(lifespan)。")
    # ================= 1. 注册与发现逻辑 =================

    def register_plugin(self, plugin_class: Type, name: Optional[str] = None) -> bool:   
        """注册插件类到管理器，增加防重逻辑"""
        try:
            # 获取插件名称
            plugin_name = name or getattr(plugin_class, 'name', None)
            
            # 容错：处理 property 对象
            if isinstance(plugin_name, property):
                temp = plugin_class()
                plugin_name = temp.name

            if not isinstance(plugin_name, str) or not plugin_name:
                logger.error(f"插件类 {plugin_class.__name__} 缺少有效的 name 属性")
                return False

            # --- 防重检查 ---
            if plugin_name in self._plugin_classes:
                # 如果已经注册过同名类，静默跳过，避免日志污染
                return True

            self._plugin_classes[plugin_name] = plugin_class
            logger.info(f"成功注册插件类: {plugin_name}")
            return True
        except Exception as e:
            logger.error(f"注册插件失败: {e}")
            return False

    def auto_discover_plugins(self, package_path: Optional[str] = None) -> int:
        """扫描插件目录并注册发现的插件"""
        try:
            if package_path is None:
                manager_dir = Path(__file__).parent.resolve()
                package_path = manager_dir / "scraper_plugins"
            else:
                package_path = Path(package_path).resolve()

            if not package_path.exists():
                logger.warning(f"插件目录不存在: {package_path}")
                return 0

            # 动态计算包名以支持相对导入
            try:
                root_dir = Path(__file__).resolve().parents[2] 
                relative_path = package_path.relative_to(root_dir)
                plugin_package = ".".join(relative_path.parts)
            except Exception:
                plugin_package = "services.scraper.scraper_plugins"

            discovered = 0
            for py_file in package_path.glob("*_scraper.py"):
                # 跳过初始化文件和核心 tmdb 文件（因为 tmdb 已手动注册）
                if py_file.stem in ["__init__", "tmdb_scraper"]:
                    continue
                
                try:
                    module_name = py_file.stem
                    full_module_name = f"{plugin_package}.{module_name}"
                    
                    spec = importlib.util.spec_from_file_location(full_module_name, str(py_file))
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[full_module_name] = module
                        spec.loader.exec_module(module)

                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            # 检查是否为插件类 (此处需确保 ScraperPlugin 已导入)
                            from .base import ScraperPlugin
                            if (isinstance(attr, type) and 
                                issubclass(attr, ScraperPlugin) and 
                                attr != ScraperPlugin):
                                if self.register_plugin(attr):
                                    discovered += 1
                                    logger.info(f"自动发现并注册插件: {attr.name}")
                except Exception as e:
                    logger.error(f"加载插件文件 {py_file.name} 失败: {e}")

            return discovered
        except Exception as e:
            logger.error(f"插件发现系统崩溃: {e}")
            return 0

    # ================= 2. 启动与生命周期 =================

    async def startup(self) -> None:
        """系统启动钩子：保底注册 -> 自动发现 -> 按需启动"""
        if self._started:
            return
            
        logger.info("正在启动插件系统...")

        # A. 保底注册核心插件 (确保即使文件系统出问题，核心功能也在)
        try:
            from .scraper_plugins.tmdb_scraper import TmdbScraper
            self.register_plugin(TmdbScraper)
        except ImportError as e:
            logger.error(f"无法导入核心插件 TmdbScraper: {e}")

        # B. 自动发现扩展插件 (如 douban 等)
        self.auto_discover_plugins()

        # C. 读取配置并激活
        try:
            from core.config import get_settings
            settings = get_settings()
            enabled_list = getattr(settings, 'ENABLE_SCRAPERS', []) or []
            enabled_names = {str(x).lower() for x in enabled_list}
        except Exception:
            enabled_names = set()

        # 强制确保核心插件在启用名单
        enabled_names.add("tmdb") 

        for name in enabled_names:
            if name in self._plugin_classes:
                # load_plugin 会处理实例化、配置应用和连接测试
                if await self.load_plugin(name):
                    self.enable_plugin(name)
                    # 执行插件内部的异步初始化（如 aiohttp session）
                    try:
                        await self._plugins[name].startup()
                    except Exception as e:
                        logger.error(f"插件 {name} 启动钩子执行失败: {e}")
            else:
                level = logging.CRITICAL if name == "tmdb" else logging.WARNING
                logger.log(level, f"插件 {name} 未能注册，请检查插件文件或路径")

        self._started = True
        logger.info(f"插件系统启动完成，当前启用: {self.get_enabled_plugins()}")

    async def shutdown(self) -> None:
        """系统关闭钩子"""
        for name, plugin in list(self._plugins.items()):
            try:
                if hasattr(plugin, 'shutdown'):
                    await plugin.shutdown()
            except Exception as e:
                logger.warning(f"插件 {name} 关闭异常: {e}")
        
        self._started = False
        logger.info("插件系统已关闭")

    # ================= 3. 插件管理操作 =================

    async def load_plugin(self, name: str, config: Optional[dict] = None) -> bool:
        """加载插件实例 (核心单例检查逻辑)"""
        if name not in self._plugin_classes:
            return False

        async with self._op_lock:
            # 如果实例已存在，尝试更新配置
            if name in self._plugins:
                if config:
                    self._plugins[name].configure(config)
                    self._plugin_configs[name] = config
                return True

            # 创建新实例
            try:
                plugin_class = self._plugin_classes[name]
                instance = plugin_class()
                
                # 应用配置
                conf = config or self._plugin_configs.get(name)
                if conf:
                    instance.configure(conf)
                    self._plugin_configs[name] = conf
                
                # 连接测试
                if not await instance.test_connection():
                    logger.warning(f"插件 {name} 连接测试未通过，将尝试继续加载")

                # 如果管理器已在运行，立即触发插件的热启动
                if self._started:
                    await instance.startup()

                self._plugins[name] = instance
                logger.info(f"加载插件实例: {name}")
                return True
            except Exception as e:
                logger.error(f"加载插件 {name} 失败: {e}", exc_info=True)
                return False

    def enable_plugin(self, name: str) -> bool:
        if name in self._plugins and name not in self._enabled_plugins:
            self._enabled_plugins.append(name)
            logger.info(f"启用插件: {name}")
            return True
        return False

    def get_enabled_plugins(self) -> List[str]:
        return self._enabled_plugins.copy()


    async def get_or_load_plugin(self, name: str) -> Optional[ScraperPlugin]:
        """
        获取插件，确保其已加载。
        业务代码调用此方法可确保插件对象存在。
        """
        if name in self._plugins:
            return self._plugins[name]
        
        # 尝试加载 (load_plugin 内部会处理配置、连接测试和 startup)
        success = await self.load_plugin(name)
        return self._plugins.get(name) if success else None
    
    def unload_plugin(self, name: str) -> bool:
        """卸载插件"""
        try:
            if name in self._plugins:
                del self._plugins[name]
                logger.info(f"卸载插件: {name}")
            return True
        except Exception as e:
            logger.error(f"卸载插件失败: {e}")
            return False
    
    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        if name in self._enabled_plugins:
            self._enabled_plugins.remove(name)
            logger.info(f"禁用插件: {name}")
        return True
    
    def get_plugin(self, name: str) -> Optional[ScraperPlugin]:
        """获取已加载的插件实例"""
        return self._plugins.get(name)
    
    def get_loaded_plugins(self) -> List[str]:
        return list(self._plugins.keys())
    
    def get_available_plugins(self) -> List[Dict[str, Any]]:
        """获取所有已注册插件的信息（优化性能，避免重复实例化）"""
        plugins_info = []
        for name, cls in self._plugin_classes.items():
            # 优先从活体实例取，拿不到则从类变量取
            instance = self._plugins.get(name)
            
            def get_meta(key, default):
                return getattr(instance, key, getattr(cls, key, default))

            info = {
                "name": name,
                "version": get_meta('version', '1.0.0'),
                "description": get_meta('description', ''),
                "enabled": name in self._enabled_plugins,
                "loaded": name in self._plugins,
                "priority": get_meta('priority', 0),
                "supported_media_types": [
                    t.value if hasattr(t, 'value') else t 
                    for t in get_meta('supported_media_types', [])
                ]
            }
            # 只有已加载的插件才显示 schema
            if instance and hasattr(instance, 'get_config_schema'):
                info["config_schema"] = instance.get_config_schema()
            
            plugins_info.append(info)
        return plugins_info
    
    # ================= 业务接口 =================
    async def search_media(self, title: str, year: Optional[int], media_type: MediaType, language: str) -> List[ScraperSearchResult]:
        """聚合搜索（增加超时控制和排序逻辑）"""
        # 核心防御
        self._ensure_started()
        
        # 获取已启用的插件实例
        active_plugins = [
            (name, self._plugins[name]) 
            for name in self._enabled_plugins 
            if name in self._plugins
        ]
        
        if not active_plugins:
            logger.warning("没有已启用的刮削器插件")
            return []

        # 按优先级降序排序
        active_plugins.sort(key=lambda x: x[1].priority, reverse=True)
        
        # 封装带超时的搜索任务
        async def _wrapped_search(name, plugin):
            try:
                # 设定单插件搜索超时，例如 10 秒
                return await asyncio.wait_for(
                    plugin.search(title, year, media_type, language), 
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error(f"插件 {name} 搜索超时")
                return []
            except Exception as e:
                logger.error(f"插件 {name} 搜索失败: {e}")
                return []

        tasks = [_wrapped_search(name, plugin) for name, plugin in active_plugins]
        results_list = await asyncio.gather(*tasks)
        
        # 合并结果
        all_results = []
        for res in results_list:
            all_results.extend(res)
            
        return all_results
    
    async def get_details(self, provider: str, provider_id: str, 
                          media_type: Any, language: str = "") -> Optional[Any]:
        # 核心防御
        self._ensure_started()
        
        plugin = self._plugins.get(provider)
        if not plugin: return None
        return await plugin.get_details(provider_id, media_type, language)

    async def clear(self):
        """完全重置管理器状态"""
        async with self._op_lock:
            # 停止所有插件的后台任务
            if self._plugins:
                tasks = []
                for name, plugin in self._plugins.items():
                    if hasattr(plugin, 'shutdown'):
                        tasks.append(plugin.shutdown())
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
            # 物理清空
            self._plugins.clear()
            self._plugin_classes.clear()
            self._enabled_plugins.clear()
            self._plugin_configs.clear()
            self._started = False
            logger.info("插件管理器状态已完全清空")
    
# 全局单例
scraper_manager = ScraperManager()