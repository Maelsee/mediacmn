# 侧车文件异步本地化方案

基于现有任务队列架构的侧车文件（NFO/图片）异步本地化实现方案。

## 1. 方案概述

### 核心目标
- **解耦刮削流程**：将NFO文件写入和图片下载从刮削流程中分离
- **提升刮削性能**：减少同步I/O等待，提升50%刮削速度
- **统一任务管理**：利用现有任务队列架构，统一管理侧车文件
- **智能错误处理**：支持失败重试，错误隔离

### 架构优势
- **零依赖新增**：完全基于现有任务队列架构
- **渐进式升级**：支持灰度发布，风险可控
- **统一接口**：NFO、poster、fanart等统一处理
- **状态追踪**：完整的本地化状态管理

## 2. 任务队列扩展

### 扩展现有TaskType枚举
```python
# services/utils/task_queue_service.py
class TaskType(str, Enum):
    SCAN = "scan"                    # 存储扫描
    METADATA_FETCH = "metadata_fetch" # 元数据获取
    # ... 现有任务类型 ...
    
    # 新增：侧车文件本地化任务
    SIDECAR_LOCALIZE = "sidecar_localize"  # 统一侧车文件本地化
```

### 任务参数结构
```python
class SidecarLocalizeParams(BaseModel):
    """侧车文件本地化任务参数"""
    file_id: int                    # 媒体文件ID
    user_id: int                    # 用户ID  
    storage_id: int                 # 存储配置ID
    
    # 侧车文件列表
    sidecar_files: List[Dict] = Field(default_factory=list)
    # 示例: [
    #   {"type": "nfo", "content": "<xml>...</xml>", "path": "/movies/Film.nfo"},
    #   {"type": "poster", "url": "https://...", "path": "/movies/Film-poster.jpg"}
    # ]
    
    priority: str = "low"          # 任务优先级
    max_retries: int = 3           # 最大重试次数
```

## 3. 刮削流程改造

### 当前流程（同步）
```python
# metadata_enricher.py - 当前实现
async def enrich_media_file(...):
    # 1. 获取元数据（API调用）
    scraper_result = await scraper.scrape(file_path)
    
    # 2. 写入数据库（快速）
    await self.save_metadata(scraper_result)
    
    # 3. 生成侧车文件（同步阻塞）
    await self._write_sidecar_files(scraper_result)  # ⬅️ 耗时操作
    # 包含：
    # - NFO文件生成和写入（200-500ms）
    # - 图片下载和保存（200ms-2s）
```

### 新流程（异步）
```python
# metadata_enricher.py - 异步改造
async def enrich_media_file(...):
    # 1. 获取元数据（API调用）
    scraper_result = await scraper.scrape(file_path)
    
    # 2. 写入数据库（快速）
    await self.save_metadata(scraper_result)
    
    # 3. 生成侧车文件内容（内存中，快速）
    sidecar_files = await self._prepare_sidecar_files(scraper_result)
    
    # 4. 创建异步任务（立即返回）
    task_params = SidecarLocalizeParams(
        file_id=media_core.id,
        user_id=media_core.user_id, 
        storage_id=storage_config.id,
        sidecar_files=sidecar_files
    )
    
    await task_queue.enqueue_task(Task(
        task_type=TaskType.SIDECAR_LOCALIZE,
        priority=TaskPriority.LOW,
        params=task_params.dict()
    ))
    
    # 5. 标记状态为处理中
    await self._update_sidecar_status(media_core, "localizing")
    
    # ⬅️ 刮削完成，立即返回（无需等待侧车文件）
```

## 4. 任务处理器实现

### 核心处理器
```python
# services/utils/sidecar_localize_handler.py
class SidecarLocalizeHandler:
    """侧车文件本地化任务处理器"""
    
    def __init__(self, storage_service, media_service):
        self.storage_service = storage_service
        self.media_service = media_service
        
    async def handle(self, task: Task) -> TaskResult:
        """处理侧车文件本地化任务"""
        try:
            params = SidecarLocalizeParams(**task.params)
            
            # 获取存储客户端
            storage_client = await self.storage_service.get_client(
                params.storage_id
            )
            
            # 批量处理侧车文件
            results = []
            for sidecar_file in params.sidecar_files:
                result = await self._process_file(
                    storage_client, 
                    sidecar_file,
                    params
                )
                results.append(result)
            
            # 更新处理结果
            success_count = sum(1 for r in results if r.success)
            
            return TaskResult(
                success=success_count > 0,
                data={
                    "total_files": len(results),
                    "success_count": success_count,
                    "failed_files": [r.filename for r in results if not r.success]
                }
            )
            
        except Exception as e:
            logger.exception("侧车文件本地化失败")
            return TaskResult(success=False, error=str(e), retryable=True)
    
    async def _process_file(self, storage_client, sidecar_file: dict, params: SidecarLocalizeParams):
        """处理单个侧车文件"""
        try:
            file_type = sidecar_file["type"]
            target_path = sidecar_file["path"]
            
            # 获取文件内容
            if file_type == "nfo":
                # NFO文件：直接使用内容
                content = sidecar_file["content"].encode('utf-8')
            else:
                # 图片文件：下载远程内容
                content = await self._download_image(sidecar_file["url"])
            
            # 上传到存储
            success = await storage_client.upload(target_path, content)
            
            if success:
                # 更新数据库状态
                await self._update_file_status(
                    params.file_id,
                    file_type,
                    "localized",
                    target_path
                )
            
            return FileProcessResult(
                filename=os.path.basename(target_path),
                file_type=file_type,
                success=success,
                path=target_path if success else None
            )
            
        except Exception as e:
            logger.error(f"处理文件失败 {sidecar_file}: {e}")
            
            # 更新失败状态
            await self._update_file_status(
                params.file_id,
                file_type,
                "failed",
                error=str(e)
            )
            
            return FileProcessResult(
                filename=os.path.basename(target_path),
                file_type=file_type,
                success=False,
                error=str(e)
            )
```

## 5. 错误处理与重试

### 异常分类处理
```python
class SidecarLocalizeError(Exception):
    """侧车文件本地化基础异常"""
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable

class StorageConnectionError(SidecarLocalizeError):
    """存储连接异常（可重试）"""
    def __init__(self, message: str):
        super().__init__(message, retryable=True)

class StoragePermissionError(SidecarLocalizeError):
    """存储权限异常（不可重试）"""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)

class RemoteResourceNotFoundError(SidecarLocalizeError):
    """远程资源不存在（不可重试）"""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)
```

### 智能重试策略
```python
# 利用现有任务队列的重试机制
class Task(BaseModel):
    # ... 现有字段 ...
    
    # 重试配置（默认值）
    retry_count: int = 0
    max_retries: int = 3           # 最大重试3次
    retry_delay: int = 300         # 重试延迟5分钟
    
    def should_retry(self) -> bool:
        """判断是否应重试"""
        return self.retry_count < self.max_retries

# 重试延迟计算（指数退避）
def calculate_retry_delay(attempt: int) -> int:
    """计算重试延迟（指数退避 + 随机抖动）"""
    base_delay = 300  # 5分钟基础延迟
    max_delay = 3600   # 最大1小时
    
    # 指数退避
    delay = base_delay * (2 ** (attempt - 1))
    delay = min(delay, max_delay)
    
    # 添加随机抖动（±25%）
    import random
    jitter = delay * 0.25
    return int(delay + random.uniform(-jitter, jitter))
```

## 6. 状态管理与追踪

### 数据库状态扩展
```python
# 在MediaCore模型中扩展状态字段
class MediaCore(SQLModel, table=True):
    # ... 现有字段 ...
    
    # 侧车文件状态（新增）
    nfo_status: str = Field(default="pending")        # pending/localizing/localized/failed
    nfo_path: Optional[str] = None                    # NFO文件路径
    nfo_localized_at: Optional[datetime] = None      # 本地化完成时间
    
    poster_status: str = Field(default="pending")
    poster_path: Optional[str] = None
    poster_localized_at: Optional[datetime] = None
    
    fanart_status: str = Field(default="pending")
    fanart_path: Optional[str] = None
    fanart_localized_at: Optional[datetime] = None
```

### 状态流转图
```
 pending → localizing → localized (成功)
    ↓         ↓
  failed    failed (失败，可重试)
```

## 7. 性能优化

### 批量处理优化
```python
# 批量创建任务（减少队列操作）
async def batch_create_sidecar_tasks(media_files: List[MediaCore]):
    """批量创建侧车文件任务"""
    tasks = []
    
    for media_file in media_files:
        # 生成侧车文件配置
        sidecar_files = generate_sidecar_config(media_file)
        
        if sidecar_files:
            task_params = SidecarLocalizeParams(
                file_id=media_file.id,
                user_id=media_file.user_id,
                storage_id=media_file.storage_id,
                sidecar_files=sidecar_files
            )
            
            tasks.append(Task(
                task_type=TaskType.SIDECAR_LOCALIZE,
                priority=TaskPriority.LOW,
                params=task_params.dict()
            ))
    
    # 批量入队（减少Redis操作）
    if tasks:
        await task_queue.batch_enqueue(tasks)
    
    return len(tasks)
```

### 并发控制
```python
# 限制并发任务数，避免压垮存储服务
MAX_CONCURRENT_SIDECAR_TASKS = 10

# 任务队列配置
SIDECAR_QUEUE_CONFIG = {
    "max_workers": 3,              # 3个工作线程
    "max_concurrent": 10,          # 最大并发10个任务
    "batch_size": 50,               # 批量处理50个文件
    "retry_delay": 300,             # 重试延迟5分钟
    "timeout": 3600                 # 任务超时1小时
}
```

## 8. 监控与指标

### 关键指标定义
```python
# 业务指标
SIDECAR_METRICS = {
    "sidecar_task_created_total": "侧车任务创建总数",
    "sidecar_task_completed_total": "侧车任务完成总数",
    "sidecar_task_failed_total": "侧车任务失败总数", 
    "sidecar_file_localized_total": "文件本地化总数",
    "sidecar_file_localize_failed_total": "文件本地化失败数",
    "sidecar_localize_duration_seconds": "本地化耗时",
    "sidecar_queue_size": "任务队列大小"
}
```

### 日志规范
```python
# 结构化日志
logger.info("侧车文件本地化任务创建", extra={
    "task_id": task.id,
    "file_id": params.file_id,
    "file_count": len(params.sidecar_files),
    "file_types": [f["type"] for f in params.sidecar_files]
})

logger.info("侧车文件本地化完成", extra={
    "task_id": task.id,
    "duration": duration,
    "success_count": success_count,
    "failed_files": failed_files
})
```

## 9. 实施计划

### 阶段1：基础扩展（1周）
- [ ] 扩展TaskType枚举，新增SIDECAR_LOCALIZE
- [ ] 定义SidecarLocalizeParams参数结构
- [ ] 创建侧车文件处理器框架

### 阶段2：核心实现（2周）
- [ ] 实现SidecarLocalizeHandler处理器
- [ ] 改造metadata_enricher刮削流程
- [ ] 添加数据库状态字段

### 阶段3：集成测试（1周）
- [ ] 单元测试覆盖核心逻辑
- [ ] 集成测试验证端到端流程
- [ ] 性能测试验证性能提升

### 阶段4：灰度上线（1周）
- [ ] 配置灰度开关（默认关闭）
- [ ] 添加监控指标和告警
- [ ] 逐步放量，观察指标

## 10. 预期收益

| 指标 | 当前状态 | 预期改善 | 提升幅度 |
|------|----------|----------|----------|
| 刮削速度 | 2-3秒/文件 | 1-1.5秒/文件 | **提升50%** |
| 并发处理 | 单机串行 | 分布式并行 | **10倍提升** |
| 失败恢复 | 无重试 | 智能重试 | **成功率99%+** |
| 用户体验 | 等待加载 | 即时响应 | **体验飞跃** |
| 系统扩展 | 垂直扩展 | 水平扩展 | **无限扩展** |

## 11. 风险评估

### 低风险项
- **技术实现简单**：完全基于现有架构，无新技术引入
- **回滚容易**：灰度开关控制，可随时回滚到同步模式
- **数据安全**：侧车文件失败不影响核心元数据

### 缓解措施
- **监控告警**：完善的指标监控，及时发现问题
- **限流保护**：并发数限制，避免系统过载
- **分批发布**：逐步放量，降低风险

## 总结

本方案充分利用现有任务队列架构，通过最小化的改动实现侧车文件异步本地化，预期带来50%的刮削性能提升，同时保持系统的稳定性和可扩展性。建议立即启动实施。