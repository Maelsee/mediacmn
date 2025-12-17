import 'package:flutter/material.dart';
import 'dart:async';
import 'package:flutter/services.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'player_core.dart';
import 'player_state_manager.dart';

/// 优化的播放器视图
///
/// 主要优化：
/// 1. 使用PlayerStateManager减少状态订阅
/// 2. 使用ValueListenableBuilder避免不必要的重建
/// 3. 优化手势响应和控件显示逻辑
/// 4. 减少UI层级和复杂度
class OptimizedPlayerView extends StatefulWidget {
  final PlayerCore core;
  final String? title;
  const OptimizedPlayerView({super.key, required this.core, this.title});

  @override
  State<OptimizedPlayerView> createState() => _OptimizedPlayerViewState();
}

class _OptimizedPlayerViewState extends State<OptimizedPlayerView> {
  late final PlayerStateManager _stateManager;

  // UI状态 - 独立于播放器状态管理
  bool _showControls = true;
  final double _rate = 1.0;
  bool _locked = false;
  bool _muted = false;
  double _volume = 1.0;
  double _lastVolume = 1.0;
  Timer? _hideTimer;
  final String _qualityLabel = '原画';
  final String _scaleLabel = '原画';
  AudioTrack? _currentAudio;
  SubtitleTrack? _currentSubtitle;
  bool _fullscreen = false;
  final BoxFit _fit = BoxFit.contain;

  @override
  void initState() {
    super.initState();
    _stateManager = PlayerStateManager(widget.core.player);
    WakelockPlus.enable();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    _stateManager.dispose();
    WakelockPlus.disable();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.portraitDown,
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    super.dispose();
  }

  void _togglePlay() {
    widget.core.toggle();
    _scheduleAutoHide();
  }

  void _seekRelative(Duration delta) {
    // 使用stateManager获取当前位置，减少player.state的直接访问
    final pos = _stateManager.position;
    final next = pos + delta;
    widget.core.seek(next);
    _scheduleAutoHide();
  }

  void _scheduleAutoHide() {
    _hideTimer?.cancel();
    _hideTimer = Timer(const Duration(seconds: 3), () {
      if (!mounted) return;
      setState(() => _showControls = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return GestureDetector(
          onTap: () {
            setState(() => _showControls = true);
            _scheduleAutoHide();
          },
          onDoubleTapDown: (d) {
            final x = d.localPosition.dx;
            final w = constraints.maxWidth;
            if (x < w / 2) {
              _seekRelative(const Duration(seconds: -10));
            } else {
              _seekRelative(const Duration(seconds: 10));
            }
          },
          child: Stack(
            children: [
              // 视频渲染层 - 移除不必要的FittedBox包装
              Positioned.fill(
                child: Video(
                  controller: widget.core.controller,
                  controls: (state) => const SizedBox.shrink(),
                  fit: _fit,
                ),
              ),

              // 缓冲指示器 - 使用ValueListenableBuilder
              ValueListenableBuilder<bool>(
                valueListenable: _stateManager.bufferingNotifier,
                builder: (context, isBuffering, child) {
                  return isBuffering
                      ? const Center(
                          child: SizedBox(
                            width: 42,
                            height: 42,
                            child: CircularProgressIndicator(
                              strokeWidth: 3,
                              color: Colors.white,
                            ),
                          ),
                        )
                      : const SizedBox.shrink();
                },
              ),

              // 控制层 - 使用ValueListenableBuilder减少重建
              ValueListenableBuilder<bool>(
                valueListenable: _stateManager.bufferingNotifier,
                builder: (context, isBuffering, child) {
                  return ValueListenableBuilder<Duration>(
                    valueListenable: _stateManager.positionNotifier,
                    builder: (context, position, child) {
                      return ValueListenableBuilder<Duration>(
                        valueListenable: _stateManager.durationNotifier,
                        builder: (context, duration, child) {
                          return ValueListenableBuilder<bool>(
                            valueListenable: _stateManager.playingNotifier,
                            builder: (context, isPlaying, child) {
                              return _buildControls(
                                context,
                                position: position,
                                duration: duration,
                                isPlaying: isPlaying,
                                isBuffering: isBuffering,
                              );
                            },
                          );
                        },
                      );
                    },
                  );
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildControls(
    BuildContext context, {
    required Duration position,
    required Duration duration,
    required bool isPlaying,
    required bool isBuffering,
  }) {
    return AnimatedOpacity(
      opacity: _showControls ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 200),
      child: IgnorePointer(
        ignoring: !_showControls,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 顶部栏
                _buildTopBar(),
                const Spacer(),
                // 中部播放按钮 - 只在非缓冲时显示
                if (isBuffering)
                  const SizedBox(height: 60)
                else
                  _buildCenterPlayButton(isPlaying),
                const Spacer(),
                // 底部控制条
                _buildBottomControls(position, duration),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Row(
      children: [
        IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.maybePop(context),
        ),
        Expanded(
          child: Text(
            widget.title ?? '',
            style: const TextStyle(color: Colors.white),
            overflow: TextOverflow.ellipsis,
          ),
        ),
        IconButton(
          icon: const Icon(Icons.settings, color: Colors.white),
          onPressed: () {},
        ),
      ],
    );
  }

  Widget _buildCenterPlayButton(bool isPlaying) {
    return Center(
      child: IconButton(
        iconSize: 44,
        icon: Icon(
          isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill,
          color: Colors.white,
        ),
        onPressed: _togglePlay,
      ),
    );
  }

  Widget _buildBottomControls(Duration position, Duration duration) {
    return Column(
      children: [
        // 进度条 - 优化滑块响应
        Row(
          children: [
            Text(
              _fmt(position),
              style: const TextStyle(color: Colors.white),
            ),
            Expanded(
              child: SliderTheme(
                data: SliderTheme.of(context).copyWith(
                  thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
                  trackHeight: 4,
                  overlayShape: const RoundSliderOverlayShape(overlayRadius: 12),
                ),
                child: Slider(
                  value: (duration.inMilliseconds > 0
                          ? position.inMilliseconds.clamp(0, duration.inMilliseconds)
                          : position.inMilliseconds.toDouble())
                      .toDouble(),
                  min: 0,
                  max: duration.inMilliseconds.toDouble() <= 0
                      ? 1
                      : duration.inMilliseconds.toDouble(),
                  onChanged: (v) {
                    final d = Duration(milliseconds: v.toInt());
                    // 直接更新位置而不等待
                    _stateManager.updatePosition(d);
                    widget.core.seek(d);
                  },
                  onChangeEnd: (v) {
                    // 拖拽结束后重新开始自动隐藏计时
                    _scheduleAutoHide();
                  },
                ),
              ),
            ),
            Text(
              _fmt(duration),
              style: const TextStyle(color: Colors.white),
            ),
          ],
        ),
        const SizedBox(height: 8),
        _buildControlButtons(),
      ],
    );
  }

  Widget _buildControlButtons() {
    return Row(
      children: [
        // 倍速 - 简化UI
        _buildSimpleButton('倍速', '${_rate.toStringAsFixed(1)}x', _showSpeedMenu),
        const SizedBox(width: 12),

        // 清晰度
        _buildSimpleButton('清晰度', _qualityLabel, _showQualityMenu),
        const SizedBox(width: 12),

        // 缩放
        _buildSimpleButton('缩放', _scaleLabel, _showScaleMenu),
        const Spacer(),

        // 锁屏
        IconButton(
          icon: Icon(_locked ? Icons.lock : Icons.lock_open, color: Colors.white),
          onPressed: _toggleLock,
        ),

        // 音量
        _buildVolumeControls(),

        // 全屏
        IconButton(
          icon: Icon(_fullscreen ? Icons.fullscreen_exit : Icons.fullscreen,
              color: Colors.white),
          onPressed: _toggleFullscreen,
        ),

        // 字幕和音轨 - 只在有内容时显示
        if (_stateManager.subtitleTracks.isNotEmpty)
          _buildSubtitleButton(),
        if (_stateManager.audioTracks.isNotEmpty)
          _buildAudioTrackButton(),
      ],
    );
  }

  Widget _buildSimpleButton(String title, String value, VoidCallback onTap) {
    return GestureDetector(
      onTap: () {
        onTap();
        _scheduleAutoHide();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: Colors.white.withValues(alpha: 0.4)),
        ),
        child: Text('$title $value', style: const TextStyle(color: Colors.white)),
      ),
    );
  }

  Widget _buildVolumeControls() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          icon: Icon(_muted ? Icons.volume_off : Icons.volume_up, color: Colors.white),
          onPressed: _toggleMute,
        ),
        SizedBox(
          width: 80,
          child: SliderTheme(
            data: SliderTheme.of(context).copyWith(
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 4),
              trackHeight: 2,
            ),
            child: Slider(
              value: _volume,
              min: 0.0,
              max: 1.0,
              onChanged: (v) {
                setState(() {
                  _volume = v;
                  _muted = v <= 0.0;
                });
                widget.core.setVolume(v);
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSubtitleButton() {
    return PopupMenuButton<SubtitleTrack?>(
      tooltip: '字幕',
      initialValue: _currentSubtitle,
      onSelected: (t) {
        setState(() => _currentSubtitle = t);
        if (t == null) {
          widget.core.setSubtitleNone();
        } else {
          widget.core.setSubtitleTrack(t);
        }
        _scheduleAutoHide();
      },
      itemBuilder: (_) => [
        const PopupMenuItem<SubtitleTrack?>(value: null, child: Text('无字幕')),
        ..._stateManager.subtitleTracks.map((t) => PopupMenuItem<SubtitleTrack?>(
            value: t,
            child: Text(t.language ?? t.title ?? '字幕'))),
      ],
      child: const Icon(Icons.subtitles, color: Colors.white),
    );
  }

  Widget _buildAudioTrackButton() {
    return PopupMenuButton<AudioTrack?>(
      tooltip: '音轨',
      initialValue: _currentAudio,
      onSelected: (t) {
        setState(() => _currentAudio = t);
        if (t == null) {
          widget.core.setAudioNone();
        } else {
          widget.core.setAudioTrack(t);
        }
        _scheduleAutoHide();
      },
      itemBuilder: (_) => [
        const PopupMenuItem<AudioTrack?>(value: null, child: Text('默认音轨')),
        ..._stateManager.audioTracks.map((t) => PopupMenuItem<AudioTrack?>(
            value: t,
            child: Text(t.language ?? t.title ?? '音轨'))),
      ],
      child: const Icon(Icons.audiotrack, color: Colors.white),
    );
  }

  void _showSpeedMenu() {
    // 实现倍速菜单
  }

  void _showQualityMenu() {
    // 实现清晰度菜单
  }

  void _showScaleMenu() {
    // 实现缩放菜单
  }

  void _toggleLock() {
    setState(() => _locked = !_locked);
    if (_locked) {
      SystemChrome.setPreferredOrientations(const [
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    } else {
      SystemChrome.setPreferredOrientations(const [
        DeviceOrientation.portraitUp,
        DeviceOrientation.portraitDown,
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    }
    _scheduleAutoHide();
  }

  void _toggleMute() {
    setState(() {
      _muted = !_muted;
      if (_muted) {
        _lastVolume = _volume > 0.0 ? _volume : _lastVolume;
        _volume = 0.0;
      } else {
        _volume = _lastVolume <= 0.0 ? 1.0 : _lastVolume;
      }
    });
    widget.core.setVolume(_volume);
    _scheduleAutoHide();
  }

  void _toggleFullscreen() {
    setState(() => _fullscreen = !_fullscreen);
    if (_fullscreen) {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
      SystemChrome.setPreferredOrientations(const [
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    } else {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
      SystemChrome.setPreferredOrientations(const [
        DeviceOrientation.portraitUp,
        DeviceOrientation.portraitDown,
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    }
    _scheduleAutoHide();
  }

  String _fmt(Duration d) {
    if (d.inMilliseconds <= 0) return '00:00';
    final h = d.inHours;
    final m = d.inMinutes % 60;
    final s = d.inSeconds % 60;
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }
}