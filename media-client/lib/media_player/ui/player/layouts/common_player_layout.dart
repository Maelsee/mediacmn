import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../../../core/state/playback_state.dart';
import '../../adaptive/platform_helper.dart';
import '../controls/common/common_controls.dart';
import '../controls/platform_specific/desktop_controls.dart';
import '../controls/platform_specific/mobile_controls.dart';
import '../controls/platform_specific/web_controls.dart';
import '../overlays/error_overlay.dart';
import '../overlays/loading_overlay.dart';

class _DelayedLoadingOverlay extends StatefulWidget {
  /// 是否处于初始化/切集加载中。
  final bool loading;

  /// 是否处于缓冲中。
  final bool buffering;

  /// 缓冲进度（0~1）。
  final double? progress;

  /// 缓冲延迟显示时长。
  ///
  /// 目的：避免短暂 seek 导致的缓冲闪烁，影响观感。
  final Duration bufferingDelay;

  const _DelayedLoadingOverlay({
    required this.loading,
    required this.buffering,
    required this.progress,
    required this.bufferingDelay,
  });

  @override
  State<_DelayedLoadingOverlay> createState() => _DelayedLoadingOverlayState();
}

class _DelayedLoadingOverlayState extends State<_DelayedLoadingOverlay> {
  /// 延迟显示计时器。
  Timer? _timer;

  /// 是否允许显示缓冲覆盖层。
  bool _showBuffering = false;

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(covariant _DelayedLoadingOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _sync() {
    if (widget.loading) {
      _timer?.cancel();
      _showBuffering = true;
      return;
    }

    if (!widget.buffering) {
      _timer?.cancel();
      if (_showBuffering) {
        setState(() => _showBuffering = false);
      }
      return;
    }

    if (_showBuffering) return;
    _timer?.cancel();
    _timer = Timer(widget.bufferingDelay, () {
      if (!mounted) return;
      if (!widget.buffering) return;
      setState(() => _showBuffering = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.loading && !(_showBuffering && widget.buffering)) {
      return const SizedBox.shrink();
    }

    return LoadingOverlay(progress: widget.progress);
  }
}

class CommonPlayerLayout extends ConsumerWidget {
  /// 播放状态（来自 Riverpod）。
  final PlaybackState state;

  /// 视频控制器（由 media_kit_video 提供）。
  final VideoController? controller;

  const CommonPlayerLayout({
    super.key,
    required this.state,
    required this.controller,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final platform = Theme.of(context).platform;
    final showControls = state.controlsVisible;

    // 字幕统一样式配置：透明背景、加大字号、阴影增强可读性。
    const subtitleConfig = SubtitleViewConfiguration(
      style: TextStyle(
        height: 1.25,
        fontSize: 40,
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
      padding: EdgeInsets.only(bottom: 24.0),
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final isMobile =
            constraints.maxWidth < 600 || isMobilePlatform(platform);
        final isDesktop = isDesktopPlatform(platform);

        final content = Stack(
          fit: StackFit.expand,
          children: [
            Positioned.fill(
              child: Container(
                color: Colors.black,
                child: controller == null
                    ? const SizedBox.expand()
                    : LayoutBuilder(
                        builder: (context, constraints) {
                          // 获取视频实际尺寸
                          final width = controller!.player.state.width;
                          final height = controller!.player.state.height;
                          final hasSize = width != null &&
                              height != null &&
                              width > 0 &&
                              height > 0;

                          // 如果是 Contain 模式且能获取到尺寸，则使用 AspectRatio 包裹 Video 组件，
                          // 使 Video 组件的大小严格贴合视频画面。
                          // 这样 media_kit_video 渲染的字幕就会相对于画面位置显示，而不是固定在屏幕底部。
                          Widget videoWidget = Video(
                            controller: controller!,
                            fit: state.fit,
                            controls: NoVideoControls,
                            subtitleViewConfiguration: subtitleConfig,
                          );

                          if (state.fit == BoxFit.contain && hasSize) {
                            videoWidget = Center(
                              child: AspectRatio(
                                aspectRatio: width / height,
                                child: videoWidget,
                              ),
                            );
                          }

                          return Transform.translate(
                            offset: state.videoOffset,
                            child: Transform.scale(
                              scale: state.videoScale,
                              alignment: Alignment.center,
                              child: videoWidget,
                            ),
                          );
                        },
                      ),
              ),
            ),
            Positioned.fill(
              child: _DelayedLoadingOverlay(
                loading: state.loading,
                buffering: state.buffering,
                progress: state.duration.inMilliseconds > 0
                    ? (state.buffered.inMilliseconds /
                            state.duration.inMilliseconds)
                        .clamp(0.0, 1.0)
                    : null,
                bufferingDelay: const Duration(milliseconds: 350),
              ),
            ),
            if (state.error != null)
              Positioned.fill(child: ErrorOverlay(message: state.error!)),
            if (showControls || state.isLocked)
              Positioned.fill(
                child: _buildControlsLayer(
                  context,
                  ref,
                  isMobile: isMobile,
                  isDesktop: isDesktop,
                ),
              ),
          ],
        );

        if (isMobile && !state.isLocked) {
          return MobileGestureLayer(
            controlsVisible: showControls,
            onToggleControls: () =>
                ref.read(playbackProvider.notifier).toggleControls(),
            onSeekBackward: () => ref
                .read(playbackProvider.notifier)
                .seekRelative(const Duration(seconds: -10)),
            onSeekForward: () => ref
                .read(playbackProvider.notifier)
                .seekRelative(const Duration(seconds: 10)),
            onPlayPause: () => ref.read(playbackProvider.notifier).playPause(),
            volume: state.volume,
            onVolumeChange: ref.read(playbackProvider.notifier).setVolume,
            position: state.position,
            duration: state.duration,
            onSeek: ref.read(playbackProvider.notifier).seek,
            speed: state.speed,
            onSetSpeed: ref.read(playbackProvider.notifier).setSpeed,
            videoScale: state.videoScale,
            videoOffset: state.videoOffset,
            onVideoTransformChanged: (scale, offset) => ref
                .read(playbackProvider.notifier)
                .setVideoTransform(scale: scale, offset: offset),
            child: content,
          );
        }

        return content;
      },
    );
  }

  Widget _buildControlsLayer(
    BuildContext context,
    WidgetRef ref, {
    required bool isMobile,
    required bool isDesktop,
  }) {
    final notifier = ref.read(playbackProvider.notifier);

    final common = CommonControls(
      state: state,
      onPlayPause: notifier.playPause,
      onSeek: notifier.seek,
      onSeekRelative: notifier.seekRelative,
      onVolume: notifier.setVolume,
      onSpeed: notifier.setSpeed,
      onToggleFullscreen: notifier.toggleFullscreen,
      onToggleControls: notifier.toggleControls,
      onSelectCandidate: notifier.selectCandidate,
      onPrev: state.hasPrevEpisode ? notifier.playPrevEpisode : null,
      onNext: state.hasNextEpisode ? notifier.playNextEpisode : null,
      onOpenSettings: () => showModalBottomSheet(
        context: context,
        backgroundColor: Colors.black87,
        builder: (_) => PlaybackSettingsPanel(
          settings: state.settings,
          onChanged: notifier.updateSettings,
        ),
      ),
    );

    if (isWebPlatform()) {
      return WebPlayerControls(state: state, common: common);
    }

    if (isDesktop) {
      return DesktopPlayerControls(
        state: state,
        common: common,
        onPlayPause: () => notifier.playPause(),
        onSeekBackward: () =>
            notifier.seekRelative(const Duration(seconds: -5)),
        onSeekForward: () => notifier.seekRelative(const Duration(seconds: 5)),
      );
    }

    final floating = ref.read(floatingProvider);
    return MobilePlayerControls(
      state: state,
      notifier: notifier,
      floating: floating,
    );
  }
}
