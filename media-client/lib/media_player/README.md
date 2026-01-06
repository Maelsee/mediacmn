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
- **Web 端手势**: Web 端屏幕亮度调节不可用（已做 try-catch 处理）。
- **国际化**: 目前硬编码中文，建议后续添加 l10n 支持。

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

