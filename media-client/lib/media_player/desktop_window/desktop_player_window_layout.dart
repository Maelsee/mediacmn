import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../core/state/playback_state.dart';
import '../ui/player/overlays/error_overlay.dart';
import '../ui/player/overlays/loading_overlay.dart';
import '../utils/player_utils.dart';
import 'desktop_player_overlay_panels.dart';
import 'desktop_player_side_panel.dart';

enum _OverlayKind {
  none,
  subtitles,
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
      _OverlayKind.subtitles => DesktopSubtitleOverlayPanel(
          state: s,
          onSelect: notifier.setSubtitleTrack,
        ),
      _OverlayKind.speed => DesktopSpeedOverlayPanel(
          speed: s.speed,
          onSelect: notifier.setSpeed,
        ),
      _OverlayKind.settings => DesktopSettingsOverlayPanel(
          settings: s.settings,
          onChanged: notifier.updateSettings,
        ),
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
        child: Stack(
          fit: StackFit.expand,
          children: [
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
            if (s.loading || s.buffering)
              Positioned.fill(
                child: LoadingOverlay(
                  progress: s.duration.inMilliseconds > 0
                      ? (s.buffered.inMilliseconds / s.duration.inMilliseconds)
                          .clamp(0.0, 1.0)
                      : null,
                ),
              ),
            if (s.error != null)
              Positioned.fill(child: ErrorOverlay(message: s.error!)),
            if (s.controlsVisible)
              Positioned(
                left: 16,
                right: 16,
                top: 12,
                child: _TopBar(
                  title: s.title ?? '',
                  onClose: () => Navigator.of(context).maybePop(),
                ),
              ),
            if (s.controlsVisible)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: _BottomBar(
                  state: s,
                  onPlayPause: notifier.playPause,
                  onPrev: s.hasPrevEpisode ? notifier.playPrevEpisode : null,
                  onNext: s.hasNextEpisode ? notifier.playNextEpisode : null,
                  onSeek: notifier.seek,
                  onToggleEpisodes: _toggleSidePanel,
                  onToggleSubtitles: () =>
                      _toggleOverlay(_OverlayKind.subtitles),
                  onToggleSpeed: () => _toggleOverlay(_OverlayKind.speed),
                  onToggleSettings: () => _toggleOverlay(_OverlayKind.settings),
                ),
              ),
            DesktopOverlayPanelHost(
              visible: s.controlsVisible && overlayPanel != null,
              child: overlayPanel ?? const SizedBox.shrink(),
            ),
            DesktopPlayerSidePanel(
              visible: _sidePanelVisible,
              state: s,
              onClose: () => setState(() => _sidePanelVisible = false),
              onEpisodeTap: (index) async {
                await notifier.openEpisodeAtIndex(index);
                _showControlsTemporarily();
              },
            ),
            DesktopSidePanelHandle(
              visible: s.controlsVisible,
              expanded: _sidePanelVisible,
              onToggle: _toggleSidePanel,
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
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        IconButton(
          tooltip: '截图（占位）',
          onPressed: () {},
          icon: const Icon(Icons.photo_camera_outlined, color: Colors.white),
        ),
        IconButton(
          tooltip: '剪辑（占位）',
          onPressed: () {},
          icon: const Icon(Icons.content_cut, color: Colors.white),
        ),
        IconButton(
          tooltip: '置顶（占位）',
          onPressed: () {},
          icon: const Icon(Icons.push_pin_outlined, color: Colors.white),
        ),
        IconButton(
          tooltip: '更多（占位）',
          onPressed: () {},
          icon: const Icon(Icons.more_horiz, color: Colors.white),
        ),
        IconButton(
          tooltip: '关闭',
          onPressed: onClose,
          icon: const Icon(Icons.close, color: Colors.white),
        ),
      ],
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
  final VoidCallback onToggleSettings;

  const _BottomBar({
    required this.state,
    required this.onPlayPause,
    required this.onPrev,
    required this.onNext,
    required this.onSeek,
    required this.onToggleEpisodes,
    required this.onToggleSubtitles,
    required this.onToggleSpeed,
    required this.onToggleSettings,
  });

  @override
  Widget build(BuildContext context) {
    final position = state.position;
    final duration = state.duration;

    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [
            Colors.black.withValues(alpha: 0.85),
            Colors.transparent,
          ],
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _DesktopProgressBar(
            position: state.position,
            duration: state.duration,
            buffered: state.buffered,
            onSeek: onSeek,
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              IconButton(
                tooltip: '上一集',
                onPressed: onPrev == null ? null : () => onPrev!(),
                icon: const Icon(Icons.skip_previous, color: Colors.white),
              ),
              IconButton(
                tooltip: state.playing ? '暂停' : '播放',
                onPressed: () => onPlayPause(),
                icon: Icon(
                  state.playing ? Icons.pause : Icons.play_arrow,
                  color: Colors.white,
                ),
              ),
              IconButton(
                tooltip: '下一集',
                onPressed: onNext == null ? null : () => onNext!(),
                icon: const Icon(Icons.skip_next, color: Colors.white),
              ),
              const SizedBox(width: 8),
              Text(
                '${formatDuration(position)} / ${formatDuration(duration)}',
                style: const TextStyle(color: Colors.white70, fontSize: 12),
              ),
              const Spacer(),
              _TextActionButton(label: 'AI总结', onPressed: () {}),
              const SizedBox(width: 6),
              _TextActionButton(label: '字幕', onPressed: onToggleSubtitles),
              const SizedBox(width: 6),
              _TextActionButton(label: '语言', onPressed: () {}),
              const SizedBox(width: 6),
              _TextActionButton(label: '选集', onPressed: onToggleEpisodes),
              const SizedBox(width: 6),
              _TextActionButton(label: '倍速', onPressed: onToggleSpeed),
              const SizedBox(width: 6),
              _TextActionButton(label: '至臻画质', onPressed: () {}),
              const SizedBox(width: 6),
              IconButton(
                tooltip: '设置',
                onPressed: onToggleSettings,
                icon: const Icon(Icons.settings, color: Colors.white),
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
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w500,
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

    return Stack(
      children: [
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 0),
            overlayShape: SliderComponentShape.noOverlay,
            activeTrackColor: Colors.white24,
            inactiveTrackColor: Colors.white24,
          ),
          child: Slider(
            value: durationMs == 0
                ? 0
                : bufferedMs.clamp(0, durationMs).toDouble(),
            min: 0,
            max: durationMs == 0 ? 1 : durationMs.toDouble(),
            onChanged: (_) {},
          ),
        ),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            activeTrackColor: Colors.white,
            inactiveTrackColor: Colors.white24,
            thumbColor: Colors.white,
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
    );
  }
}
