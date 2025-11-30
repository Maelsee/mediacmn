# DESIGN: 扫描与丰富化解耦架构

## 1. 总体架构图
```mermaid
graph TD
    subgraph "UnifiedTaskScheduler"
        S[Scan Task Executor]
        E[Event Bus]
    end
    
    subgraph "Event Handlers"
        MH[Metadata Handler]
        DH[Delete Sync Handler]
    end
    
    subgraph "Task Queue"
        Q[Task Queue (Redis)]
    end

    S -- 1. Scan Completed --> E
    E -- 2. Publish 'scan.completed' --> MH
    E -- 2. Publish 'scan.completed' --> DH
    MH -- 3. Create Metadata Task --> Q
    DH -- 3. Create Delete Task --> Q
```

## 2. 核心组件设计

### 2.1 EventBus (事件总线)
一个简单的观察者模式实现，支持同步/异步事件分发。

**Interface**:
```python
class EventBus:
    def subscribe(self, event_type: str, handler: Callable): ...
    def publish(self, event_type: str, payload: Any): ...
```

### 2.2 Events (事件定义)
定义标准的事件数据结构。

**Event Types**:
- `SCAN_COMPLETED`: 扫描任务完成。

**Payload Schema**:
```python
@dataclass
class ScanCompletedEvent:
    task_id: str
    storage_id: int
    user_id: int
    scan_path: str
    new_file_ids: List[int]
    updated_file_ids: List[int]
    encountered_media_paths: List[str]
    scan_params: Dict[str, Any]  # 包含 enable_metadata_enrichment 等配置
    timestamp: datetime
```

### 2.3 Handlers (处理器)

#### MetadataEnrichmentHandler
- **订阅**: `SCAN_COMPLETED`
- **逻辑**: 
    1. 检查 `event.scan_params.get('enable_metadata_enrichment')`。
    2. 如果启用且有 `new_file_ids`，批量创建 `METADATA_FETCH` 任务。
    3. 调用 `task_queue_service.enqueue_task`。

#### DeleteSyncHandler
- **订阅**: `SCAN_COMPLETED`
- **逻辑**:
    1. 检查 `event.scan_params.get('enable_delete_sync')`。
    2. 如果启用，创建 `DELETE_SYNC` 任务。

## 3. 模块交互流程
1. `UnifiedTaskScheduler` 初始化时，实例化 `EventBus`。
2. 注册 `MetadataEnrichmentHandler` 和 `DeleteSyncHandler` 到 `EventBus`。
3. `_execute_scan_task` 执行完毕后，构造 `ScanCompletedEvent`。
4. 调用 `self.event_bus.publish(EventType.SCAN_COMPLETED, event)`。
5. Handlers 接收事件，执行具体的业务逻辑（创建后续任务）。

## 4. 目录结构调整
建议在 `services/event` 下创建事件相关代码，或放在 `services/task/events.py`。
考虑到规模，暂放在 `services/task/events.py` 和 `services/task/handlers.py`。
