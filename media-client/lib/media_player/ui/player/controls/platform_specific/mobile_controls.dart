import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:floating/floating.dart';
import 'package:screen_brightness/screen_brightness.dart';
import 'package:flutter_volume_controller/flutter_volume_controller.dart';

import '../../../../core/state/playback_state.dart';
import '../mobile/widgets/mobile_top_bar.dart';
import '../mobile/widgets/mobile_bottom_bar.dart';
import '../mobile/widgets/mobile_center_controls.dart';
import '../mobile/panels/settings_panel.dart';
import '../mobile/panels/episode_panel.dart';
import '../mobile/panels/subtitle_panel.dart';
import '../mobile/panels/audio_panel.dart';
import '../mobile/panels/speed_panel.dart';
import '../mobile/panels/quality_panel.dart';

typedef PanelBuilder = Widget Function(
    PlaybackState state, PlaybackNotifier notifier);

class MobilePlayerControls extends StatefulWidget {
  /// 当前播放状态（来自 Riverpod）。
  final PlaybackState state;

  /// 播放控制器（来自 Riverpod）。
  final PlaybackNotifier notifier;

  /// 画中画控制器（由播放页统一创建并传入）。
  final Floating floating;

  const MobilePlayerControls({
    super.key,
    required this.state,
    required this.notifier,
    required this.floating,
  });

  @override
  State<MobilePlayerControls> createState() => _MobilePlayerControlsState();
}

class _MobilePlayerControlsState extends State<MobilePlayerControls> {
  /// 控制层自动隐藏定时器。
  Timer? _autoHideTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _scheduleAutoHide();
    });
  }

  /// 当前由播放器控制层设置的屏幕方向偏好。
  ///
  /// 用于在打开面板期间临时锁定方向，并在关闭面板后恢复到用户此前的选择。
  List<DeviceOrientation>? _preferredOrientations;

  @override
  void dispose() {
    _autoHideTimer?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant MobilePlayerControls oldWidget) {
    super.didUpdateWidget(oldWidget);

    final becameVisible =
        !oldWidget.state.controlsVisible && widget.state.controlsVisible;
    final becamePlaying = !oldWidget.state.playing && widget.state.playing;
    // 如果刚刚锁定，且当前可见，也应该安排自动隐藏
    final becameLocked = !oldWidget.state.isLocked && widget.state.isLocked;

    if (becameVisible ||
        becamePlaying ||
        (becameLocked && widget.state.controlsVisible)) {
      _scheduleAutoHide();
    }

    if (!widget.state.controlsVisible) {
      _autoHideTimer?.cancel();
    }
  }

  /// 安排控制层自动隐藏。
  void _scheduleAutoHide() {
    _autoHideTimer?.cancel();
    if (!widget.state.controlsVisible) return;

    // 播放中或锁屏状态下都需要自动隐藏
    // 锁屏状态下即使暂停也隐藏，避免遮挡画面
    final shouldAutoHide = widget.state.playing || widget.state.isLocked;
    if (!shouldAutoHide) return;

    _autoHideTimer = Timer(const Duration(seconds: 3), () {
      if (!mounted) return;
      if (!widget.state.controlsVisible) return;

      final shouldAutoHideNow = widget.state.playing || widget.state.isLocked;
      if (!shouldAutoHideNow) return;

      widget.notifier.toggleControls();
    });
  }

  @override
  Widget build(BuildContext context) {
    if (widget.state.isLocked) {
      return Stack(
        children: [
          // 锁屏状态下点击背景显示/隐藏控制层（主要是显示解锁按钮）
          GestureDetector(
            onTap: () {
              widget.notifier.toggleControls();
              _scheduleAutoHide();
            },
            behavior: HitTestBehavior.translucent,
            child: Container(color: Colors.transparent),
          ),
          if (widget.state.controlsVisible)
            MobileCenterControls(
              isLocked: true,
              onLockToggle: _toggleLock,
              onOrientationToggle: () {}, // 锁屏状态下禁用旋转按钮
            ),
        ],
      );
    }

    return Stack(
      children: [
        // 点击背景区域：显示/隐藏控制层
        GestureDetector(
          onTap: () {
            widget.notifier.toggleControls();
            _scheduleAutoHide();
          },
          behavior: HitTestBehavior.translucent,
          child: Container(color: Colors.transparent),
        ),

        // 顶部栏
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: MobileTopBar(
            title: widget.state.title ?? '',
            onBack: () => Navigator.of(context).maybePop(),
            onSettings: () => _openPanel(context, _buildSettingsPanel),
            onPip: () async {
              // 仅当系统与设备支持画中画时才触发。
              final available = await widget.floating.isPipAvailable;
              if (!available) return;
              await widget.floating.enable(
                const ImmediatePiP(aspectRatio: Rational.landscape()),
              );
            },
          ),
        ),

        // 中间控制（锁屏/旋转）
        Positioned.fill(
          child: Center(
            child: MobileCenterControls(
              isLocked: widget.state.isLocked,
              onLockToggle: _toggleLock,
              onOrientationToggle: _toggleOrientation,
            ),
          ),
        ),

        // 底部栏（进度、播放、面板入口）
        Positioned(
          bottom: 0,
          left: 0,
          right: 0,
          child: MobileBottomBar(
            isPlaying: widget.state.playing,
            position: widget.state.position,
            duration: widget.state.duration,
            buffered: widget.state.buffered,
            onPlayPause: widget.notifier.playPause,
            onSeek: widget.notifier.seek,
            onEpisodes: () => _openPanel(context, _buildEpisodePanel),
            onSpeed: () => _openPanel(context, _buildSpeedPanel),
            onQuality: () => _openPanel(context, _buildQualityPanel),
            onSubtitles: () => _openPanel(context, _buildSubtitlePanel),
            onAudios: () => _openPanel(context, _buildAudioPanel),
            speedText: '${widget.state.speed}x',
            qualityText: _getQualityText(),
          ),
        ),
      ],
    );
  }

  String _getQualityText() {
    final t = widget.state.selectedVideoTrack;
    if (t == null) return '自动';
    if (t.title != null && t.title!.isNotEmpty) return t.title!;
    if (t.w != null && t.h != null) return '${t.w}x${t.h}';
    return '自动';
  }

  void _toggleLock() {
    widget.notifier.toggleLock();
  }

  /// 切换横竖屏（仅控制系统允许的方向集合）。
  void _toggleOrientation() {
    if (MediaQuery.of(context).orientation == Orientation.portrait) {
      _setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    } else {
      _setPreferredOrientations([DeviceOrientation.portraitUp]);
    }
  }

  /// 根据当前布局决定面板的展示方式：
  /// - 竖屏：底部弹窗
  /// - 横屏/全屏：右侧抽屉
  void _openPanel(BuildContext context, PanelBuilder builder) {
    // 打开面板时隐藏控制层（注意：控制层隐藏会触发本组件从树上移除）
    widget.notifier.toggleControls();

    final size = MediaQuery.of(context).size;
    final isLandscapeLayout = size.width > size.height;
    final showSideDrawer = widget.state.isFullscreen || isLandscapeLayout;
    final wasFullscreen = widget.state.isFullscreen;

    final previousPreferred = _preferredOrientations;

    // 打开面板期间锁定方向，避免面板弹出时触发系统自动旋转
    _applyOrientationLock(showSideDrawer: showSideDrawer);

    if (!showSideDrawer) {
      // 竖屏模式：底部弹出面板
      showModalBottomSheet(
        context: context,
        backgroundColor: Colors.transparent,
        isScrollControlled: true, // 允许自定义高度
        useRootNavigator: true,
        builder: (context) => Consumer(
          builder: (context, ref, _) {
            final state = ref.watch(playbackProvider);
            final notifier = ref.read(playbackProvider.notifier);
            return Container(
              height: MediaQuery.of(context).size.height * 0.5, // 占据 60% 高度
              clipBehavior: Clip.hardEdge, // 新增：强制裁剪子组件
              decoration: const BoxDecoration(
                color: Color(0xFF1E1E1E),
                borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
              ),
              child: SafeArea(top: false, child: builder(state, notifier)),
            );
          },
        ),
      ).then((_) {
        _restoreOrientationAfterPanel(
          previousPreferred: previousPreferred,
          wasLandscapeLayout: isLandscapeLayout,
          wasFullscreen: wasFullscreen,
        );
      });
    } else {
      // 横屏/全屏模式：右侧滑入面板
      showGeneralDialog(
        context: context,
        barrierDismissible: true,
        barrierLabel: 'Dismiss',
        barrierColor: Colors.black54,
        transitionDuration: const Duration(milliseconds: 250),
        pageBuilder: (context, animation, secondaryAnimation) {
          return Consumer(
            builder: (context, ref, _) {
              final state = ref.watch(playbackProvider);
              final notifier = ref.read(playbackProvider.notifier);
              return Align(
                alignment: Alignment.centerRight,
                child: Material(
                  color: const Color(0xFF1E1E1E),
                  child: SizedBox(
                    width: 350, // 侧边栏固定宽度
                    child: builder(state, notifier),
                  ),
                ),
              );
            },
          );
        },
        transitionBuilder: (context, animation, secondaryAnimation, child) {
          return SlideTransition(
            position: Tween<Offset>(
              begin: const Offset(1, 0),
              end: Offset.zero,
            ).animate(animation),
            child: child,
          );
        },
      ).then((_) {
        _restoreOrientationAfterPanel(
          previousPreferred: previousPreferred,
          wasLandscapeLayout: isLandscapeLayout,
          wasFullscreen: wasFullscreen,
        );
      });
    }
  }

  /// 设置系统允许的屏幕方向，并记录到本地用于后续恢复。
  void _setPreferredOrientations(List<DeviceOrientation> orientations) {
    _preferredOrientations = orientations;
    SystemChrome.setPreferredOrientations(orientations);
  }

  /// 应用面板期间的方向锁。
  void _applyOrientationLock({required bool showSideDrawer}) {
    if (showSideDrawer) {
      _setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
      return;
    }
    _setPreferredOrientations([DeviceOrientation.portraitUp]);
  }

  /// 面板关闭后恢复方向策略：
  /// - 全屏：继续锁定横屏
  /// - 非全屏：恢复为系统默认（允许所有方向）
  void _restoreOrientationAfterPanel({
    required List<DeviceOrientation>? previousPreferred,
    required bool wasLandscapeLayout,
    required bool wasFullscreen,
  }) {
    if (previousPreferred != null && previousPreferred.isNotEmpty) {
      _setPreferredOrientations(previousPreferred);
      return;
    }

    if (wasFullscreen) {
      _setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
      return;
    }

    if (wasLandscapeLayout) {
      _setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
      return;
    }

    _setPreferredOrientations([DeviceOrientation.portraitUp]);
  }

  Widget _buildSettingsPanel(PlaybackState state, PlaybackNotifier notifier) {
    return SettingsPanel(
      settings: state.settings,
      onSettingsChanged: notifier.updateSettings,
      fit: state.fit,
      onFitChanged: notifier.setFit,
      playlistMode: state.playlistMode,
      onPlaylistModeChanged: notifier.setPlaylistMode,
      videoScale: state.videoScale,
      onVideoScaleChanged: (scale) {
        notifier.setVideoTransform(scale: scale, offset: Offset.zero);
      },
    );
  }

  Widget _buildEpisodePanel(PlaybackState state, PlaybackNotifier notifier) {
    final current = state.fileId ?? state.currentEpisodeFileId;
    var currentIndex = 0;
    if (current != null && state.episodes.isNotEmpty) {
      for (var i = 0; i < state.episodes.length; i++) {
        final e = state.episodes[i];
        if (e.assets.isEmpty) continue;
        if (e.assets.first.fileId == current) {
          currentIndex = i;
          break;
        }
      }
    }
    return EpisodePanel(
      episodes: state.episodes,
      loading: state.episodesLoading,
      errorText: state.episodesError,
      currentEpisodeIndex: currentIndex,
      onEpisodeSelected: (index) {
        notifier.openEpisodeAtIndex(index);
      },
      closeOnSelect: true,
    );
  }

  Widget _buildSubtitlePanel(PlaybackState state, PlaybackNotifier notifier) {
    final visibleSubtitles = state.subtitleTracks
        .where((track) => track.id != 'auto' && track.id != 'no')
        .toList(growable: false);
    final hasSubtitle = state.selectedSubtitleTrack != null &&
        state.selectedSubtitleTrack!.id != 'no';
    return SubtitlePanel(
      showSubtitles: hasSubtitle,
      onToggleShowSubtitles: (value) {
        if (!value) {
          notifier.setSubtitleTrack(SubtitleTrack.no());
        } else {
          if (visibleSubtitles.isNotEmpty) {
            notifier.setSubtitleTrack(visibleSubtitles.first);
          } else {
            notifier.setSubtitleTrack(SubtitleTrack.auto());
          }
        }
      },
      subtitles: state.subtitleTracks,
      selectedSubtitle: state.selectedSubtitleTrack ?? SubtitleTrack.auto(),
      onSubtitleSelected: notifier.setSubtitleTrack,
      fontSize: state.settings.subtitleFontSize,
      bottomPadding: state.settings.subtitleBottomPadding,
      onFontSizeChanged: (v) => notifier.updateSettings(
        state.settings.copyWith(subtitleFontSize: v),
      ),
      onBottomPaddingChanged: (v) => notifier.updateSettings(
        state.settings.copyWith(subtitleBottomPadding: v),
      ),
    );
  }

  Widget _buildAudioPanel(PlaybackState state, PlaybackNotifier notifier) {
    return AudioPanel(
      audios: state.audioTracks,
      selectedAudio: state.selectedAudioTrack,
      onAudioSelected: notifier.setAudioTrack,
    );
  }

  Widget _buildSpeedPanel(PlaybackState state, PlaybackNotifier notifier) {
    return SpeedPanel(
      currentSpeed: state.speed,
      onSpeedChanged: notifier.setSpeed,
    );
  }

  Widget _buildQualityPanel(PlaybackState state, PlaybackNotifier notifier) {
    return QualityPanel(
      qualities: state.videoTracks,
      currentQuality: state.selectedVideoTrack ?? VideoTrack.auto(),
      onQualitySelected: notifier.setVideoTrack,
    );
  }
}

class MobileGestureLayer extends StatefulWidget {
  /// 被手势层包裹的实际内容（视频画面 + 控制层等）。
  ///
  /// 说明：将手势识别放在父层后，子树仍可正常响应按钮点击。
  final Widget child;

  /// 控制层是否可见。
  ///
  /// 当控制层可见时：
  /// - 点击事件交给控制层自己处理（例如点击空白处隐藏控制层）。
  /// - 手势（亮度/音量/进度/双击）仍然需要生效。
  final bool controlsVisible;

  /// 切换控制层显示/隐藏。
  final VoidCallback onToggleControls;

  /// 双击左侧区域：快退。
  final VoidCallback onSeekBackward;

  /// 双击右侧区域：快进。
  final VoidCallback onSeekForward;

  /// 双击中间区域：播放/暂停。
  final VoidCallback onPlayPause;

  /// 当前音量（0~100）。
  final double volume;

  /// 设置音量（0~100）。
  final ValueChanged<double> onVolumeChange;

  /// 当前播放位置。
  final Duration position;

  /// 当前媒体总时长。
  final Duration duration;

  /// 进度跳转。
  final ValueChanged<Duration> onSeek;

  /// 当前倍速。
  final double speed;

  /// 设置倍速。
  final ValueChanged<double> onSetSpeed;

  /// 当前画面缩放倍数。
  final double videoScale;

  /// 当前画面位置偏移。
  final Offset videoOffset;

  /// 更新画面缩放与位置。
  final void Function(double scale, Offset offset) onVideoTransformChanged;

  const MobileGestureLayer({
    super.key,
    required this.child,
    required this.controlsVisible,
    required this.onToggleControls,
    required this.onSeekBackward,
    required this.onSeekForward,
    required this.onPlayPause,
    required this.volume,
    required this.onVolumeChange,
    required this.position,
    required this.duration,
    required this.onSeek,
    required this.speed,
    required this.onSetSpeed,
    required this.videoScale,
    required this.videoOffset,
    required this.onVideoTransformChanged,
  });

  @override
  State<MobileGestureLayer> createState() => _MobileGestureLayerState();
}

class _MobileGestureLayerState extends State<MobileGestureLayer> {
  /// 当前拖动模式。
  /// - 0：无
  /// - 1：亮度
  /// - 2：音量
  /// - 3：进度
  /// - 4：双指缩放/拖动
  int _dragMode = 0;

  /// 当前屏幕上的触点数量。
  int _pointerCount = 0;

  /// 单指手势开始时是否在左半屏。
  bool _isLeftSide = true;

  /// 拖动开始时的初始值（亮度 0~1 或音量 0~1）。
  double _startValue = 0.0;

  /// 水平拖动开始时的起始播放位置。
  Duration _startPos = Duration.zero;

  /// 水平拖动时的起始触点横坐标（用于计算总位移）。
  double _seekStartDx = 0.0;

  /// 水平拖动时的预览位置（抬手时用于最终 seek）。
  Duration _seekPreviewPos = Duration.zero;

  /// 双指缩放开始时的起始倍数。
  double _startScale = 1.0;

  /// 双指缩放过程中累计的画面偏移。
  Offset _scaleOffset = Offset.zero;

  /// 手势反馈浮层文案。
  String? _overlayText;

  /// 长按开始时的原始倍速。
  double _longPressStartSpeed = 1.0;

  /// 最近一次下发系统音量的时间。
  DateTime _lastVolumeUpdateAt = DateTime.fromMillisecondsSinceEpoch(0);

  /// 系统音量待下发值（0~1）。
  double? _pendingSystemVolume;

  /// 系统音量节流定时器。
  Timer? _systemVolumeTimer;

  /// 延迟检查并重置浮层状态，防止手势异常中断导致文案残留。
  void _checkAndResetOverlay() {
    Future.delayed(const Duration(milliseconds: 200), () {
      if (mounted &&
          _pointerCount == 0 &&
          (_overlayText != null || _dragMode != 0)) {
        setState(() {
          _overlayText = null;
          _dragMode = 0;
        });
      }
    });
  }

  @override
  void dispose() {
    _systemVolumeTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Listener(
          onPointerDown: (_) => _pointerCount++,
          onPointerUp: (_) {
            _pointerCount = _pointerCount > 0 ? _pointerCount - 1 : 0;
            // 所有触点抬起后，延迟检查并重置可能残留的浮层
            if (_pointerCount == 0) _checkAndResetOverlay();
          },
          onPointerCancel: (_) {
            _pointerCount = _pointerCount > 0 ? _pointerCount - 1 : 0;
            if (_pointerCount == 0) _checkAndResetOverlay();
          },
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTap: widget.controlsVisible ? null : widget.onToggleControls,
            onLongPressStart: (_) {
              // 长按：临时 2 倍速播放。
              _longPressStartSpeed = widget.speed;
              widget.onSetSpeed(2.0);
              setState(() {
                _overlayText = '2倍速';
              });
            },
            onLongPressCancel: () {
              // 长按取消：恢复倍速并清除文案
              widget.onSetSpeed(_longPressStartSpeed);
              setState(() {
                _overlayText = null;
              });
            },
            onLongPressEnd: (_) {
              // 松开：恢复到长按前的倍速。
              widget.onSetSpeed(_longPressStartSpeed);
              setState(() {
                _overlayText = null;
              });
            },
            onDoubleTapDown: (d) {
              final w = MediaQuery.sizeOf(context).width;

              // 双击热区：左 25% 快退，中间 50% 播放/暂停，右 25% 快进。
              if (d.localPosition.dx < w * 0.25) {
                widget.onSeekBackward();
              } else if (d.localPosition.dx > w * 0.75) {
                widget.onSeekForward();
              } else {
                widget.onPlayPause();
              }
            },
            onScaleStart: (details) async {
              final size = MediaQuery.sizeOf(context);

              // 双指：缩放 + 拖动。
              if (_pointerCount >= 2) {
                _dragMode = 4;
                _startScale = widget.videoScale;
                _scaleOffset = widget.videoOffset;
                setState(() {
                  _overlayText = '缩放: ${(_startScale * 100).toInt()}%';
                });
                return;
              }

              // 单指：根据手势方向决定“进度/亮度/音量”。
              _dragMode = 0;
              _startPos = widget.position;
              _seekPreviewPos = widget.position;
              _seekStartDx = details.focalPoint.dx;
              _isLeftSide = details.focalPoint.dx < size.width / 2;
              if (_isLeftSide) {
                try {
                  _startValue = await ScreenBrightness().application;
                } catch (_) {
                  _startValue = 0.5;
                }
              } else {
                try {
                  final v = await FlutterVolumeController.getVolume();
                  _startValue = v ?? 0.5;
                } catch (_) {
                  _startValue = 0.5;
                }
              }
            },
            onScaleUpdate: (details) async {
              final size = MediaQuery.sizeOf(context);

              if (_dragMode == 4 || _pointerCount >= 2) {
                // 双指缩放：倍数按比例缩放；位移按触点移动累加。
                final nextScale = (_startScale * details.scale).clamp(0.5, 3.0);
                final rawOffset = _scaleOffset + details.focalPointDelta;
                final nextOffset = _clampVideoOffset(
                  size: size,
                  scale: nextScale,
                  offset: rawOffset,
                );

                _scaleOffset = nextOffset;

                widget.onVideoTransformChanged(nextScale, nextOffset);
                setState(() {
                  _overlayText = '缩放: ${(nextScale * 100).toInt()}%';
                });
                return;
              }

              // 单指：用 focalPointDelta 同时覆盖竖向/横向调整。
              final dx = details.focalPointDelta.dx;
              final dy = details.focalPointDelta.dy;

              // 先根据手势方向选择模式，避免刚按下就触发调整。
              if (_dragMode == 0) {
                // 降低防抖阈值（6 -> 2），提升微小滑动的识别灵敏度。
                if ((dx.abs() + dy.abs()) < 2) return;
                if (dx.abs() > dy.abs() * 1.2) {
                  _dragMode = 3;
                } else {
                  _dragMode = _isLeftSide ? 1 : 2;
                }
              }

              if (_dragMode == 1) {
                // 亮度：上滑增加、下滑减少。
                // 优化：直接映射系统亮度 0.0 - 1.0 范围，而非基于初始值的增量累加，以解决边界无法触达的问题。
                final delta = -dy / 300;
                final newValue = (_startValue + delta).clamp(0.0, 1.0);
                _startValue = newValue; // 更新基准值，保证连续滑动的手感
                try {
                  await ScreenBrightness().setApplicationScreenBrightness(
                    newValue,
                  );
                } catch (_) {}
                setState(() {
                  _overlayText = '亮度: ${(newValue * 100).toInt()}%';
                });
              } else if (_dragMode == 2) {
                // 音量：上滑增加、下滑减少（系统媒体音量）。
                final delta = -dy / 300;
                final newValue = (_startValue + delta).clamp(0.0, 1.0);
                _startValue = newValue;
                _requestSystemVolume(newValue);
                setState(() {
                  _overlayText = '音量: ${(newValue * 100).toInt()}%';
                });
              } else if (_dragMode == 3) {
                // 进度：水平滑动映射为时间偏移。
                final width = size.width <= 0 ? 1.0 : size.width;

                // 将“总位移 / 屏幕宽度”映射为可调节的 seek 范围。
                // 说明：
                // - 全屏拖动（从左到右）至少可调 10 分钟。
                // - 若视频更长，则按总时长的 25% 作为可调范围，保证长视频也足够灵敏。
                final deltaRatio =
                    (details.focalPoint.dx - _seekStartDx) / width;
                final durationMs = widget.duration.inMilliseconds;

                // 可调范围（毫秒）：取“总时长的 25%”与“10 分钟”中的较大值。
                final rangeMs = ((durationMs * 0.25).toInt() < 10 * 60 * 1000)
                    ? 10 * 60 * 1000
                    : (durationMs * 0.25).toInt();
                final deltaMs = (deltaRatio * rangeMs).toInt();
                final newPos = _startPos + Duration(milliseconds: deltaMs);
                final clamped = newPos < Duration.zero
                    ? Duration.zero
                    : (newPos > widget.duration ? widget.duration : newPos);
                _seekPreviewPos = clamped;
                setState(() {
                  _overlayText =
                      '${_formatDuration(clamped)} / ${_formatDuration(widget.duration)}';
                });
              }
            },
            onScaleEnd: (_) {
              if (_dragMode == 3) {
                widget.onSeek(_seekPreviewPos);
              }
              _flushPendingSystemVolume();
              setState(() {
                _dragMode = 0;
                _overlayText = null;
              });
            },
            child: widget.child,
          ),
        ),
        if (_overlayText != null)
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            left: 0,
            right: 0,
            child: IgnorePointer(
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    _overlayText!,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }

  /// 限制画面拖动范围，避免拖出黑边。
  Offset _clampVideoOffset({
    required Size size,
    required double scale,
    required Offset offset,
  }) {
    if (scale <= 1.0) return Offset.zero;
    final maxDx = (scale - 1.0) * size.width / 2;
    final maxDy = (scale - 1.0) * size.height / 2;
    return Offset(
      offset.dx.clamp(-maxDx, maxDx),
      offset.dy.clamp(-maxDy, maxDy),
    );
  }

  String _formatDuration(Duration d) {
    final h = d.inHours;
    final m = d.inMinutes.remainder(60);
    final s = d.inSeconds.remainder(60);
    if (h > 0) {
      return '$h:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  /// 请求设置系统媒体音量（带节流）。
  void _requestSystemVolume(double value) {
    _pendingSystemVolume = value;

    final now = DateTime.now();
    final elapsed = now.difference(_lastVolumeUpdateAt);
    if (elapsed >= const Duration(milliseconds: 50)) {
      _flushPendingSystemVolume();
      return;
    }

    if (_systemVolumeTimer != null) return;
    _systemVolumeTimer = Timer(const Duration(milliseconds: 50), () {
      _systemVolumeTimer = null;
      _flushPendingSystemVolume();
    });
  }

  /// 立即下发待设置的系统媒体音量。
  void _flushPendingSystemVolume() {
    final value = _pendingSystemVolume;
    if (value == null) return;

    _pendingSystemVolume = null;
    _lastVolumeUpdateAt = DateTime.now();
    unawaited(FlutterVolumeController.setVolume(value).catchError((_) {}));
  }
}
