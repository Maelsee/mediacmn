# 播放器组件架构文档

## 1. 架构概览

本次重构采用了分层架构设计，结合 Flutter Riverpod 进行状态管理，旨在提高代码的可维护性、可测试性和扩展性。

### 架构分层

*   **UI 层 (`ui/`)**: 负责界面展示和用户交互。
    *   **Common (`ui/common/`)**: 跨平台通用 UI 组件。
        *   **Layouts**: 顶层布局容器 (`PlayerLayout`)。
        *   **Layers**: 功能图层 (`VideoLayer`, `ControlsLayer`, `GestureLayer`, `LoadingLayer`)。
        *   **Panels**: 功能面板 (`SettingsPanel`, `EpisodePanel`)。
        *   **Components**: 原子组件 (`PlayerButtons`, `SidePanel`)。
    *   **Platforms (`ui/platforms/`)**: 平台特定实现 (Mobile/Desktop/Web)。
*   **逻辑层 (`logic/`)**: 负责业务逻辑和状态管理。
    *   `PlayerNotifier`: 基于 `StateNotifier` 的控制器，处理播放逻辑。
    *   `MediaPlayerState`: 不可变的状态类，包含播放器的所有状态。
*   **核心服务层 (`core/`)**: 负责底层媒体能力的封装。
    *   `MediaService`: 封装 `media_kit` 的 `Player` 实例，提供统一的播放接口。
    *   `VideoControllerService`: 管理 `media_kit_video` 的 `VideoController`，处理硬件加速。
*   **数据层 (`data/`)**: (目前复用现有 `PlayerSource`，后续可扩展)
    *   `PlayableSource`: 播放源模型。

## 2. 核心模块说明

### 2.1 状态管理 (Riverpod)

使用 `StateNotifierProvider` 管理 `MediaPlayerState`。UI 组件通过 `ref.watch(playerProvider)` 监听状态变化，通过 `ref.read(playerProvider.notifier)` 调用业务方法。

状态包括：
- 播放状态 (playing, buffering, completed)
- 进度 (position, duration)
- 音量/倍速 (volume, rate)
- 轨道信息 (tracks, current track)
- 硬件加速配置

### 2.2 核心服务 (MediaService)

`MediaService` 是对 `media_kit` 的一层薄封装，目的是隔离底层实现，方便未来替换或测试。它暴露了 `Player` 的 Stream 和控制方法。

### 2.3 UI 交互层级

`PlayerLayout` 使用 `Stack` 管理多个图层：
1.  **VideoLayer**: 最底层，显示视频画面，支持手势缩放 (`InteractiveViewer`)。
2.  **GestureLayer**: 处理全屏手势（单击、双击、滑动快进/音量/亮度）。
3.  **LoadingLayer**: 显示缓冲动画。
4.  **ControlsLayer**: 显示顶部栏、底部栏和锁定按钮。支持自动隐藏。
5.  **Panels**: 侧边弹出的功能面板 (支持点击遮罩关闭)。

### 2.4 平台适配

- **Web**: 使用统一的 `PlayerLayout`，但底层 `media_kit` 会处理 Web 端的差异。
- **Mobile**:
    - 默认进入横屏模式。
    - 支持通过按钮手动切换横竖屏。
    - 支持屏幕亮度调节和触摸手势。

## 3. 重构关键点

- **移除 `PlayerEngine`**: 不再使用 `ValueNotifier` 手动管理状态，转为 Riverpod 单向数据流。
- **组件原子化**: 将通用 UI 拆分为独立组件，并按 `common/platforms` 结构组织。
- **硬件加速管理**: 将 `VideoController` 的创建和销毁逻辑封装在 `VideoControllerService` 中。
- **手势优化**: 重写 `GestureLayer`，支持更流畅的滑动调节体验，并修复了音量调节的 scaling 问题。
- **交互增强**:
    - 修复了 UI 显示/隐藏逻辑。
    - 增加了模态窗口遮罩，支持点击空白关闭。
    - 优化了横竖屏切换体验，支持默认横屏和手动切换。

## 4. 已知问题与未来优化

- **播放列表管理**: 目前播放列表逻辑仍部分耦合在 `MediaPlayerPage` 中，未来应迁移至 `PlaylistNotifier`。
- **Web 端手势**: Web 端屏幕亮度调节不可用（已做 try-catch 处理）。浏览器端播放页使用 Riverpod 的 `ref.listen` 监听播放错误与当前文件 `fileId`，监听逻辑已移动到 `build` 方法内部以避免断言错误。
- **国际化**: 目前硬编码中文，建议后续添加 l10n 支持。

## 3. 功能方案设计

### 3.1 选集列表方案

- 前端：
  - 播放入口携带 `fileId` 信息，由 `MediaPlayerPage` 优先通过后端 `/api/media/file/{file_id}/episodes` 接口获取该文件所属剧集的完整选集列表。
  - 当后端未返回选集或接口不可用时，回退到 `detail.seasons[].episodes[].assets` 结构中解析本地选集列表，保证兼容旧数据。
  - 将选集列表整理为统一的模型（包含 `fileId`、标题、集数等），并通过 `PlayerLayout` 传递给移动端与浏览器端的 `EpisodePanel` 组件展示。
  - 选中某一集时，将对应 `fileId` 回传给 `MediaPlayerPage`，触发重新解析播放源并续播。
- 后端：
  - 提供基于 `fileId` 的接口 `/api/media/file/{file_id}/episodes`，返回该文件所属媒体的完整选集信息（包含每一集的标题、集数、对应资产及存储信息）。
  - 通过 `season_version_id` 关联一季下的所有集版本，并结合 `EpisodeExt` 等扩展表返回业务所需字段。

### 3.2 字幕加载方案

- 内嵌字幕：
  - 利用 `media_kit` 的轨道枚举能力，在打开媒体后枚举所有字幕轨道，并将其映射到前端的 `SubtitleTrack` 模型。
  - 通过 `MediaPlayerState.tracks.subtitle` 暴露所有可选字幕轨道，通过 `PlayerNotifier.setSubtitleTrack` 进行切换。
- 外挂字幕（当前实现状态）：
  - 通过后端提供的字幕列表接口 `/api/media/file/{file_id}/subtitles`，根据当前播放文件 `fileId` 拉取同目录下可用的外挂字幕文件（支持常见格式如 `.srt`、`.vtt`、`.ass` 等）。
  - 列表接口在 WebDAV/Web DNA 存储场景下为每一项拼装可浏览的完整 `url`（由后端根据存储配置生成），同时返回 `path`、`size`、`language` 等元数据。
  - **注意**：为了兼容 `media_kit` 播放器无法为外部字幕添加请求头的问题，后端会在生成 WebDAV 字幕 URL 时自动嵌入认证信息（Basic Auth），确保播放器可以直接访问受保护的字幕资源。
  - 由于部分 WebDAV 后端（如云盘回源）对“下载”请求做了额外的回调校验（需要浏览器登录态），服务端主动发起下载会被拒绝，但通过前端使用 `url` 直接访问则可以浏览。因此当前实现对 WebDAV 字幕采取“直接 URL 加载”的方案：
    - 字幕文件的真实访问权限仍由存储侧控制（如签名 URL、反向代理、回源鉴权等）。
    - 后端只负责生成可访问的 `url`，不再尝试在服务端侧下载字幕内容。
  - 前端在移动端和浏览器端统一使用 `TracksPanel` 组件，将返回的字幕文件列表在播放页的「字幕/音轨」面板中与内嵌字幕分组展示：
    - 「内嵌字幕」区：展示来自播放器轨道的字幕。
    - 「外挂字幕」区：展示来自后端接口的外挂字幕文件名。
  - 点击任意外挂字幕时，前端直接使用列表中的 `url` 构造 `SubtitleTrack.uri(url, title)`，并通过 `PlayerNotifier.setSubtitleTrack` 切换到对应外挂字幕轨道。在 WebDAV/Web DNA 存储下，这个 `url` 由存储系统保证可浏览（例如通过签名链接或中间层代理），即使服务端主动下载会被回源拒绝，前端仍可正常加载用于播放显示。
- 字幕样式自定义：
  - 在设置面板中预留字幕样式配置项（字体、字号、颜色、描边等），将用户配置持久化到本地存储。
  - 播放器在渲染字幕时读取这些设置，并在 `media_kit` 或自定义绘制层中应用。

### 3.3 音轨选择方案

- 轨道识别（当前实现状态）：
  - 媒体打开后，`PlayerNotifier` 通过订阅 `MediaService.tracksStream` 与 `trackStream`，将 `media_kit` 返回的 `Tracks` 与当前 `Track` 写入 `MediaPlayerState.tracks` 与 `MediaPlayerState.track`。
  - `tracks.audio` 列表即为所有可用音频轨道，`track.audio` 为当前选中音轨。
- UI 与交互：
  - 在移动端和浏览器端的「字幕/音轨」面板中统一复用 `TracksPanel` 组件：
    - 「音频」Tab 使用 `state.tracks.audio` 构建列表，当前选中音轨在 UI 中高亮并带有勾选标记。
    - 「字幕」Tab 展示内嵌字幕与外挂字幕列表，并支持切换。
    - 「视频」Tab 展示可用的视频轨道。
  - 点击列表项通过 `PlayerNotifier.setAudioTrack` / `setSubtitleTrack` / `setVideoTrack` 调用底层 `MediaService` 完成轨道切换，保持当前播放进度不变。
- 语言标识（规划中）：
  - 当前直接使用轨道的 `title` / `language` / `id` 字段展示，尚未做语言代码到人类可读名称的映射。
  - 后续可增加语言表，将常见语言代码（如 `zh-CN`）映射为「简体中文」，并支持额外描述（如「导演评论音轨」）以增强可读性。
