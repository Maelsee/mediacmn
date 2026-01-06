import 'dart:async';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';

import '../../logic/player_notifier.dart';
import '../../../core/api_client.dart';
import '../common/layers/controls_layer.dart';
import '../common/layers/loading_layer.dart';
import '../common/layers/video_layer.dart';
import '../common/panels/episode_panel.dart';
import '../common/panels/settings_panel.dart';
import '../common/panels/tracks_panel.dart';

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

  // 外挂字幕相关状态
  List<Map<String, dynamic>> _externalSubtitles = [];
  bool _loadingExternalSubtitles = false;
  String? _externalSubtitleError;
  int? _currentSubtitleFileId;

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

  /// 加载当前文件对应的外挂字幕列表
  Future<void> _loadExternalSubtitles(int fileId) async {
    _currentSubtitleFileId = fileId;
    setState(() {
      _loadingExternalSubtitles = true;
      _externalSubtitleError = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final list = await api.getSubtitles(fileId);
      if (!mounted || fileId != _currentSubtitleFileId) return;
      setState(() {
        _externalSubtitles = list;
        _loadingExternalSubtitles = false;
      });
    } catch (e) {
      if (!mounted || fileId != _currentSubtitleFileId) return;
      setState(() {
        _externalSubtitles = [];
        _loadingExternalSubtitles = false;
        _externalSubtitleError = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // 监听播放器错误并在界面上提示
    ref.listen(playerProvider.select((s) => s.error), (prev, next) {
      if (next != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('错误: $next'), backgroundColor: Colors.red),
        );
      }
    });

    // 监听当前播放文件ID变化，动态加载对应的外挂字幕列表
    ref.listen<int?>(
      playerProvider.select((s) => s.fileId),
      (prev, next) {
        final fid = next;
        if (fid != null && fid != _currentSubtitleFileId) {
          _loadExternalSubtitles(fid);
        }
      },
    );

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

    return TracksPanel(
      audioTracks: state.tracks.audio,
      currentAudio: state.track.audio,
      subtitleTracks: state.tracks.subtitle,
      currentSubtitle: state.track.subtitle,
      videoTracks: state.tracks.video,
      externalSubtitles: _externalSubtitles,
      loadingExternalSubtitles: _loadingExternalSubtitles,
      externalSubtitleError: _externalSubtitleError,
      onAudioSelected: (track) {
        notifier.setAudioTrack(track);
      },
      onSubtitleSelected: (track) {
        notifier.setSubtitleTrack(track);
      },
      onExternalSubtitleSelected: (sub) {
        _handleExternalSubtitleTap(sub, notifier);
      },
      onVideoSelected: (track) {
        notifier.setVideoTrack(track);
      },
    );
  }

  Future<void> _handleExternalSubtitleTap(
      Map<String, dynamic> sub, PlayerNotifier notifier) async {
    final messenger = ScaffoldMessenger.of(context);
    final url = sub['url'] as String?;
    if (url == null || url.isEmpty) {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('该外挂字幕暂不可用'),
          backgroundColor: Colors.blueGrey,
        ),
      );
      return;
    }
    final name = (sub['name'] ?? sub['path'] ?? sub['id'] ?? '外挂字幕').toString();

    final track = SubtitleTrack.uri(url, title: name);
    notifier.setSubtitleTrack(track);
    messenger.showSnackBar(
      SnackBar(
        content: Text('已切换到外挂字幕: $name'),
        backgroundColor: Colors.blueGrey,
      ),
    );
  }
}
