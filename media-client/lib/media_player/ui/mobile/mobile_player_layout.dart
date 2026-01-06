import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:media_kit/media_kit.dart';

import '../../logic/player_notifier.dart';
import '../../../core/api_client.dart';
import '../common/layers/video_layer.dart';
import '../common/layers/controls_layer.dart';
import '../common/layers/loading_layer.dart';
import '../common/panels/episode_panel.dart';
import '../common/panels/settings_panel.dart';
import '../common/panels/tracks_panel.dart';
import 'gesture_layer.dart';

class MobilePlayerLayout extends ConsumerStatefulWidget {
  final String? title;
  final List<Map<String, dynamic>> episodes;
  final int currentEpisodeIndex;
  final Function(int index)? onEpisodeSelected;
  final VoidCallback? onNext;
  final VoidCallback? onPrev;

  const MobilePlayerLayout({
    super.key,
    this.title,
    this.episodes = const [],
    this.currentEpisodeIndex = -1,
    this.onEpisodeSelected,
    this.onNext,
    this.onPrev,
  });

  @override
  ConsumerState<MobilePlayerLayout> createState() => _MobilePlayerLayoutState();
}

class _MobilePlayerLayoutState extends ConsumerState<MobilePlayerLayout> {
  bool _uiVisible = false;
  Timer? _hideTimer;
  bool _isLocked = false;
  final TransformationController _transformController =
      TransformationController();

  bool _isLandscape = true;

  String? _activePanel;

  bool _autoSkip = false;
  bool _enableHardwareAcceleration = true;

  List<Map<String, dynamic>> _externalSubtitles = [];
  bool _loadingExternalSubtitles = false;
  String? _externalSubtitleError;
  int? _currentSubtitleFileId;

  @override
  void initState() {
    super.initState();
    _enterFullscreen();
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    WakelockPlus.enable();
    _showUI();

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
    ref.listen(playerProvider.select((s) => s.error), (prev, next) {
      if (next != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('错误: $next'), backgroundColor: Colors.red),
        );
      }
    });

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
      body: Stack(
        fit: StackFit.expand,
        children: [
          Positioned.fill(
            child: VideoLayer(transformationController: _transformController),
          ),
          Positioned.fill(
            child: GestureLayer(
              onTap: _toggleUI,
              onActivity: _onActivity,
            ),
          ),
          const Positioned.fill(
            child: LoadingLayer(),
          ),
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
