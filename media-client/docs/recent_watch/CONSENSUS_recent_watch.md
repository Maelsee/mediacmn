# 共识文档：最近观看模块本地优先设计方案

## 1. 核心目标
构建一个**本地优先（Local-First）**、**多端同步**、**按媒体聚合**的最近观看记录模块。确保用户在播放返回首页时能立即看到更新，同时在多设备间保持进度一致。

## 2. 技术方案概览

### 2.1 架构分层
*   **Data Layer**:
    *   **Local Source**: Hive (`recent_watch_box`) - 存储 `LocalRecentRecord`。
    *   **Remote Source**: `ApiClient` - 调用后端 API。
    *   **Repository**: `RecentRepository` - 负责读写策略、同步逻辑、数据合并。
*   **State Layer**:
    *   `RecentNotifier` (Riverpod) - 仅与 Repository 交互，向 UI 暴露 `List<MediaItem>`。
*   **UI Layer**:
    *   `RecentMediaCard` - 消费数据展示，无需关心数据来源。

### 2.2 数据模型

#### 本地存储模型 (`LocalRecentRecord`)
```dart
class LocalRecentRecord {
  // 聚合主键：对于电影是 "movie_{id}"，对于剧集是 "tv_{id}"
  final String key; 
  
  // 基础展示信息
  final String mediaId; // 原始数字ID字符串
  final String kind; // 'movie' | 'tv'
  final String title;
  final String? posterPath;
  final String? backdropPath;
  
  // 播放状态
  final int fileId; // 具体播放的文件/集数ID
  final int positionMs;
  final int durationMs;
  final int lastUpdatedAt; // Unix Timestamp (ms)
  
  // 剧集特有信息
  final String? seriesName;
  final int? seasonIndex;
  final int? episodeIndex;
  final String? episodeTitle;
  
  // ... fromJson/toJson for Hive
}
```

### 2.3 关键流程

#### A. 播放进度更新流程 (Write Path)
当用户在播放器中产生进度更新（或停止播放）时：
1.  **构建记录**：根据当前播放的媒体信息构建 `LocalRecentRecord`。
2.  **本地写入**：立即 `put` 到 Hive Box 中，Key 为聚合 ID。
3.  **UI 通知**：Riverpod 监听到 Hive 变更（或手动触发），立即更新首页 UI。
4.  **异步同步**：后台调用 `api.updatePlaybackProgress(...)` 上报给服务器。

#### B. 列表加载流程 (Read Path)
当 App 启动或进入首页时：
1.  **加载本地**：从 Hive 读取所有记录，按 `lastUpdatedAt` 倒序排序，取前 N 条返回给 UI。
2.  **后台拉取**：静默调用 `api.getRecent()` 获取服务器最新记录。
3.  **合并策略 (Merge Strategy)**：
    *   遍历服务器返回的记录列表。
    *   对于每条记录，检查本地 Hive 是否存在。
    *   **Case 1 (Server Newer)**: `server.updatedAt > local.updatedAt` -> 更新本地 Hive，触发 UI 刷新。
    *   **Case 2 (Local Newer)**: `local.updatedAt > server.updatedAt` -> 保留本地（可能尚未同步成功），尝试加入同步队列（可选）。
    *   **Case 3 (New Item)**: 本地不存在 -> 写入本地 Hive。
    *   **Case 4 (Stale Local)**: 本地有但服务器列表没有（且本地时间较旧） -> 视为已删除或过期，从本地移除（可选，视保留策略而定）。

#### C. 聚合逻辑
*   **唯一性**：每个 Series 或 Movie 在列表中只占一个位置。
*   **更新机制**：看同一部剧的第 2 集会覆盖第 1 集的记录（因为 Key 都是 `tv_{seriesId}`），从而自动实现“显示最后观看的一集”。

## 3. 接口契约
前端需要后端 API 支持返回数据的完整性，特别是时间戳。
*   **Input (Report)**: `file_id`, `position`, `duration` (现有接口)。
*   **Output (List)**: `MediaItem` 需要包含 `updated_at` (timestamp) 用于比对。目前 `MediaItem` 中尚未明确该字段，需确认或添加。

## 4. 验收标准
1.  **即时响应**：从播放页返回首页，无需等待网络请求，卡片立即显示最新进度。
2.  **数据准确**：剧集卡片显示的是最后观看的那一集信息（SxxExx）。
3.  **多端同步**：在一个设备看了一半，打开另一个设备刷新后能看到该记录并接续播放。
4.  **离线可用**：无网络启动 App，仍能显示之前的观看记录。
