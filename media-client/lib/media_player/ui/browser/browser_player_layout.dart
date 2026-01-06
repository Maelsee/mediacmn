import 'dart:async';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../logic/player_notifier.dart';
import '../common/components/side_panel.dart';
import '../common/layers/controls_layer.dart';
import '../common/layers/loading_layer.dart';
import '../common/layers/video_layer.dart';
import '../common/panels/episode_panel.dart';
import '../common/panels/settings_panel.dart';

class BrowserPlayerLayout extends ConsumerStatefulWidget {
  final String? title;
  final List<Map<String, dynamic>> episodes;
  final int currentEpisodeIndex;
  final Function(int index)? onEpisodeSelected;
  final VoidCallback? onNext;
  final VoidCallback? onPrev;

  const BrowserPlayerLayout({
    super.key,
    this.title,
    this.episodes = const [],
    this.currentEpisodeIndex = -1,
    this.onEpisodeSelected,
    this.onNext,
    this.onPrev,
  });

  @override
  ConsumerState<BrowserPlayerLayout> createState() =>
      _BrowserPlayerLayoutState();
}

class _BrowserPlayerLayoutState extends ConsumerState<BrowserPlayerLayout> {
  bool _uiVisible = true;
  Timer? _hideTimer;
  final TransformationController _transformController =
      TransformationController();

  String? _activePanel;

  bool _autoSkip = false;
  bool _enableHardwareAcceleration = true;

  @override
  void initState() {
    super.initState();
    final state = ref.read(playerProvider);
    _enableHardwareAcceleration = state.hardwareAccelerationEnabled;
    _showUI();
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    _transformController.dispose();
    super.dispose();
  }

  void _showUI() {
    setState(() => _uiVisible = true);
    _resetHideTimer();
  }

  void _hideUI() {
    if (_activePanel != null) return;
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
    if (_activePanel == null) {
      _hideTimer = Timer(const Duration(seconds: 4), _hideUI);
    }
  }

  void _onActivity() {
    if (!_uiVisible) {
      _showUI();
    } else {
      _resetHideTimer();
    }
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

  void _onPointerSignal(PointerSignalEvent event) {
    if (event is PointerScrollEvent) {
      final notifier = ref.read(playerProvider.notifier);
      final state = ref.read(playerProvider);
      final currentVolume = state.volume;
      const step = 5.0;
      final direction = event.scrollDelta.dy > 0 ? -1 : 1;
      final nextVolume =
          (currentVolume + direction * step).clamp(0.0, 100.0).toDouble();
      notifier.setVolume(nextVolume);
    }
    _onActivity();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(playerProvider.select((s) => s.error), (prev, next) {
      if (next != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('错误: $next'), backgroundColor: Colors.red),
        );
      }
    });

    return Scaffold(
      backgroundColor: Colors.black,
      body: Listener(
        onPointerSignal: _onPointerSignal,
        onPointerHover: (_) => _onActivity(),
        onPointerDown: (_) => _onActivity(),
        child: Stack(
          fit: StackFit.expand,
          children: [
            Positioned.fill(
              child: VideoLayer(
                transformationController: _transformController,
              ),
            ),
            const Positioned.fill(
              child: LoadingLayer(),
            ),
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: _toggleUI,
                child: const SizedBox.expand(),
              ),
            ),
            Positioned.fill(
              child: ControlsLayer(
                title: widget.title ?? '',
                visible: _uiVisible,
                isLocked: false,
                onLockToggle: () {},
                onSettingsTap: () => _togglePanel('settings'),
                onEpisodesTap: () => _togglePanel('episodes'),
                onTracksTap: () => _togglePanel('tracks'),
                onOrientationToggle: () {},
                showLockButton: false,
                showOrientationToggle: false,
              ),
            ),
            if (_activePanel != null)
              Stack(
                children: [
                  Positioned.fill(
                    child: GestureDetector(
                      onTap: () => _togglePanel(_activePanel!),
                      behavior: HitTestBehavior.translucent,
                      child: Container(color: Colors.black54),
                    ),
                  ),
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
