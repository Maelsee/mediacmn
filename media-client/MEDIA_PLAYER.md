# 媒体播放器插件设计方案（Media Player Plugin）

## 背景与目标
- 后端详情接口已返回可直接播放的 `playurl`，在无资产时提供默认 `source_path`。
- 现有旧页面 `media_library/player_page.dart` 已移除；播放器将以“插件”形式独立于媒体库页面实现，统一接管播放入口。
- 目标：提供跨平台、稳定、可扩展的播放器插件，支持直链与 HLS，具备清晰度、字幕、音轨、倍速、缩放、全屏、进度恢复等能力。

## 技术选型
- Flutter：Riverpod（状态）、GoRouter（路由）、Hive（本地存储）
- 播放引擎：`media_kit` / `media_kit_video` / `media_kit_libs_video`
- 后端接口：`/api/media/{id}/detail`、`/subtitles/{file_id}`，资产字段对齐 `playurl`、`path`、`source_path`。

## 架构分层
- 核心控制层
  - `MediaPlayerController`：统一播放控制 API（open/play/pause/seek/speed/scale/track/fullscreen/playlist）。
  - `PlayerState`：可观察状态（position/duration/buffering/error/tracks/subtitle/audio/quality/fullscreen）。
  - `PlayerEvents`：事件与回调（onReady/onError/onComplete/onTrackChanged）。
- 引擎适配层
  - `MediaKitAdapter`：桥接 `media_kit` 引擎，封装媒体 `open(Media)`、速率、轨道枚举与切换、事件订阅。
  - `HeadersInterceptor`：向直链/HLS请求注入 HTTP 头（鉴权、UA、Referrer 等）。
- 数据服务层
  - `ProgressStore`：使用 Hive 持久化播放进度与用户设置（倍速/缩放）。
  - `SubtitleService`：后端字幕拉取与加载，外挂与在线切换。
  - `HlsQualitySelector`：HLS 变体分析与清晰度切换（尽量无重开，保留进度）。
- UI 表现层
  - `PlayerView`：视频画布与 UI 控件层组合。
  - `ControlsOverlay`：交互控件（播放/暂停、进度条、倍速、缩放、清晰度、字幕、音轨、全屏）。
- 集成层
  - `PlayIntent`：播放入口模型（`fileId?`, `playurl?`, `path?`, `sourcePath?`, `title?`, `headers?`）。
  - `media_player_provider.dart`：Riverpod Provider 导出控制器与状态。
  - `play_route.dart`：统一路由入口 `'/play/:id'`（接管原播放路由）。

```mermaid
flowchart LR
  A[PlayIntent] --> B[MediaPlayerController]
  B --> C[MediaKitAdapter]
  B --> D[SubtitleService]
  B --> E[HlsQualitySelector]
  B --> F[ProgressStore]
  C --> G[PlayerState]
  D --> G
  E --> G
  F --> G
  G --> H[PlayerView]
  H --> I[ControlsOverlay]
  I --> B
```

## 数据模型与优先级
- `PlayIntent` 解析来源的优先级：
  1. `playurl`（后端直链，最高优先）
  2. `sourcePath`（默认主文件直链）
  3. `path`（相对路径，需拼接 `AppConfig.baseUrl + path`）
- 详情资产对齐：前端模型已支持 `AssetItem.playurl` 与 `MediaDetail.sourcePath`（参考 `media_library/media_models.dart:241` 与 `media_library/media_models.dart:115`）。

## 播放流程（概述）
1. 入口接收 `PlayIntent`，选择最佳 URL（见优先级）。
2. 通过 `MediaKitAdapter.open(Media)` 初始化播放；同步速率与缩放。
3. 拉取字幕（如 `fileId` 可用），加载轨道，枚举清晰度与音轨。
4. 恢复进度（Hive `pos_{fileId}`）；订阅事件与状态。
5. UI 控件驱动控制器，控制器更新状态，状态驱动视图刷新。

## HLS 支持
- 变体枚举：从引擎的 video tracks 或解析 m3u8 变体，生成清晰度列表。
- 清晰度切换：优先使用引擎轨道切换；必要时重新 `open` 保留当前进度。
- 片段鉴权：确保每个分片请求都携带鉴权（参考认证方案）。

## 字幕与音轨
- 字幕来源：后端 `GET /subtitles/{file_id}` 返回在线字幕列表；支持外挂文件加载。
- 轨道切换：通过引擎 `setAudioTrack`、`setSubtitleTrack` 实现，提供 UI 列表选择。

## 认证与鉴权（WebDAV/直链）
背景：存储配置中含 WebDAV 主机名、用户名与密码；后端生成的 `playurl` 指向 WebDAV/直链。客户端需要在直链或 HLS 分片请求中完成认证。

推荐优先策略（安全优先）：
1. 服务端代理（强烈推荐）
   - 增加后端 `/stream/{file_id}` 或 `/proxy/play/{file_id}`，由后端与 WebDAV 通信，注入认证并转发字节流。
   - 前端仅访问业务域名，避免泄露第三方存储凭据；Cookie/JWT 即可鉴权到后端。
   - HLS：代理同时重写 m3u8 与分片 URL，确保分片也走代理。
2. 预签名/一次性令牌（推荐）
   - 后端生成带有效期的签名 URL（或临时票据），前端拿到无需用户名/密码的直链。
   - 适合支持签名的网关/存储（如对象存储、反向代理）。
3. 客户端注入 HTTP 头（折中）
   - 在播放器引擎请求中添加 `Authorization: Basic base64(user:pass)`；对 HLS 分片同样注入。
   - 通过 `HeadersInterceptor` 在 `MediaKitAdapter` 层统一设置请求头；若引擎不支持自定义头，回退到服务端代理。
   - 账号口令仅在运行期从后端下发短期票据或加密存储，不保存在明文配置。
4. URL 嵌入凭据（不推荐，仅临时排障）
   - `https://user:pass@host/path`；存在安全与兼容问题，不作为正式方案。

实现要点：
- 后端为客户端提供“安全的播放入口”，而不是直传用户名/密码。
- 如必须客户端认证，使用短期 Token/票据（例如服务端签发一次性 Basic 值或自有 Bearer），并在引擎请求中统一注入头。
- HLS 的分片与 m3u8 请求均需同样鉴权；代理或头注入必须覆盖所有请求链路。

安全策略：
- 凭据绝不硬编码到客户端；不写入版本控制；运行期通过后端安全通道获取。
- Hive 仅保存非敏感偏好与进度；凭据或票据使用内存态或系统安全存储（必要时）。
- 日志中不打印 URL 与头中的敏感信息。

## 路由与集成
- 插件独立路由 `'/play/:id'`，参数透传 `PlayIntent` 或从详情页构造。
- 媒体库“播放”按钮改为调用插件路由；旧的 `/media/play/:id` 已移除，等插件接管。

## 里程碑与任务拆分
1. 控制器与状态（直链最小可播放）
2. 引擎适配与事件订阅（含错误恢复）
3. HLS 清晰度/字幕/音轨（列表与切换）
4. 进度与用户设置持久化（倍速/缩放）
5. 认证落地（优先后端代理；备选头注入）
6. UI 完成度与交互优化（全屏、手势、动画）
7. 接管路由与媒体库集成

## 参考与约束
- 详情模型对齐：`media-client/lib/media_library/media_models.dart:115`（`sourcePath`），`media-client/lib/media_library/media_models.dart:241`（`playurl`）。
- 路由清理：`media-client/lib/router.dart:68-84`（旧播放入口已移除）。

## 风险与备选
- 若第三方存储不支持签名或跨域访问受限，优先走后端代理；链路可控，便于统计与限流。
- 若引擎不支持头注入（取决于 `media_kit`/libmpv 能力），则无需在客户端处理鉴权，统一走后端代理。

---
本方案仅提供架构与实现路线；后续实现将按原子任务逐步落地，并在每阶段提供验证与测试。

好的，感谢你提供浏览器控制台的信息。

这次的 `403 Forbidden` 错误和上一次的认证问题原因不同。根据我从控制台日志中的分析，核心问题在于 **Referer 检查**。

### 问题分析

1.  **错误信息**: 关键的响应头是 `x-tengine-error: denied by Referer ACL`。
2.  **含义**: 这表示夸克网盘（`video-play-p-zb.drive.quark.cn`）的服务器拒绝了你的请求，因为它检查了请求的来源（`Referer`），而你的应用来源（`http://localhost:5201/`）不在其允许的列表中。
3.  **原因**: 这是一种常见的 **防盗链** 机制。服务提供商（这里是夸克网盘）为了保护其带宽资源，会限制哪些网站可以直接嵌入或链接他们的资源。当你的 Flutter Web 应用在 `localhost` 上运行时，浏览器向夸克服务器发出的请求会带上 `Referer: http://localhost:5201/` 这个头，夸克服务器识别出这不是一个被授权的来源，因此拒绝了请求。

简单来说，夸克网盘不允许你直接在他的网站之外播放这个视频链接。

### 解决方案

要解决这个问题，我们需要阻止浏览器在请求视频时发送 `Referer` 头。一个简单有效的方法是在你的 Flutter Web 应用的 `index.html` 文件中添加一个 `<meta>` 标签来改变浏览器的 `Referrer-Policy`（引用站点策略）。

我将帮你修改 `media-client/web/index.html` 文件，在 `<head>` 部分添加 `<meta name="referrer" content="no-referrer">`。

我现在就执行这个修改。
        
            
toolName: edit_file_search_replace
            
status: failed
          
            
filePath: /home/meal/Django-Web/mediacmn/media-client/web/index.html
          
          
很抱歉，我刚才的修改失败了，因为我试图定位的 `<meta name="apple-mobile-web-app-capable" content="yes">` 标签在 `index.html` 文件中不存在。

为了找到正确的插入位置，我需要先读取 `media-client/web/index.html` 文件的内容。
        
            
toolName: view_files
            
status: success
          
            
filePath: /home/meal/Django-Web/mediacmn/media-client/web/index.html
          
好的，我已经阅读了 `index.html` 的内容。我找到了一个合适的插入位置。

我将把 `<meta name="referrer" content="no-referrer">` 添加在 `<meta charset="UTF-8">` 之后。

我现在就执行这个修改。
        
            
toolName: edit_file_search_replace
            
status: success
          
            
filePath: /home/meal/Django-Web/mediacmn/media-client/web/index.html
          
changes: undefined
          
我已经成功地在 `media-client/web/index.html` 文件中添加了 `<meta name="referrer" content="no-referrer">` 标签。

**详细解释**

1.  **问题根源**: 夸克网盘的视频服务器配置了防盗链机制。它会检查HTTP请求中的 `Referer` 头部，如果请求不是来自它所允许的域名，就会返回 `403 Forbidden` 错误。在你的案例中，浏览器从 `localhost` 发起的请求包含了 `Referer: http://localhost:5201/`，这个来源未被授权，因此请求被拒绝。

2.  **解决方案**: 我通过在 `index.html` 的 `<head>` 部分添加 `<meta name="referrer" content="no-referrer">` 标签，来指示浏览器在发起任何跨域请求时都不要发送 `Referer` 头部。这样一来，夸克网盘的服务器就无法进行来源检查，从而允许视频播放。

**后续步骤**

你需要**强制刷新**你的浏览器（通常是 `Ctrl+Shift+R` 或 `Cmd+Shift+R`）以确保 `index.html` 的最新版本被加载。然后再次尝试播放视频。

如果问题依然存在，请清除浏览器缓存后重试。

如果还有其他问题，随时可以向我提问。