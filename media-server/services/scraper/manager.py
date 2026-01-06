
"""
刮削器插件管理器 - Optimized
"""
import asyncio
import importlib
import logging
import sys
import time
import secrets
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Type, Any, Callable, Awaitable, Tuple

import orjson
import redis.asyncio as redis

from core.config import get_settings
from .base import (
    MediaType,
    ScraperPlugin,
    ScraperSearchResult,
    ScraperMovieDetail,
    ScraperSeriesDetail,
    ScraperSeasonDetail,
)
logger = logging.getLogger(__name__)

class _LocalDetailCache:
    def __init__(self, maxsize: int, ttl_seconds: int):
        self._maxsize = max(1, int(maxsize))
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._data: OrderedDict[Tuple[Any, ...], Tuple[float, Any]] = OrderedDict()

    def clear(self) -> None:
        self._data.clear()

    def get(self, key: Tuple[Any, ...]) -> Optional[Any]:
        item = self._data.get(key)
        if not item:
            return None
        expires_at, value = item
        now = time.time()
        if expires_at <= now:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key, last=True)
        return value

    def set(self, key: Tuple[Any, ...], value: Any) -> None:
        now = time.time()
        expires_at = now + self._ttl_seconds
        self._data[key] = (expires_at, value)
        self._data.move_to_end(key, last=True)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

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
        self._inflight: Dict[Tuple[Any, ...], asyncio.Task] = {}
        self._inflight_lock: asyncio.Lock = asyncio.Lock()
        self._timeout_seconds: float = 10.0

        settings = get_settings()
        self._detail_cache = _LocalDetailCache(
            maxsize=getattr(settings, "SCRAPER_DETAIL_CACHE_LOCAL_MAXSIZE", 2048),
            ttl_seconds=getattr(settings, "SCRAPER_DETAIL_CACHE_TTL_SECONDS", 86400),
        )
        self._use_redis_cache: bool = bool(getattr(settings, "SCRAPER_DETAIL_CACHE_USE_REDIS", False))
        self._cache_ttl_seconds: int = int(getattr(settings, "SCRAPER_DETAIL_CACHE_TTL_SECONDS", 86400))
        self._lock_ttl_seconds: int = int(getattr(settings, "SCRAPER_DETAIL_CACHE_LOCK_TTL_SECONDS", 30))
        self._lock_wait_ms: int = int(getattr(settings, "SCRAPER_DETAIL_CACHE_LOCK_WAIT_MS", 1500))
        self._lock_poll_ms: int = int(getattr(settings, "SCRAPER_DETAIL_CACHE_LOCK_POLL_MS", 50))
        self._redis: Optional[redis.Redis] = None
        
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

    def _cache_key(self, kind: str, provider: str, language: str, *parts: Any) -> Tuple[Any, ...]:
        return ("scraper_detail", kind, provider, language, *parts)

    def _redis_key(self, kind: str, provider: str, language: str, *parts: Any) -> str:
        suffix = ":".join(str(p) for p in parts)
        return f"scraper:detail:{kind}:{provider}:{language}:{suffix}"

    def _redis_lock_key(self, redis_key: str) -> str:
        return f"{redis_key}:lock"

    def _ensure_redis(self) -> Optional[redis.Redis]:
        if not self._use_redis_cache:
            return None
        if self._redis is not None:
            return self._redis
        s = get_settings()
        self._redis = redis.from_url(s.SCRAPER_CACHE_REDIS_URL, db=s.SCRAPER_CACHE_REDIS_DB, decode_responses=False)
        return self._redis

    async def _singleflight(self, key: Tuple[Any, ...], coro_factory: Callable[[], Awaitable[Any]]) -> Any:
        async with self._inflight_lock:
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(coro_factory())
                self._inflight[key] = task
        try:
            return await task
        finally:
            async with self._inflight_lock:
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)

    async def _get_cached_model(self, key: Tuple[Any, ...], redis_key: str, model_cls: Any) -> Optional[Any]:
        local = self._detail_cache.get(key)
        if local is not None:
            return local

        r = self._ensure_redis()
        if not r:
            return None
        try:
            raw = await r.get(redis_key)
            if not raw:
                return None
            data = orjson.loads(raw)
            model = model_cls.model_validate(data)
            self._detail_cache.set(key, model)
            return model
        except Exception:
            return None

    async def _set_cached_model(self, key: Tuple[Any, ...], redis_key: str, model: Any) -> None:
        if model is None:
            return
        self._detail_cache.set(key, model)

        r = self._ensure_redis()
        if not r:
            return
        try:
            payload = orjson.dumps(model.model_dump(mode="json"))
            await r.set(redis_key, payload, ex=self._cache_ttl_seconds)
        except Exception:
            return

    async def get_series_details_cached(
        self,
        best_match: "ScraperSearchResult",
        language: str = "",
    ) -> Optional["ScraperSeriesDetail"]:
        """
        获取并缓存系列详情，只命中一次插件调用
        """
        self._ensure_started()

        provider = getattr(best_match, "provider", None)
        provider_id = getattr(best_match, "id", None)
        if not provider or provider_id is None:
            return None

        plugin = self._plugins.get(provider)
        if not plugin:
            return None

        lang = language or getattr(plugin, "default_language", "")
        cache_key = self._cache_key("series", provider, lang, int(provider_id))
        redis_key = self._redis_key("series", provider, lang, int(provider_id))
        return await self._get_or_compute_cached_model(
            cache_key,
            redis_key,
            ScraperSeriesDetail,
            lambda: self._call_with_timeout(
                provider,
                "get_series_details",
                plugin.get_series_details(int(provider_id), lang),
            ),
        )

    async def get_season_details_cached(
        self,
        best_match: "ScraperSearchResult",
        language: str = "",
        season: Optional[int] = None,
    ) -> Optional["ScraperSeasonDetail"]:
        """
        获取并缓存某一季详情，只命中一次插件调用
        """
        self._ensure_started()

        if season is None:
            return None

        provider = getattr(best_match, "provider", None)
        provider_id = getattr(best_match, "id", None)
        if not provider or provider_id is None:
            return None

        plugin = self._plugins.get(provider)
        if not plugin:
            return None

        lang = language or getattr(plugin, "default_language", "")
        cache_key = self._cache_key("season", provider, lang, int(provider_id), int(season))
        redis_key = self._redis_key("season", provider, lang, int(provider_id), int(season))
        return await self._get_or_compute_cached_model(
            cache_key,
            redis_key,
            ScraperSeasonDetail,
            lambda: self._call_with_timeout(
                provider,
                "get_season_details",
                plugin.get_season_details(int(provider_id), int(season), lang),
            ),
        )

    async def _get_or_compute_cached_model(
        self,
        cache_key: Tuple[Any, ...],
        redis_key: str,
        model_cls: Any,
        compute: Callable[[], Awaitable[Any]],
    ) -> Optional[Any]:
        cached = self._detail_cache.get(cache_key)
        if cached is not None:
            return cached

        r = self._ensure_redis()
        if r:
            from_redis = await self._get_cached_model(cache_key, redis_key, model_cls)
            if from_redis is not None:
                return from_redis

        async def _run_once() -> Optional[Any]:
            cached2 = self._detail_cache.get(cache_key)
            if cached2 is not None:
                return cached2
            if r:
                from_redis2 = await self._get_cached_model(cache_key, redis_key, model_cls)
                if from_redis2 is not None:
                    return from_redis2

            if not r:
                try:
                    model = await compute()
                except Exception:
                    return None
                if model is not None:
                    self._detail_cache.set(cache_key, model)
                return model

            lock_key = self._redis_lock_key(redis_key)
            token = secrets.token_hex(16).encode("utf-8")
            try:
                acquired = bool(await r.set(lock_key, token, ex=self._lock_ttl_seconds, nx=True))
            except Exception:
                acquired = False

            if acquired:
                try:
                    model = await compute()
                    if model is not None:
                        await self._set_cached_model(cache_key, redis_key, model)
                    return model
                finally:
                    try:
                        current = await r.get(lock_key)
                        if current == token:
                            await r.delete(lock_key)
                    except Exception:
                        pass

            wait_s = max(0.0, self._lock_wait_ms / 1000.0)
            poll_s = max(0.001, self._lock_poll_ms / 1000.0)
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                from_redis3 = await self._get_cached_model(cache_key, redis_key, model_cls)
                if from_redis3 is not None:
                    return from_redis3
                await asyncio.sleep(poll_s)

            try:
                model = await compute()
            except Exception:
                return None
            if model is not None:
                await self._set_cached_model(cache_key, redis_key, model)
            return model

        try:
            return await self._singleflight(cache_key, _run_once)
        except Exception:
            return None

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

    async def rollback_search_media(self, title: str, year: Optional[int], media_type: MediaType, language: str) -> Tuple[List[ScraperSearchResult], MediaType]:
        """回滚搜索（类型切换,去掉年份）"""
        self._ensure_started()

        current_type = media_type

        results = await self.search_media(title=title, year=year, media_type=current_type, language=language)
        if results:
            return results, current_type

        alt_type = MediaType.MOVIE if current_type == MediaType.TV_EPISODE else MediaType.TV_EPISODE
        logger.info(f"回滚搜索：当前类型 {current_type} 无结果，尝试切换为 {alt_type}")
        results = await self.search_media(title=title, year=year, media_type=alt_type, language=language)
        if results:
            return results, alt_type

        if year is not None:
            logger.info(f"回滚搜索：去掉年份 {year}")
            results = await self.search_media(title=title, year=None, media_type=current_type, language=language)
            if results:
                return results, current_type

            results = await self.search_media(title=title, year=None, media_type=alt_type, language=language)
            if results:
                return results, alt_type

        return [], current_type
       
    async def _call_with_timeout(self, provider: str, op: str, coro: Awaitable[Any]) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout_seconds)
        except asyncio.TimeoutError:
            logger.error(f"插件 {provider} {op} 超时")
            raise

    async def get_detail(
        self,
        best_match: ScraperSearchResult,
        media_type: MediaType,
        language: str = "",
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> Tuple[str, Optional[Any]]:
        self._ensure_started()

        provider = getattr(best_match, "provider", None)
        provider_id = getattr(best_match, "id", None)
        if not provider or provider_id is None:
            return "search_result", best_match

        plugin = self._plugins.get(provider)
        if not plugin:
            return "search_result", best_match

        lang = language or getattr(plugin, "default_language", "")

        async def get_series_details() -> Optional[ScraperSeriesDetail]:
            cache_key = self._cache_key("series", provider, lang, int(provider_id))
            redis_key = self._redis_key("series", provider, lang, int(provider_id))
            return await self._get_or_compute_cached_model(
                cache_key,
                redis_key,
                ScraperSeriesDetail,
                lambda: self._call_with_timeout(provider, "get_series_details", plugin.get_series_details(int(provider_id), lang)),
            )

        async def get_season_details() -> Any:
            if season is None:
                return None
            cache_key = self._cache_key("season", provider, lang, int(provider_id), int(season))
            redis_key = self._redis_key("season", provider, lang, int(provider_id), int(season))
            return await self._get_or_compute_cached_model(
                cache_key,
                redis_key,
                ScraperSeasonDetail,
                lambda: self._call_with_timeout(provider, "get_season_details", plugin.get_season_details(int(provider_id), int(season), lang)),
            )

        try:
            if media_type == MediaType.MOVIE:
                cache_key = self._cache_key("movie", provider, lang, int(provider_id))
                redis_key = self._redis_key("movie", provider, lang, int(provider_id))
                details_obj = await self._get_or_compute_cached_model(
                    cache_key,
                    redis_key,
                    ScraperMovieDetail,
                    lambda: self._call_with_timeout(provider, "get_movie_details", plugin.get_movie_details(int(provider_id), lang)),
                )
                if details_obj:
                    return "movie", details_obj
                return "search_result", best_match

            if media_type == MediaType.TV_EPISODE and season is not None and episode is not None:
                inflight_key = ("episode", provider, int(provider_id), int(season), int(episode), lang)
                details_obj = await self._singleflight(
                    inflight_key,
                    lambda: self._call_with_timeout(
                        provider,
                        "get_episode_details",
                        plugin.get_episode_details(int(provider_id), int(season), int(episode), lang),
                    ),
                )
                if details_obj:
                    series_task = asyncio.create_task(get_series_details())
                    season_task = asyncio.create_task(get_season_details())
                    series_res, season_res = await asyncio.gather(series_task, season_task, return_exceptions=True)
                    if not isinstance(series_res, Exception):
                        try:
                            details_obj.series = series_res
                        except Exception:
                            pass
                    if not isinstance(season_res, Exception):
                        try:
                            details_obj.season = season_res
                        except Exception:
                            pass
                    return "episode", details_obj

            details_obj = await get_series_details()
            if details_obj:
                return "series", details_obj
            return "search_result", best_match
        except Exception:
            return "search_result", best_match

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
            async with self._inflight_lock:
                self._inflight.clear()
            self._detail_cache.clear()
            logger.info("插件管理器状态已完全清空")
    
# 全局单例
scraper_manager = ScraperManager()
