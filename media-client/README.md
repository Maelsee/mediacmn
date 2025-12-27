# media_client

A new Flutter project.

## Development Log

### Media Detail Page UI Refinements (2025-11-26 Part 2)

**Goal**: Further refine the UI based on visual feedback, focusing on background alignment, dynamic coloring, and spacing.

**Changes**:

1.  **Dynamic Background Color**:
    *   Integrated `palette_generator` to extract the dominant color from the poster/backdrop.
    *   Updated `DetailBackground` to use this extracted color for the gradient overlay, replacing the fixed black gradient.
    *   Ensured smooth transition from the image to the background color.

2.  **Image Alignment Fix**:
    *   Set `alignment: Alignment.topCenter` for the background image to prevent the top part (e.g., heads/titles) from being cropped.
    *   Increased `DetailBackground` height to 75% of the screen height.

3.  **Layout & Spacing**:
    *   Increased the top spacing in `MediaDetailPage` (via `SliverAppBar` expanded height) to push the title and content down, revealing more of the poster art.

4.  **Visual Polish**:
    *   Changed selection highlight borders (Versions, Episodes) to `Colors.white` for better visibility and contrast.

### Media Detail Page Modularization Refactor (2025-11-26)

**Goal**: Refactor the detail page into modular widgets based on `DESIGN_AND_SPEC.md` and implement specific UI/UX enhancements.

**Changes**:

1.  **Modular Architecture**:
    *   Split `MediaDetailPage` into independent widgets in `detail_widgets.dart`:
        *   `DetailBackground`: Full-screen height with gradient overlay.
        *   `DetailTitle`: Media title display.
        *   `DetailInfo`: Metadata (rating, date, runtime, genres).
        *   `DetailOverview`: Expandable text description.
        *   `DetailCast`: Horizontal list with character names.
        *   `DetailSeasonsEpisodes`: Season dropdown and episode list with selection.
        *   `DetailVersions`: Movie version selection with quality/size info.
        *   `DetailPath`: File path display.
        *   `DetailPlayButton`: Context-aware play action.

2.  **State Management**:
    *   Used `ConsumerStatefulWidget` in `MediaDetailPage` to manage selection state (`_selectedSeasonIndex`, `_selectedEpisodeIndex`, `_selectedVersionIndex`).
    *   Passed state and callbacks to child widgets for interactivity.

3.  **UI/UX Enhancements**:
    *   **Background**: Adjusted to 2/3 screen height with a dark gradient transition from the image bottom.
    *   **Cast**: Added character names below actor names.
    *   **Episodes**: Added border selection highlighting; play button now plays the selected episode.
    *   **Overview**: Added expandable arrow icon for long text.
    *   **Versions**: Reordered before overview; implemented long card style with quality/size info and selection highlighting.

4.  **Verification**:
    *   Ran `flutter analyze` to ensure code quality and fixed deprecated API usage (`withOpacity` -> `withValues`).

### 详情页沉浸式背景改造 (2025-11-27)

**目标**：实现详情页背景图与页面内容的无缝融合，消除图片底部的割裂感，并实现背景随内容整体自然上滑的效果。

**开发记录**：

1.  **颜色提取与渐变融合**：
    *   **方案**：引入 `palette_generator` 库，异步提取背景图的主色调（优先取 `darkMutedColor`）。
    *   **实现**：在 `DetailBackground` 中使用 `LinearGradient` 创建从透明到提取色的遮罩。
    *   **难点攻克**：初期发现图片底部与纯色背景间存在细微白线（亚像素渲染导致）。通过调整 Gradient Stops（在 0.98 处提前结束渐变）并添加一个物理覆盖层（2px 高度的纯色条）完美消除缝隙。

2.  **无限延伸与整体滑动**：
    *   **初版问题**：最初使用 `SliverAppBar` 的 `flexibleSpace`，导致上滑时背景产生视差收缩效果，且纯色部分被截断，露出底层白色背景。
    *   **重构方案**：
        *   移除 `SliverAppBar` 的背景功能，改用 `SliverToBoxAdapter` 将 `DetailBackground` 作为列表的第一个元素，确保其随内容**整体上滑**，符合物理直觉。
        *   使用 `Stack` + 透明 `AppBar` 保持返回按钮悬浮。
        *   同步更新 `Scaffold` 的 `backgroundColor` 为提取色，确保背景图滑出屏幕后，视觉上依然保持“无限延伸”的深色背景。

**最终效果**：
*   背景图底部无缝过渡到提取的纯色。
*   上滑时，背景图与文字内容作为整体移动，无视差割裂。
*   向下滑动超过图片区域后，背景依然保持一致的深色，无白边。

### 媒体库首页模块化重构与最近观看功能优化 (2025-11-27)

**目标**：重构媒体库首页，实现模块化组件管理，优化最近观看功能（实时更新、样式统一、内容丰富），并提升代码的可维护性。

**实施方案**：
1.  **后端接口扩展**：
    *   修改 `media-server/api/routes_playback.py`，扩展 `HomeCardItem` 模型，增加 `backdrop_path`, `still_path`, `season_index`, `episode_index`, `episode_title`, `series_name` 等字段。
    *   更新 `recent_list` 逻辑，从数据库（MediaCore, EpisodeExt, Artwork）中获取上述信息。

2.  **前端数据模型更新**：
    *   更新 `media-client/lib/media_library/media_models.dart` 中的 `MediaItem`，添加新字段并优化 `fromJson` 方法以支持灵活的数据映射。
    *   更新 `media-client/lib/core/api_client.dart`，确保 `getRecent` 方法使用新的 `MediaItem.fromJson` 解析数据。

3.  **UI 组件开发**：
    *   创建 `RecentMediaCard` (`media-client/lib/media_library/widgets/recent_media_card.dart`)：
        *   统一采用 16:9 宽卡片设计。
        *   封面逻辑：优先使用剧照（still_path），其次背景图（backdrop_path），最后海报（poster）。
        *   内容展示：显示剧集信息（SxxExx + 标题）、播放进度、播放按钮。

### 播放器核心重构与UI焕新 (2025-12-26)

**目标**：解决播放器布局错乱及无画面问题，全面重构冗余架构，实现强制横屏、手势交互、沉浸式UI及模块化代码结构。

**实施方案**：

1.  **架构重构 (Architecture Refactor)**：
    *   **模块合并**：将原有的分散文件整合为四个核心模块：
        *   `player_source.dart`: 合并 `PlayableSource` 与 `SourceAdapter`，统一管理播放源解析逻辑。
        *   `player_engine.dart`: 合并 `PlayerCore` 与 `PlayerStateManager`，封装 `media_kit` 底层操作与状态流转。
        *   `player_ui.dart`: 整合 `VideoLayer`, `GestureLayer`, `ControlsLayer`，统一 UI 渲染逻辑。
        *   `media_player_page.dart`: 合并 `PlayPage` 与 `PlaybackReporter`，作为业务入口。
    *   **清理冗余**：删除 `optimized_player_view.dart` 及旧的 `ui/` 目录，消除死代码。

2.  **UI/UX 焕新 (UI/UX Revamp)**：
    *   **强制横屏**：进入播放页面自动切换至横屏模式，退出时恢复竖屏。
    *   **沉浸式体验**：启用 `SystemUiMode.immersiveSticky` 隐藏系统栏，配合 `WakelockPlus` 保持屏幕常亮。
    *   **手势交互**：
        *   **双击**：屏幕两侧双击分别快进/快退 10秒，中间双击播放/暂停。
        *   **滑动**：水平滑动实现精确进度调节，显示目标时间预览。
        *   **双指缩放**：集成 `InteractiveViewer` 支持视频画面无级缩放，缩放状态下显示“还原”按钮。
    *   **自动隐藏**：UI 控件在无操作 5秒后自动淡出，点击屏幕重新唤醒。

3.  **核心功能优化 (Core Improvements)**：
    *   **播放源解析**：优化 `DefaultSourceAdapter`，支持多层级（Detail/Assets/Candidates）文件ID提取与续播进度获取。
    *   **状态管理**：引入 `ValueNotifier` 替代繁琐的 Stream 监听，对播放进度更新进行 200ms 节流处理，提升 UI 性能。
    *   **进度上报**：重构 `PlaybackReporter` 为独立的心跳机制，确保播放进度准确同步至服务器。

4.  **Bug 修复**：
    *   修复 `Video` 组件在无约束布局下尺寸异常导致无画面的问题（引入 `LayoutBuilder`）。
    *   修复控制栏按钮在小屏设备上的溢出问题。
