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

### 桌面端多窗口播放器插件注册修复与架构文档重写 (2026-01-14)

**目标**：桌面端点击播放后打开独立播放窗口，确保窗口内可正常调用 `window_manager` 与 `media_kit_video`；同时完善多窗口架构设计，规避插件注册、Hive 锁冲突、窗口互相阻塞等常见坑。

**问题与原因**：
1.  **新窗口无法播放（MissingPluginException）**：
    *   现象：子窗口报 `window_manager.ensureInitialized` 与 `media_kit_video` 的 `VideoOutputManager.Create` 缺少实现。
    *   根因：`desktop_multi_window` 创建的每个窗口都是新的 Flutter 引擎；插件注册是“每引擎一次”，只注册主窗口引擎不影响子窗口引擎。
2.  **Windows 构建失败（.plugin_symlinks 缺失）**：
    *   现象：CMake 报 `flutter/ephemeral/.plugin_symlinks/<plugin>/windows` 目录不存在。
    *   根因：Windows 环境下插件链接目录生成失败（常见于开发者模式未开启、权限/安全策略或路径问题）。

**改动**：
1.  **补齐新引擎插件注册回调**：
    *   Windows：在 Runner 初始化处设置 desktop_multi_window 的新窗口回调，确保每个新引擎都会执行 `RegisterPlugins`。
    *   Linux：注册 `desktop_multi_window_plugin_set_window_created_callback`，在回调中调用 `fl_register_plugins`。
    *   macOS：设置 `FlutterMultiWindowPlugin.setOnWindowCreatedCallback`，对新控制器执行 `RegisterGeneratedPlugins`。
2.  **完善播放器多窗口设计文档**：
    *   统一阐述通信协议、初始化顺序、Hive 目录隔离与阻塞规避策略。

**验证**：
*   执行 `flutter analyze / dart format . / flutter test`（当前 Flutter 版本无 `flutter format` 命令）。

### 连续播放与最近观看选集统一优化 (2026-01-15)

**目标**：修复从“最近观看”卡片进入播放器时，连续播放模式下播完当前集不会自动跳到下一集的问题，并统一不同入口下的选集列表使用方式。

**改动**：

1.  **选集列表来源统一**：
    * 详情页入口继续通过路由 `extra.episodes` 直接传入当前季版本的 `EpisodeDetail` 列表。
    * “最近观看”入口仅携带 `fileId`，播放器在初始化时通过 `/api/media/file/{file_id}/episodes` 获取完整选集列表，并写入 `PlaybackState.episodes`，实现与详情页相同的数据结构。

2.  **当前剧集反查逻辑增强**：
    * 在 `PlaybackNotifier` 中，新增基于“任意资源 fileId”反查所属 `EpisodeDetail` 的逻辑：
      * 先按“每集首个资源 fileId”匹配；
      * 若未命中，则在该集的所有 `assets` 中查找匹配的 `fileId`。
    * 解决了从“最近观看”进入时，当前播放 `fileId` 不是首个资源导致无法找到当前剧集，从而上一集/下一集和连续播放均不可用的问题。

3.  **上一集/下一集导航修正**：
    * `_recomputeEpisodeNav` 与 `_resolveAdjacentEpisode` 在无法直接通过 `fileId` 命中“首个资源列表”索引时，会回退使用上述反查到的剧集索引计算上一集/下一集。
    * 导航开启条件从“媒体类型不为 movie”改为“存在至少两条可导航的选集 fileId”，避免后端把剧集误标为 `movie` 时导致从“最近观看”入口连续播放失效。
    * 确保无论从详情页还是“最近观看”入口进入，只要后端返回了完整选集，连续播放模式都能正确跳转到下一集。

4.  **文档同步**：
    * 在 `lib/media_player/design.md` 中补充“来源 B：后端接口拉取”说明，记录基于 `fileId` 反查所属剧集并驱动连续播放的实现细节。

**验证**：

* 通过从详情页与“最近观看”两种入口进入相同剧集，分别在播放结束时验证：
  * 连续播放模式：自动跳转到下一集；
  * 单集循环模式：当前集从头重新播放；
  * 不循环模式：播放结束后停留在完成状态，不再自动切集。

### 播放器标题格式统一优化 (2026-01-15)

**目标**：统一播放器中的标题格式，使其在以下场景保持一致且信息完整：

* 从“最近观看”卡片进入播放器时，初始标题与卡片标题语义一致；
* 从详情页点击播放进入播放器时，标题包含系列名、季信息和集标题；
* 在选集面板中切换集数后，播放器标题依然展示完整的“系列 + 季 + 集 + 集标题”信息。

**改动**：

1.  **最近观看数据模型扩展**：
    * 为 `RecentCardItem` 增加 `seriesName`、`seasonIndex`、`episodeIndex`、`episodeTitle` 字段，用于保存后端返回的原始剧集信息，而不再仅依赖已经拼好的展示名称。
    * 更新 `RecentCardItem.fromApi` 从接口字段 `series_name`、`season_index`、`episode_index`、`episode_title` 中解析并落地上述字段，同时继续使用这些字段生成卡片展示用的 `name`（例如 `剧名 S01E02 集标题`）。
    * 在合并本地进度的 `_mergeItemWithLocal` 中，将扩展字段从远端条目透传到新的 `RecentCardItem`，避免在“最近观看”数据流转过程中丢失系列与季/集信息。

2.  **路由参数补齐系列/季/集信息**：
    * 在 `RecentMediaCard` 点击续播时的 `extra.detail` 中，除了原有的 `id`、`media_type`、`name`、`poster_path` 外，额外携带：
      * `series_name`：系列名（来自 `RecentCardItem.seriesName`）；
      * `season_index`：季编号；
      * `episode_index`：集编号；
      * `episode_title`：原始集标题。
    * 播放器初始化时从 `detail` Map 中解析上述字段，并保存到内部的 `_seriesNameHint` 与 `_seasonIndexHint` 作为标题拼接的提示信息，用于在缺少完整 `MediaDetail` 的场景（如最近观看入口）构造完整标题。

3.  **标题拼接逻辑统一**：
    * 在 `PlaybackNotifier` 中重写 `_composeEpisodeTitle`：
      * 电影：继续优先使用整体标题，不追加季/集信息。
      * 剧集：统一按“系列名 + 第几季 + 第几集 + 集标题”格式拼接：
        * 系列名优先取 `MediaDetail.title`，否则取 `_seriesNameHint`，再否则退回当前 `state.title`。
        * 季信息优先通过 `state.seasonVersionId` 在 `detail.seasons[].versions[].id` 中反查季号；若查不到则退回 `_seasonIndexHint`。
        * 集信息固定使用 `EpisodeDetail.episodeNumber` 和 `EpisodeDetail.title`。
    * `_syncTitleForCurrentEpisode` 调用新的 `_composeEpisodeTitle`，保证：
      * 从详情页入口打开时，首集标题包含“系列 + 季 + 集 + 集标题”；
      * 从“最近观看”入口打开并在选集面板切换集数后，标题仍然是完整格式，而不再退化为仅显示集标题。

**效果**：

* 播放器顶部标题在“最近观看入口 + 切换选集”与“详情页入口 + 切换选集”两种路径下，都会保持统一的结构化信息展示，便于用户快速识别当前播放的是哪一部剧的第几季第几集。

## 3. 功能方案设计

### 3.1 选集列表方案

- 前端：
  - 播放入口携带 `fileId` 信息，由 `MediaPlayerPage` 通过详情接口获取当前媒体及其相关版本 / 剧集元数据。
  - 将同一剧集下的所有视频条目整理为统一的选集模型列表（包含 `fileId`、标题、集数、时长、缩略图地址等）。
  - 在 UI 层使用可滚动列表构建选集组件：
    - 横屏：通过 `EpisodePanel` 在右侧侧边面板中展示。
    - 竖屏：通过底部面板展示，限制高度为屏幕三分之一，内部使用 `ListView` 支持长列表滚动。
  - 选中某一集时，将对应 `fileId` 回传给 `MediaPlayerPage`，触发重新解析播放源并续播。
- 后端：
  - 提供基于 `fileId` 的接口，返回该文件所属媒体的完整选集信息：
    - 包含每一集的标题、集数、时长、缩略图、对应的 `fileId` 等字段。
  - 建议与当前详情接口复用数据模型，避免多次查询。

### 3.2 字幕加载方案

- 内嵌字幕：
  - 利用 `media_kit` 的轨道枚举能力，在打开媒体后枚举所有字幕轨道，并将其映射到前端的 `SubtitleTrack` 模型。
  - 通过 `MediaPlayerState.tracks.subtitle` 暴露所有可选字幕轨道，通过 `PlayerNotifier.setSubtitleTrack` 进行切换。
- 外挂字幕：
  - 通过后端提供的字幕列表接口，根据当前媒体或 `fileId` 拉取可用字幕文件（支持常见格式如 `.srt`、`.vtt`）。
  - 前端根据返回的 URL 或文件标识加载字幕内容，并注入 `media_kit` 的自定义字幕轨道中。
  - 支持在 UI 中与内嵌字幕统一展示和切换。
- 字幕样式自定义：
  - 在设置面板中预留字幕样式配置项（字体、字号、颜色、描边等），将用户配置持久化到本地存储。
  - 播放器在渲染字幕时读取这些设置，并在 `media_kit` 或自定义绘制层中应用。

### 3.3 音轨选择方案

- 轨道识别：
  - 媒体打开后，通过 `media_kit` 枚举所有音频轨道并转换为前端的 `AudioTrack` 模型，包含语言代码、标题、描述等信息。
  - 将当前选中的音轨存储在 `MediaPlayerState.track.audio` 中。
- UI 与交互：
  - 使用 `TracksPanel` 中的「音频」Tab 展示所有可用音轨，采用 `ListView + ListTile` 形式。
  - 当前选中音轨在列表中高亮并带有勾选标记。
  - 点击列表项通过 `PlayerNotifier.setAudioTrack` 切换音轨，保持当前播放进度不变。
- 语言标识：
  - 结合语言代码与标题信息，在 UI 中展示人类可读的语言名称（如 `zh-CN` 映射为「简体中文」）。
  - 在多音轨场景下，通过附加描述（如「导演评论音轨」）帮助用户快速识别。

### 3.4 4K 60fps 视频播放优化 (2026-01-20)

**背景**：移动端在播放4K 60fps视频时，用户反馈开启2倍速播放出现音画不同步和严重画面卡顿。此前的 1.5x 限速方案未能满足用户需求。

**问题分析**：
- **解码能力不足**：4K 60fps 2x 倍速要求 120fps 解码，远超大多数移动设备的硬件解码极限。
- **同步策略失效**：默认同步策略在解码严重滞后时会导致视频停滞等待，进而拖累音频或导致完全卡死。
- **渲染瓶颈**：高分辨率高帧率渲染消耗大量 GPU 资源。

**解决方案（V2 - 激进性能优化版）**：

1. **底层解码优化 (`libmpvOptions`)**：
   - 启用 **解码级丢帧 (`framedrop: decoder`)**：当解码速度落后于播放进度时，直接丢弃视频帧（包括 B 帧），优先保证音频同步和时间轴推进。
   - 启用 **非参考帧去块滤波跳过 (`vd-lavc-skiploopfilter: nonref`)**：牺牲微小的画质细节（通常在运动中不可见），换取显著的 CPU/GPU 负载降低。
   - 强制 **自动硬件解码 (`hwdec: auto`)**。

   ```dart
   configuration: const PlayerConfiguration(
     vo: 'gpu',
     libmpvOptions: {
       'hwdec': 'auto',
       'framedrop': 'decoder', // 核心优化：保同步，弃画质
       'vd-lavc-skiploopfilter': 'nonref', // 核心优化：降负载
     },
   ),
   ```

2. **策略调整**：
   - **移除倍速限制**：撤销对 4K 视频 1.5x 倍速的强制限制，允许用户使用 2.0x/3.0x。
   - **UI 提示**：将警告图标改为“性能优化模式”提示，告知用户高倍速下可能会自动降低帧率。

**实施效果**：
- **音画同步**：在 2.0x 播放 4K 60fps 视频时，音频保持完美同步，不再卡顿。
- **视觉体验**：虽然实际显示帧率可能低于 120fps（触发丢帧），但画面保持连续流动，无冻结感。
- **功能完整性**：完全恢复了高倍速播放功能。

**技术亮点**：
- 利用 `media_kit` (mpv) 强大的底层控制能力，通过参数微调解决硬件瓶颈问题，而非简单粗暴地阉割功能。

### 3.5 倍速播放音画同步优化 (2026-01-20)

**问题现象**：
- **声音比画面快**：倍速播放时音频正常推进，视频解码滞后导致画面落后
- **倍速结束后画面仍在倍速**：速度切换时音视频时钟未正确同步，视频继续保持倍速渲染

**根本原因**：
- **音频时钟主导**：mpv默认以音频时钟为主，倍速时音频推进过快
- **视频解码滞后**：高分辨率下视频解码无法跟上音频节奏  
- **同步策略失效**：默认同步参数在倍速场景下未动态调整

**解决方案（V3 - 音画同步优化版）**：

1. **动态同步策略调整**：
   - **video-sync=audio**：视频严格跟随音频时钟，确保音画同步
   - **audio-pitch-correction=no**：关闭音调修正，避免倍速音频失真
   - **framedrop=vo**：渲染级丢帧，优先保证音频流畅度
   - **video-latency-hacks=yes**：降低视频延迟，减少画面滞后

2. **缓冲区动态管理**：
   - 高速播放时减少缓冲区大小，避免缓存延迟导致的同步问题
   - 根据播放速度动态调整demuxer缓存参数

3. **代码实现**：
```dart
Future<void> setSpeed(double speed) async {
  final platform = _player.platform as dynamic;
  
  if (speed > 1.0) {
    // 高速播放时启用严格同步模式
    await platform.setProperty('video-sync', 'audio');
    await platform.setProperty('audio-pitch-correction', 'no');
    await platform.setProperty('hr-seek', 'always');
    await platform.setProperty('cache-pause', 'no');
    
    if (speed >= 2.0) {
      await platform.setProperty('framedrop', 'vo');
      await platform.setProperty('video-latency-hacks', 'yes');
      await platform.setProperty('cache', 'no');
      await platform.setProperty('demuxer-max-bytes', '50M');
    }
  } else {
    // 恢复正常速度模式
    await platform.setProperty('video-sync', 'display-resample');
    await platform.setProperty('audio-pitch-correction', 'yes');
    await platform.setProperty('framedrop', 'decoder');
    await platform.setProperty('video-latency-hacks', 'no');
    await platform.setProperty('cache', 'auto');
    await platform.setProperty('demuxer-max-bytes', '200M');
  }

  await _player.setRate(speed);
}
```

**实施效果**：
- **音画完美同步**：声音与画面严格对齐，无快慢差异
- **倍速切换平滑**：速度切换时无卡顿或同步错乱
- **音频质量保持**：关闭音调修正避免倍速音频失真
- **播放流畅稳定**：动态丢帧策略保证连续播放体验

### 3.6 字幕自定义调节功能 (2026-01-22)

**需求背景**：用户希望能自定义调节字幕的大小和垂直位置，以适应不同视频画面和个人阅读习惯。

**解决方案**：
1.  **状态管理**：在 `PlaybackSettings` 中新增 `subtitleFontSize` (默认 40.0) 和 `subtitleBottomPadding` (默认 24.0) 字段，并持久化存储。
2.  **UI 交互**：改造 `SubtitlePanel`，引入 Tab 布局：
    *   **字幕选择** Tab：保留原有的字幕轨道列表选择功能。
    *   **样式设置** Tab：新增字体大小 (20-80) 和 垂直位置 (0-200) 的调节滑块。
3.  **渲染实现**：`CommonPlayerLayout` 监听 `PlaybackSettings` 变化，动态更新 `SubtitleViewConfiguration`，实时应用样式调整。

**效果**：
*   用户可实时预览字幕大小和位置变化。
*   设置自动保存，下次播放自动应用。

### 播放器锁屏与UI体验优化 (2026-01-21)

**目标**：修复播放器锁屏状态下的交互 Bug，并优化图标显示逻辑，确保锁屏体验符合用户直觉。

**修复内容**：

1.  **锁屏旋转图标隐藏**：
    *   **问题**：锁屏状态下，虽然其他控制图标隐藏，但屏幕旋转图标仍然可见。
    *   **修复**：在 `MobileCenterControls` 中强化 `if (!isLocked)` 判断逻辑，确保锁屏时旋转图标及其文字标签完全不渲染。

2.  **锁屏图标自动隐藏**：
    *   **问题**：锁屏图标（解锁按钮）在显示后常驻屏幕，不会像其他控件一样自动消失，且暂停时无法自动隐藏。
    *   **修复**：修改 `_scheduleAutoHide` 逻辑，在检测到 `isLocked` 状态时，即使视频处于暂停状态也允许触发自动隐藏计时器，防止锁屏图标遮挡画面或造成烧屏。

3.  **锁屏点击交互优化**：
    *   **问题**：锁屏后点击屏幕无反应，无法唤出解锁按钮。
    *   **修复**：在 `MobilePlayerControls` 的锁屏分支中添加 `GestureDetector`，点击背景区域触发 `toggleControls` 并调度自动隐藏，实现“点击显示解锁按钮 -> 再次点击或超时自动隐藏”的交互闭环。

**验证**：
*   锁屏状态下，旋转图标彻底消失。
*   锁屏图标在无操作 3 秒后自动淡出。
*   点击锁屏背景可正常唤起/隐藏解锁按钮。
### 锁屏图标不自动隐藏 Bug 修复 (2026-01-21)

**问题**：虽然实现了锁屏自动隐藏逻辑，但实际测试中发现锁屏后图标依然常驻。
**原因**：`PlaybackNotifier.toggleControls` 方法中存在保护逻辑 `if (state.isLocked) return;`，导致即便自动隐藏定时器触发，也无法更新 `controlsVisible` 状态。
**修复**：移除 `toggleControls` 中的锁屏检查，允许在锁屏状态下通过定时器或点击事件改变控制层可见性。