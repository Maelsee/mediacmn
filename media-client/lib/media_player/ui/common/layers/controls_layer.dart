import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../logic/player_notifier.dart';
import '../../../utils/formatters.dart';
import '../components/player_buttons.dart';

/// 控制层
///
/// 包含顶部栏、底部栏和锁定按钮。
class ControlsLayer extends ConsumerWidget {
  final String title;
  final bool visible;
  final bool isLocked;
  final VoidCallback onLockToggle;
  final VoidCallback onSettingsTap;
  final VoidCallback onEpisodesTap;
  final VoidCallback onTracksTap;
  final VoidCallback onOrientationToggle;
  final bool showLockButton;
  final bool showOrientationToggle;
  final bool showSettingsButton;
  final bool showEpisodesButton;
  final bool showTracksButton;
  final bool showSpeedButton;
  final bool showVolumeButton;

  const ControlsLayer({
    super.key,
    required this.title,
    required this.visible,
    required this.isLocked,
    required this.onLockToggle,
    required this.onSettingsTap,
    required this.onEpisodesTap,
    required this.onTracksTap,
    required this.onOrientationToggle,
    this.showLockButton = true,
    this.showOrientationToggle = true,
    this.showSettingsButton = true,
    this.showEpisodesButton = true,
    this.showTracksButton = true,
    this.showSpeedButton = true,
    this.showVolumeButton = true,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AnimatedOpacity(
      opacity: visible ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 300),
      child: IgnorePointer(
        ignoring: !visible,
        child: Stack(
          children: [
            if (!isLocked)
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: _buildTopBar(context),
              ),
            if (!isLocked)
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: _buildBottomBar(context, ref),
              ),
            if (showLockButton)
              Positioned(
                left: 20,
                bottom: 100,
                child: PlayerIconButton(
                  icon: isLocked ? Icons.lock : Icons.lock_open,
                  onTap: onLockToggle,
                  color: Colors.white,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 8,
        left: 16,
        right: 16,
        bottom: 8,
      ),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.black87, Colors.transparent],
        ),
      ),
      child: Row(
        children: [
          PlayerIconButton(
            icon: Icons.arrow_back,
            onTap: () => context.pop(),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (showOrientationToggle)
            PlayerIconButton(
              icon: Icons.screen_rotation,
              onTap: onOrientationToggle,
            ),
          if (showSettingsButton)
            PlayerIconButton(
              icon: Icons.settings,
              onTap: onSettingsTap,
            ),
        ],
      ),
    );
  }

  Widget _buildBottomBar(BuildContext context, WidgetRef ref) {
    final state = ref.watch(playerProvider);
    final notifier = ref.read(playerProvider.notifier);
    final duration = state.duration;
    final position = state.position;

    return Container(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).padding.bottom + 16,
        left: 16,
        right: 16,
        top: 16,
      ),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [Colors.black87, Colors.transparent],
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Text(
                formatDuration(position),
                style: const TextStyle(color: Colors.white),
              ),
              Expanded(
                child: SliderTheme(
                  data: SliderTheme.of(context).copyWith(
                    trackHeight: 2,
                    thumbShape:
                        const RoundSliderThumbShape(enabledThumbRadius: 6),
                    overlayShape:
                        const RoundSliderOverlayShape(overlayRadius: 12),
                  ),
                  child: Slider(
                    value: position.inSeconds
                        .toDouble()
                        .clamp(0.0, duration.inSeconds.toDouble()),
                    min: 0.0,
                    max: duration.inSeconds.toDouble(),
                    activeColor: Theme.of(context).primaryColor,
                    inactiveColor: Colors.white24,
                    onChanged: (value) {
                      notifier.seek(Duration(seconds: value.toInt()));
                    },
                  ),
                ),
              ),
              Text(
                formatDuration(duration),
                style: const TextStyle(color: Colors.white),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              PlayerIconButton(
                icon: state.playing ? Icons.pause : Icons.play_arrow,
                onTap: () => notifier.toggle(),
                size: 32,
              ),
              Row(
                children: [
                  if (showVolumeButton)
                    PlayerIconButton(
                      icon: state.volume <= 0
                          ? Icons.volume_off
                          : Icons.volume_up,
                      onTap: () {
                        final isMuted = state.volume <= 0;
                        final targetVolume = isMuted ? 50.0 : 0.0;
                        notifier.setVolume(targetVolume);
                      },
                      tooltip: state.volume <= 0 ? '取消静音' : '静音',
                    ),
                  if (showSpeedButton)
                    PlayerTextButton(
                      text: '${state.rate}x',
                      onTap: () {
                        final speeds = [0.5, 1.0, 1.25, 1.5, 2.0];
                        final index = speeds.indexOf(state.rate);
                        final nextRate = speeds[(index + 1) % speeds.length];
                        notifier.setRate(nextRate);
                      },
                    ),
                  if (showEpisodesButton)
                    PlayerIconButton(
                      icon: Icons.list,
                      onTap: onEpisodesTap,
                      tooltip: '选集',
                    ),
                  if (showTracksButton)
                    PlayerIconButton(
                      icon: Icons.subtitles,
                      onTap: onTracksTap,
                      tooltip: '字幕/音轨',
                    ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}
