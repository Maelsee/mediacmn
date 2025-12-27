import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../../logic/player_notifier.dart';
import 'components/side_panel.dart';
import 'layers/video_layer.dart';
import 'layers/gesture_layer.dart';
import 'layers/controls_layer.dart';
import 'layers/loading_layer.dart';
import 'panels/settings_panel.dart';
import 'panels/episode_panel.dart';

class PlayerLayout extends ConsumerStatefulWidget {
  final String? title;
  final List<Map<String, dynamic>> episodes;
  final int currentEpisodeIndex;
  final Function(int index)? onEpisodeSelected;
  final VoidCallback? onNext;
  final VoidCallback? onPrev;

  const PlayerLayout({
    super.key,
    this.title,
    this.episodes = const [],
    this.currentEpisodeIndex = -1,
    this.onEpisodeSelected,
    this.onNext,
    this.onPrev,
  });

  @override
  ConsumerState<PlayerLayout> createState() => _PlayerLayoutState();
}

class _PlayerLayoutState extends ConsumerState<PlayerLayout> {
  // UI 状态
  bool _uiVisible = false;
  Timer? _hideTimer;
  bool _isLocked = false;
  final TransformationController _transformController =
      TransformationController();

  // 屏幕方向状态
  bool _isLandscape = true;

  // 面板状态
  String? _activePanel; // 'settings', 'episodes', 'tracks', null

  // 设置状态
  bool _autoSkip = false;
  bool _enableHardwareAcceleration = true;

  @override
  void initState() {
    super.initState();
    _enterFullscreen();
    // 强制横屏
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    WakelockPlus.enable();
    _showUI();

    // 初始化设置
    final state = ref.read(playerProvider);
    _enableHardwareAcceleration = state.hardwareAccelerationEnabled;
  }

  @override
  void dispose() {
    _exitFullscreen();
    WakelockPlus.disable();
    _hideTimer?.cancel();
    _transformController.dispose();
    super.dispose();
  }

  void _enterFullscreen() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  void _exitFullscreen() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.portraitDown,
    ]);
  }

  void _toggleOrientation() {
    setState(() {
      _isLandscape = !_isLandscape;
    });
    if (_isLandscape) {
      SystemChrome.setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    } else {
      SystemChrome.setPreferredOrientations([
        DeviceOrientation.portraitUp,
        DeviceOrientation.portraitDown,
      ]);
    }
  }

  void _showUI() {
    setState(() => _uiVisible = true);
    _resetHideTimer();
  }

  void _hideUI() {
    if (_activePanel != null) return; // 面板打开时不隐藏
    setState(() => _uiVisible = false);
  }

  void _toggleUI() {
    if (_uiVisible) {
      _hideUI();
    } else {
      _showUI();
    }
  }

  void _resetHideTimer() {
    _hideTimer?.cancel();
    if (!_isLocked && _activePanel == null) {
      _hideTimer = Timer(const Duration(seconds: 5), _hideUI);
    }
  }

  void _onActivity() {
    if (!_uiVisible) _showUI();
    _resetHideTimer();
  }

  void _togglePanel(String panelName) {
    setState(() {
      if (_activePanel == panelName) {
        _activePanel = null;
        _resetHideTimer();
      } else {
        _activePanel = panelName;
        _hideTimer?.cancel();
        _uiVisible = true;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // 监听错误
    ref.listen(playerProvider.select((s) => s.error), (prev, next) {
      if (next != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('错误: $next'), backgroundColor: Colors.red),
        );
      }
    });

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. 视频层
          Positioned.fill(
            child: VideoLayer(transformationController: _transformController),
          ),

          // 2. 手势层
          Positioned.fill(
            child: GestureLayer(
              onTap: _toggleUI,
              onActivity: _onActivity,
            ),
          ),

          // 3. 加载层
          const Positioned.fill(
            child: LoadingLayer(),
          ),

          // 4. 控制层
          Positioned.fill(
            child: ControlsLayer(
              title: widget.title ?? '',
              visible: _uiVisible,
              isLocked: _isLocked,
              onLockToggle: () {
                setState(() => _isLocked = !_isLocked);
                if (_isLocked) {
                  _hideUI();
                } else {
                  _showUI();
                }
              },
              onSettingsTap: () => _togglePanel('settings'),
              onEpisodesTap: () => _togglePanel('episodes'),
              onTracksTap: () => _togglePanel('tracks'),
              onOrientationToggle: _toggleOrientation,
            ),
          ),

          // 5. 侧边面板 (带模态遮罩)
          if (_activePanel != null)
            Stack(
              children: [
                // 遮罩层 (点击关闭)
                Positioned.fill(
                  child: GestureDetector(
                    onTap: () => _togglePanel(_activePanel!),
                    behavior: HitTestBehavior.translucent,
                    child: Container(color: Colors.black54),
                  ),
                ),
                // 面板内容
                Positioned(
                  top: 0,
                  bottom: 0,
                  right: 0,
                  width: MediaQuery.of(context).size.width > 400
                      ? 350
                      : MediaQuery.of(context).size.width * 0.85,
                  child: _buildActivePanel(),
                ),
              ],
            ),
        ],
      ),
    );
  }

  Widget _buildActivePanel() {
    switch (_activePanel) {
      case 'settings':
        return SettingsPanel(
          autoSkip: _autoSkip,
          enableHardwareAcceleration: _enableHardwareAcceleration,
          onAutoSkipChanged: (v) => setState(() => _autoSkip = v),
          onHardwareAccelerationChanged: (v) {
            setState(() => _enableHardwareAcceleration = v);
            ref.read(playerProvider.notifier).toggleHardwareAcceleration();
          },
          onClose: () => _togglePanel('settings'),
        );
      case 'episodes':
        return EpisodePanel(
          episodes: widget.episodes,
          currentEpisodeIndex: widget.currentEpisodeIndex,
          onEpisodeSelected: (index) {
            widget.onEpisodeSelected?.call(index);
          },
          onClose: () => _togglePanel('episodes'),
        );
      case 'tracks':
        return _buildTracksPanel();
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _buildTracksPanel() {
    final state = ref.watch(playerProvider);
    final notifier = ref.read(playerProvider.notifier);

    return SidePanel(
      title: '字幕/音轨',
      child: DefaultTabController(
        length: 3,
        child: Column(
          children: [
            const TabBar(
              labelColor: Colors.blue,
              unselectedLabelColor: Colors.white70,
              indicatorColor: Colors.blue,
              tabs: [
                Tab(text: '音频'),
                Tab(text: '字幕'),
                Tab(text: '视频'),
              ],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  // 音频
                  ListView(
                    children: state.tracks.audio.map((track) {
                      return ListTile(
                        title: Text(track.title ?? track.language ?? track.id,
                            style: const TextStyle(color: Colors.white)),
                        selected: track == state.track.audio,
                        onTap: () => notifier.setAudioTrack(track),
                        trailing: track == state.track.audio
                            ? const Icon(Icons.check, color: Colors.blue)
                            : null,
                      );
                    }).toList(),
                  ),
                  // 字幕
                  ListView(
                    children: state.tracks.subtitle.map((track) {
                      return ListTile(
                        title: Text(track.title ?? track.language ?? track.id,
                            style: const TextStyle(color: Colors.white)),
                        selected: track == state.track.subtitle,
                        onTap: () => notifier.setSubtitleTrack(track),
                        trailing: track == state.track.subtitle
                            ? const Icon(Icons.check, color: Colors.blue)
                            : null,
                      );
                    }).toList(),
                  ),
                  // 视频
                  ListView(
                    children: state.tracks.video.map((track) {
                      return ListTile(
                        title: Text(track.title ?? track.language ?? track.id,
                            style: const TextStyle(color: Colors.white)),
                        selected: track == state.track.video,
                        onTap: () => notifier.setVideoTrack(track),
                        trailing: track == state.track.video
                            ? const Icon(Icons.check, color: Colors.blue)
                            : null,
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
