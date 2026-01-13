import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:window_manager/window_manager.dart';

import '../core/state/playback_state.dart';
import '../ui/player/overlays/error_overlay.dart';
import '../ui/player/overlays/loading_overlay.dart';
import '../utils/player_utils.dart';
import 'desktop_player_overlay_panels.dart';
import 'desktop_player_side_panel.dart';

enum _OverlayKind {
  none,
  volume,
  subtitles,
  audioTracks,
  quality,
  speed,
  settings,
}

class DesktopPlayerWindowLayout extends ConsumerStatefulWidget {
  const DesktopPlayerWindowLayout({super.key});

  @override
  ConsumerState<DesktopPlayerWindowLayout> createState() =>
      _DesktopPlayerWindowLayoutState();
}

class _DesktopPlayerWindowLayoutState
    extends ConsumerState<DesktopPlayerWindowLayout> {
  bool _sidePanelVisible = false;
  _OverlayKind _overlay = _OverlayKind.none;

  Timer? _hideTimer;
  double _volume = 100.0;

  @override
  void dispose() {
    _hideTimer?.cancel();
    super.dispose();
  }

  void _showControlsTemporarily() {
    ref.read(playbackProvider.notifier).showControls();
    _hideTimer?.cancel();
    _hideTimer = Timer(const Duration(seconds: 3), () {
      if (!mounted) return;
      ref.read(playbackProvider.notifier).hideControls();
      setState(() => _overlay = _OverlayKind.none);
    });
  }

  void _toggleSidePanel() {
    setState(() {
      _sidePanelVisible = !_sidePanelVisible;
      _overlay = _OverlayKind.none;
    });
    _showControlsTemporarily();
  }

  void _toggleOverlay(_OverlayKind kind) {
    setState(() {
      _overlay = _overlay == kind ? _OverlayKind.none : kind;
    });
    _showControlsTemporarily();
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(playbackProvider);
    final notifier = ref.read(playbackProvider.notifier);
    final service = ref.watch(playerServiceProvider);

    final controller = service.videoController;

    const subtitleConfig = SubtitleViewConfiguration(
      style: TextStyle(
        height: 1.25,
        fontSize: 34,
        color: Color(0xffffffff),
        backgroundColor: Colors.transparent,
        shadows: [
          Shadow(
            color: Color(0xaa000000),
            offset: Offset(2.0, 2.0),
            blurRadius: 2.0,
          ),
        ],
      ),
      padding: EdgeInsets.only(bottom: 48.0),
    );

    final overlayPanel = switch (_overlay) {
      _OverlayKind.volume => DesktopVolumeOverlayPanel(
          volume: _volume,
          onVolumeChanged: (v) async {
            setState(() => _volume = v);
            await notifier.setVolume(v);
            _showControlsTemporarily();
          },
        ),
      _OverlayKind.subtitles => DesktopSubtitleOverlayPanel(
          state: s,
          onSelect: notifier.setSubtitleTrack,
        ),
      _OverlayKind.speed => DesktopSpeedOverlayPanel(
          speed: s.speed,
          onSelect: notifier.setSpeed,
        ),
      _OverlayKind.audioTracks => DesktopAudioTrackOverlayPanel(
          state: s,
          onSelect: notifier.setAudioTrack,
        ),
      _OverlayKind.quality => DesktopQualityOverlayPanel(
          state: s,
          onSelect: (q) async {
            // TODO: 实现画质切换逻辑
            _showControlsTemporarily();
          },
        ),
      _OverlayKind.settings => DesktopSettingsOverlayPanel(
          settings: s.settings,
          onChanged: notifier.updateSettings,
        ),
      _OverlayKind.none => null,
    };

    final double? overlayWidth = switch (_overlay) {
      _OverlayKind.volume => 60,
      _OverlayKind.speed => 140,
      _OverlayKind.subtitles => 280,
      _OverlayKind.audioTracks => 240,
      _OverlayKind.quality => 140,
      _OverlayKind.settings => 320,
      _OverlayKind.none => null,
    };

    // 根据底部按钮位置估算面板的 right 偏移量
    // 布局顺序(从右往左): 全屏(40) -> 设置(40) -> 音量(40) -> 画质(72) -> 倍速(44) -> 选集(44) -> 音轨(44) -> 字幕(44)
    // 间距: 4 (之前是8)
    // padding right: 16
    final double? overlayRight = switch (_overlay) {
      _OverlayKind.settings => 16 + 40, // 设置按钮左侧附近
      _OverlayKind.volume => 16 + 40 + 40, // 音量按钮附近
      _OverlayKind.quality => 16 + 120 + 4, // 画质按钮附近
      _OverlayKind.speed => 16 + 120 + 4 + 72 + 4, // 倍速按钮附近
      // 选集 (没有 overlay)
      _OverlayKind.audioTracks =>
        16 + 120 + 4 + 72 + 4 + 44 + 4 + 44 + 4, // 音轨按钮附近
      _OverlayKind.subtitles =>
        16 + 120 + 4 + 72 + 4 + 44 + 4 + 44 + 4 + 44 + 4, // 字幕按钮附近
      _OverlayKind.none => null,
    };

    return MouseRegion(
      onHover: (_) => _showControlsTemporarily(),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          _showControlsTemporarily();
          if (_overlay != _OverlayKind.none) {
            setState(() => _overlay = _OverlayKind.none);
          }
        },
        child: Row(
          children: [
            // 左侧播放区域 (自动伸缩)
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  // 视频层
                  Positioned.fill(
                    child: Container(
                      color: Colors.black,
                      child: controller == null
                          ? const SizedBox.expand()
                          : Video(
                              controller: controller,
                              controls: NoVideoControls,
                              fit: s.fit,
                              subtitleViewConfiguration: subtitleConfig,
                            ),
                    ),
                  ),
                  // 加载/错误层
                  if (s.loading || s.buffering)
                    Positioned.fill(
                      child: LoadingOverlay(
                        progress: s.duration.inMilliseconds > 0
                            ? (s.buffered.inMilliseconds /
                                    s.duration.inMilliseconds)
                                .clamp(0.0, 1.0)
                            : null,
                      ),
                    ),
                  if (s.error != null)
                    Positioned.fill(child: ErrorOverlay(message: s.error!)),

                  // 顶部栏
                  if (s.controlsVisible)
                    Positioned(
                      left: 0,
                      right: 0,
                      top: 0,
                      child: _TopBar(
                        title: s.title ?? '',
                        onClose: () => Navigator.of(context).maybePop(),
                      ),
                    ),

                  // 底部栏
                  if (s.controlsVisible)
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      child: _BottomBar(
                        state: s,
                        onPlayPause: notifier.playPause,
                        onPrev:
                            s.hasPrevEpisode ? notifier.playPrevEpisode : null,
                        onNext:
                            s.hasNextEpisode ? notifier.playNextEpisode : null,
                        onSeek: notifier.seek,
                        onToggleEpisodes: _toggleSidePanel,
                        onToggleSubtitles: () =>
                            _toggleOverlay(_OverlayKind.subtitles),
                        onToggleSpeed: () => _toggleOverlay(_OverlayKind.speed),
                        onToggleAudioTracks: () =>
                            _toggleOverlay(_OverlayKind.audioTracks),
                        onToggleQuality: () =>
                            _toggleOverlay(_OverlayKind.quality),
                        onToggleSettings: () =>
                            _toggleOverlay(_OverlayKind.settings),
                        onToggleVolume: () =>
                            _toggleOverlay(_OverlayKind.volume),
                        onToggleFullscreen: notifier.toggleFullscreen,
                      ),
                    ),

                  // 浮动面板容器
                  DesktopOverlayPanelHost(
                    visible: s.controlsVisible && overlayPanel != null,
                    width: overlayWidth,
                    right: overlayRight,
                    child: overlayPanel ?? const SizedBox.shrink(),
                  ),

                  // 侧边栏手柄 (始终位于播放区域最右侧)
                  DesktopSidePanelHandle(
                    visible: s.controlsVisible,
                    expanded: _sidePanelVisible,
                    onToggle: _toggleSidePanel,
                  ),
                ],
              ),
            ),
            // 右侧侧边栏 (动画显示)
            AnimatedSize(
              duration: const Duration(milliseconds: 240),
              curve: Curves.easeOut,
              alignment: Alignment.centerLeft,
              child: SizedBox(
                width: _sidePanelVisible ? kDesktopSidePanelWidth : 0,
                child: DesktopPlayerSidePanel(
                  visible: _sidePanelVisible,
                  state: s,
                  onClose: () => setState(() => _sidePanelVisible = false),
                  onEpisodeTap: (index) async {
                    await notifier.openEpisodeAtIndex(index);
                    _showControlsTemporarily();
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  final String title;
  final VoidCallback onClose;

  const _TopBar({
    required this.title,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.black.withValues(alpha: 0.8),
            Colors.transparent,
          ],
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          // 窗口控制按钮组
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                tooltip: '画中画',
                onPressed: () {}, // 暂时置空，避免报错
                icon: const Icon(Icons.picture_in_picture_alt,
                    color: Colors.white, size: 20),
              ),
              IconButton(
                tooltip: '截图（占位）',
                onPressed: () {},
                icon: const Icon(Icons.camera_alt_outlined,
                    color: Colors.white, size: 20),
              ),
              const SizedBox(width: 8),
              // 窗口最小化/最大化/关闭
              IconButton(
                tooltip: '最小化',
                onPressed: () async => await windowManager.minimize(),
                icon: const Icon(Icons.remove, color: Colors.white, size: 20),
              ),
              IconButton(
                tooltip: '最大化/还原',
                onPressed: () async {
                  if (await windowManager.isMaximized()) {
                    await windowManager.unmaximize();
                  } else {
                    await windowManager.maximize();
                  }
                },
                icon: const Icon(Icons.crop_square,
                    color: Colors.white, size: 20),
              ),
              IconButton(
                tooltip: '关闭',
                onPressed: onClose,
                icon: const Icon(Icons.close, color: Colors.white, size: 20),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _BottomBar extends StatelessWidget {
  final PlaybackState state;
  final Future<void> Function() onPlayPause;
  final Future<void> Function()? onPrev;
  final Future<void> Function()? onNext;
  final Future<void> Function(Duration position) onSeek;
  final VoidCallback onToggleEpisodes;
  final VoidCallback onToggleSubtitles;
  final VoidCallback onToggleSpeed;
  final VoidCallback onToggleAudioTracks;
  final VoidCallback onToggleQuality;
  final VoidCallback onToggleSettings;
  final VoidCallback onToggleVolume;
  final VoidCallback onToggleFullscreen;

  const _BottomBar({
    required this.state,
    required this.onPlayPause,
    required this.onPrev,
    required this.onNext,
    required this.onSeek,
    required this.onToggleEpisodes,
    required this.onToggleSubtitles,
    required this.onToggleSpeed,
    required this.onToggleAudioTracks,
    required this.onToggleQuality,
    required this.onToggleSettings,
    required this.onToggleVolume,
    required this.onToggleFullscreen,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [
            Colors.black.withValues(alpha: 0.9),
            Colors.transparent,
          ],
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 进度条在最上方
          _DesktopProgressBar(
            position: state.position,
            duration: state.duration,
            buffered: state.buffered,
            onSeek: onSeek,
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              // 左侧：播放控制与时间
              IconButton(
                tooltip: state.playing ? '暂停' : '播放',
                onPressed: () => onPlayPause(),
                icon: Icon(
                  state.playing ? Icons.pause : Icons.play_arrow,
                  color: Colors.white,
                  size: 28,
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: '下一集',
                onPressed: onNext == null ? null : () => onNext!(),
                icon: const Icon(Icons.skip_next, color: Colors.white),
              ),
              const SizedBox(width: 16),
              Text(
                '${formatDuration(state.position)} / ${formatDuration(state.duration)}',
                style: const TextStyle(color: Colors.white70, fontSize: 13),
              ),
              const Spacer(),
              // 右侧：功能按钮组
              _TextActionButton(label: '字幕', onPressed: onToggleSubtitles),
              const SizedBox(width: 4),
              _TextActionButton(label: '音轨', onPressed: onToggleAudioTracks),
              const SizedBox(width: 4),
              _TextActionButton(label: '选集', onPressed: onToggleEpisodes),
              const SizedBox(width: 4),
              _TextActionButton(label: '倍速', onPressed: onToggleSpeed),
              const SizedBox(width: 4),
              _TextActionButton(label: '至臻画质', onPressed: onToggleQuality),
              const SizedBox(width: 4),
              IconButton(
                tooltip: '音量',
                onPressed: onToggleVolume,
                icon: const Icon(Icons.volume_up, color: Colors.white),
              ),
              IconButton(
                tooltip: '设置',
                onPressed: onToggleSettings,
                icon: const Icon(Icons.settings, color: Colors.white),
              ),
              IconButton(
                tooltip: '全屏',
                onPressed: onToggleFullscreen,
                icon: const Icon(Icons.fullscreen, color: Colors.white),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TextActionButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;

  const _TextActionButton({
    required this.label,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

class _DesktopProgressBar extends StatefulWidget {
  final Duration position;
  final Duration duration;
  final Duration buffered;
  final Future<void> Function(Duration position) onSeek;

  const _DesktopProgressBar({
    required this.position,
    required this.duration,
    required this.buffered,
    required this.onSeek,
  });

  @override
  State<_DesktopProgressBar> createState() => _DesktopProgressBarState();
}

class _DesktopProgressBarState extends State<_DesktopProgressBar> {
  double? _drag;

  @override
  Widget build(BuildContext context) {
    final durationMs = widget.duration.inMilliseconds;
    final posMs = widget.position.inMilliseconds;
    final bufferedMs = widget.buffered.inMilliseconds;
    final valueMs = _drag?.toInt() ?? posMs;

    return SizedBox(
      height: 20, // 增加高度以便于点击
      child: Stack(
        alignment: Alignment.centerLeft,
        children: [
          // 缓冲进度
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 0),
              overlayShape: SliderComponentShape.noOverlay,
              trackHeight: 2,
              activeTrackColor: Colors.white30,
              inactiveTrackColor: Colors.white10,
              disabledActiveTrackColor: Colors.white30,
              disabledInactiveTrackColor: Colors.white10,
            ),
            child: Slider(
              value: durationMs == 0
                  ? 0
                  : bufferedMs.clamp(0, durationMs).toDouble(),
              min: 0,
              max: durationMs == 0 ? 1 : durationMs.toDouble(),
              onChanged: null, // 禁用交互
            ),
          ),
          // 播放进度
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              trackHeight: 2,
              activeTrackColor: const Color(0xFF1F7AE0), // 主题色
              inactiveTrackColor: Colors.transparent,
              thumbColor: Colors.white,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
              overlayShape: const RoundSliderOverlayShape(overlayRadius: 12),
            ),
            child: Slider(
              value:
                  durationMs == 0 ? 0 : valueMs.clamp(0, durationMs).toDouble(),
              min: 0,
              max: durationMs == 0 ? 1 : durationMs.toDouble(),
              onChangeStart: (v) => setState(() => _drag = v),
              onChanged: (v) => setState(() => _drag = v),
              onChangeEnd: (v) async {
                setState(() => _drag = null);
                await widget.onSeek(Duration(milliseconds: v.toInt()));
              },
            ),
          ),
        ],
      ),
    );
  }
}
