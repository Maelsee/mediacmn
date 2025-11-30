# 需求对齐文档：最近观看记录模块设计

## 1. 原始需求分析
用户希望重新设计最近观看（Recent Watch）模块，核心诉求如下：
1.  **架构模式**：采用“本地存储为主，后端同步为辅”的策略（Local-First + Sync）。
2.  **数据范围**：
    *   首页显示 5-10 条最近观看记录。
    *   播放页返回时需实时刷新。
    *   支持多设备同步（通过后端 API）。
3.  **聚合逻辑**：
    *   以“媒体（Media）”为单位聚合（即电影或剧集系列）。
    *   对于剧集，卡片应显示最近观看的某一集信息。
    *   对于电影，卡片应显示最近观看的版本信息。
4.  **存储内容**：
    *   媒体基础信息：ID、标题、封面（Poster/Backdrop）。
    *   播放状态：文件ID、播放进度（position/duration）、最后观看时间。
    *   剧集特有：Season Index, Episode Index, Episode Title。
    *   同步字段：last_updated 时间戳。

## 2. 现有系统分析
*   **前端（Flutter）**：
    *   目前使用 `RecentNotifier` (Riverpod) 管理状态。
    *   `RecentMediaCard` 用于展示。
    *   数据模型 `MediaItem` 包含 `positionMs`, `durationMs`, `fileId` 等字段。
    *   目前逻辑似乎是混合的，首页通过 API 拉取，播放页有部分本地状态但最终依赖 API 刷新。
*   **后端（Django/FastAPI）**：
    *   已存在 `getRecent` API。
    *   已存在 `deletePlaybackProgress` API。

## 3. 关键决策点 (Questions & Decisions)
为了实现“本地为主，后端为辅”，我们需要明确以下设计细节：

1.  **本地存储选型**：
    *   *方案*：使用 Hive (NoSQL key-value database for Flutter)，已在项目中引入（见 `media_provider.dart`）。
    *   *结构*：创建一个名为 `recent_watch_box` 的 Box。

2.  **数据结构设计 (Local Schema)**：
    *   Key: `media_id` (String/Int, 统一格式)。确保同一部剧集的不同集数更新同一条记录。
    *   Value (JSON Object):
        *   `media_id`: (Primary Key)
        *   `media_kind`: 'movie' | 'tv'
        *   `title`: String
        *   `poster_path`: String
        *   `backdrop_path`: String
        *   `last_watched_file_id`: Int (用于恢复播放)
        *   `last_position_ms`: Int
        *   `duration_ms`: Int
        *   `last_updated_at`: Int (Timestamp, for sync)
        *   *TV Specific*:
            *   `season_index`: Int
            *   `episode_index`: Int
            *   `episode_title`: String
            *   `series_name`: String (if different from title)

3.  **同步机制 (Sync Strategy)**：
    *   **写入时 (On Playback Update)**：
        1.  立即写入本地 Hive。
        2.  后台异步调用 API 上报进度（Fire & Forget 或 队列重试）。
    *   **读取时 (On App Start / Home Refresh)**：
        1.  优先读取本地 Hive 数据渲染 UI（达到 0 延迟）。
        2.  后台静默调用 API 获取最新记录列表。
        3.  **合并逻辑 (Merge Logic)**：
            *   对比本地与远端的 `last_updated_at`。
            *   如果远端比本地新（例如在其他设备看了一集），更新本地 Hive 并刷新 UI。
            *   如果本地比远端新（刚看完但在同步前断网），保留本地，并尝试再次上报。

4.  **聚合策略**：
    *   剧集：用户看 S01E01 -> 记录 Key: `tv_123`, Val: `{ep: 1, pos: 50%}`。
    *   用户接着看 S01E02 -> 更新 Key: `tv_123`, Val: `{ep: 2, pos: 10%}`。
    *   列表永远只显示该剧集最后一次观看的状态。

## 4. 待确认事项
*   后端 API 是否已经支持返回 `last_updated_at` 时间戳？
*   后端 API 的 `getRecent` 是否已经按 `media_id` 聚合？（根据描述似乎是，但需要确认 `MediaItem` 结构是否满足）。
*   *目前假设后端已支持基本聚合，前端主要负责本地缓存和体验优化。*

## 5. 下一步计划
1.  设计 `LocalRecentRecord` 模型。
2.  实现 `RecentRepository` (封装 Hive + API)。
3.  重构 `RecentNotifier` 使用 Repository。
