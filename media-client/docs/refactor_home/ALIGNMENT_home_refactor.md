# 6A工作流 - 阶段1: Align (对齐) - 媒体库首页重构

## 1. 项目上下文分析
### 1.1 现有架构
- **前端 (Flutter)**:
  - `MediaLibraryHomePage` (`media_home_page.dart`): 目前使用单一 `ListView` 混合展示，逻辑耦合度高。
  - 数据模型 (`media_models.dart`): 包含 `MediaHomeState` 等。
  - 状态管理 (Riverpod): `mediaHomeProvider` 负责加载首页数据。
  - 路由 (GoRouter): `/media/cards` 等路由处理导航。
- **后端 (FastAPI)**:
  - `/api/media/cards/home` (`routes_media.py`): 返回首页聚合数据。
  - `/api/playback/recent` (`routes_playback.py`): 获取最近观看记录。
  - `/api/playback/progress` (`routes_playback.py`): 上报播放进度。

### 1.2 关键依赖
- **前端**: `flutter_riverpod`, `go_router`, `json_annotation`.
- **后端**: `sqlmodel`, `pydantic`.

## 2. 需求理解与确认

### 2.1 原始需求
1.  **模块化重构**: 将首页拆分为独立的 Widget 模块（类型、电影、电视剧、动漫等）。
2.  **动态渲染**:
    - 基于后端 JSON 数据动态生成 Widget。
    - 遵循用户设置的顺序 (`settingsProvider.order`)。
    - 遵循用户设置的可见性 (`settingsProvider.visibility`) 和数据存在性（双重校验）。
3.  **最近观看模块增强**:
    - **独立解耦**: 作为一个独立的 Widget，实时监控状态。
    - **动态显示**: 无数据时不显示。
    - **实时更新**: 用户观看媒体时及时更新。
    - **卡片样式**:
        - 封面: 电影(backdrop), 系列(still/backdrop), 动漫/综艺/纪录片(poster/cover)。
        - 进度: `mm:ss/mm:ss` 格式。
        - 名称: 电影(title), 系列(Series + SxxExx + Title), 其他(Title + Ep)。
        - 交互: 封面中间显示播放按钮。
    - **一致性**: 与 `recent_list_page.dart` 样式保持一致。
4.  **后端适配**: 允许修改后端接口以支持上述需求。

### 2.2 边界确认
- **数据源**: 主要依赖 `/api/media/cards/home` 和 `/api/playback/recent`。
- **实时性**: "实时监控" 意味着前端需要监听播放进度的变化（可能通过 Riverpod 状态共享或事件总线），并在返回首页时自动刷新或通过 Stream 更新。考虑到 HTTP 协议，通常是在 `onResume` 或路由返回时触发刷新，或者使用轮询/WebSocket（本项目暂无 WebSocket 基础设施，倾向于路由感知刷新）。
- **样式**: 需要参考现有的 `MediaCard` 和 `recent_list_page.dart` 的实现。

### 2.3 疑问澄清点
- **Q1**: "实时监控" 的具体实现方式？
  - *假设*: 利用 Riverpod 的 `ref.watch` 机制，当播放器更新进度并保存到后端后，能够触发首页数据的刷新（例如通过 invalidate provider）。
- **Q2**: 后端接口修改范围？
  - *确认*: 主要涉及 `routes_playback.py` 的 `/recent` 接口返回字段是否满足新的卡片展示需求（如 backdrop, still path 等）。

## 3. 智能决策与澄清 (模拟)
- **决策**: 将首页拆分为 `HomeSectionWidget` 的工厂模式，根据 `sectionName` 返回对应的 Widget。
- **决策**: 最近观看模块单独封装为 `RecentWatchSection`，内部使用 `FutureBuilder` 或 `ref.watch` 监听专门的 `recentWatchProvider`。
- **决策**: 修改后端 `/api/playback/recent` 的响应模型 `HomeCardItem`，确保包含 `backdrop_path`, `still_path`, `media_type`, `season_index`, `episode_index`, `episode_title` 等字段。

## 4. 达成共识 (Consensus)
### 4.1 核心变更
1.  **前端**:
    - 新建 `lib/media_library/home_sections/` 目录。
    - 创建 `base_section.dart`, `movie_section.dart`, `tv_section.dart`, `recent_section.dart`, `genres_section.dart`.
    - 重构 `MediaLibraryHomePage` 使用 `SectionBuilder`。
    - 更新 `recent_list_page.dart` 复用新的卡片组件 `RecentMediaCard`.
2.  **后端**:
    - 更新 `schemas/media_serialization.py` 中的 `HomeCardItem` 模型。
    - 更新 `api/routes_playback.py` 中的 `recent_list` 逻辑，填充更多元数据。

### 4.2 验收标准
- [ ] 首页按用户设置顺序显示模块。
- [ ] 无数据的模块自动隐藏。
- [ ] "最近观看" 模块在有数据时显示，无数据隐藏。
- [ ] "最近观看" 卡片显示正确的封面（电影背景图/剧照）、进度条和格式化标题。
- [ ] "最近观看" 卡片有播放按钮，点击跳转播放。
- [ ] 从播放页返回首页时，"最近观看" 列表自动更新。
