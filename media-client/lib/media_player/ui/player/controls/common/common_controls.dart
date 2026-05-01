import 'package:flutter/material.dart';

import '../../../../core/player/player_config.dart';
import '../../../../core/state/playback_state.dart';
import '../../../../../media_library/media_models.dart';
import '../../../../utils/player_utils.dart';

class CommonControls extends StatelessWidget {
  final PlaybackState state;
  final Future<void> Function() onPlayPause;
  final Future<void> Function(Duration position) onSeek;
  final Future<void> Function(Duration delta) onSeekRelative;
  final Future<void> Function(double volume) onVolume;
  final Future<void> Function(double speed) onSpeed;
  final Future<void> Function() onToggleFullscreen;
  final Future<void> Function() onToggleControls;
  final Future<void> Function(int index) onSelectCandidate;
  final Future<void> Function()? onPrev;
  final Future<void> Function()? onNext;
  final VoidCallback onOpenSettings;

  const CommonControls({
    super.key,
    required this.state,
    required this.onPlayPause,
    required this.onSeek,
    required this.onSeekRelative,
    required this.onVolume,
    required this.onSpeed,
    required this.onToggleFullscreen,
    required this.onToggleControls,
    required this.onSelectCandidate,
    required this.onOpenSettings,
    this.onPrev,
    this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: Container(
        padding: const EdgeInsets.only(
          left: 12,
          right: 12,
          top: 10,
          bottom: 16,
        ),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.bottomCenter,
            end: Alignment.topCenter,
            colors: [Colors.black.withValues(alpha: 0.75), Colors.transparent],
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ProgressBar(
              position: state.position,
              duration: state.duration,
              buffered: state.buffered,
              onSeek: onSeek,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                IconButton(
                  onPressed: onPrev == null ? null : () => onPrev!(),
                  icon: const Icon(Icons.skip_previous, color: Colors.white),
                ),
                PlayPauseButton(playing: state.playing, onPressed: onPlayPause),
                IconButton(
                  onPressed: onNext == null ? null : () => onNext!(),
                  icon: const Icon(Icons.skip_next, color: Colors.white),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Row(
                    children: [
                      Text(
                        '${formatDuration(state.position)} / ${formatDuration(state.duration)}',
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 12,
                        ),
                      ),
                      const Spacer(),
                      _SpeedButton(speed: state.speed, onSpeed: onSpeed),
                      const SizedBox(width: 8),
                      _CandidateButton(
                        candidates: state.candidates,
                        selectedIndex: state.selectedCandidateIndex,
                        onSelect: onSelectCandidate,
                      ),
                      const SizedBox(width: 8),
                      _VolumeButton(volume: state.volume, onVolume: onVolume),
                      const SizedBox(width: 4),
                      FullscreenButton(
                        fullscreen: state.isFullscreen,
                        onPressed: () => onToggleFullscreen(),
                      ),
                      IconButton(
                        onPressed: onOpenSettings,
                        icon: const Icon(Icons.settings, color: Colors.white),
                      ),
                      IconButton(
                        onPressed: () => onToggleControls(),
                        icon: const Icon(Icons.close, color: Colors.white),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class PlayPauseButton extends StatelessWidget {
  final bool playing;
  final Future<void> Function() onPressed;

  const PlayPauseButton({
    super.key,
    required this.playing,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: () => onPressed(),
      icon: Icon(playing ? Icons.pause : Icons.play_arrow, color: Colors.white),
    );
  }
}

class ProgressBar extends StatefulWidget {
  final Duration position;
  final Duration duration;
  final Duration buffered;
  final Future<void> Function(Duration position) onSeek;

  const ProgressBar({
    super.key,
    required this.position,
    required this.duration,
    required this.buffered,
    required this.onSeek,
  });

  @override
  State<ProgressBar> createState() => _ProgressBarState();
}

class _ProgressBarState extends State<ProgressBar> {
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

class VolumeSlider extends StatelessWidget {
  final double volume;
  final ValueChanged<double> onChanged;

  const VolumeSlider({
    super.key,
    required this.volume,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Slider(
      value: volume.clamp(0, 100),
      min: 0,
      max: 100,
      onChanged: onChanged,
    );
  }
}

class FullscreenButton extends StatelessWidget {
  final bool fullscreen;
  final VoidCallback onPressed;

  const FullscreenButton({
    super.key,
    required this.fullscreen,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onPressed,
      icon: Icon(
        fullscreen ? Icons.fullscreen_exit : Icons.fullscreen,
        color: Colors.white,
      ),
    );
  }
}

class _SpeedButton extends StatelessWidget {
  final double speed;
  final Future<void> Function(double speed) onSpeed;

  const _SpeedButton({required this.speed, required this.onSpeed});

  @override
  Widget build(BuildContext context) {
    const options = PlayerConfig.kSpeedOptions;
    return PopupMenuButton<double>(
      tooltip: '倍速',
      initialValue: speed,
      onSelected: (v) => onSpeed(v),
      itemBuilder: (context) {
        return [
          for (final v in options)
            PopupMenuItem<double>(
              value: v,
              child: Row(
                children: [
                  Text('${v}x'),
                  const Spacer(),
                  if ((v - speed).abs() < 0.001)
                    const Icon(Icons.check, size: 18),
                ],
              ),
            ),
        ];
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          '${speed.toStringAsFixed(speed == 1.0 ? 0 : 2)}x',
          style: const TextStyle(color: Colors.white, fontSize: 12),
        ),
      ),
    );
  }
}

class _VolumeButton extends StatelessWidget {
  final double volume;
  final Future<void> Function(double volume) onVolume;

  const _VolumeButton({required this.volume, required this.onVolume});

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<double>(
      tooltip: '音量',
      itemBuilder: (context) {
        return [
          PopupMenuItem<double>(
            enabled: false,
            child: SizedBox(
              width: 160,
              child: Row(
                children: [
                  const Icon(Icons.volume_up, size: 18),
                  Expanded(
                    child: Slider(
                      value: volume.clamp(0, 100),
                      min: 0,
                      max: 100,
                      onChanged: (v) => onVolume(v),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ];
      },
      child: Icon(
        volume <= 0
            ? Icons.volume_off
            : volume < 50
                ? Icons.volume_down
                : Icons.volume_up,
        color: Colors.white,
      ),
    );
  }
}

class _CandidateButton extends StatelessWidget {
  final List<AssetItem> candidates;
  final int selectedIndex;
  final Future<void> Function(int index) onSelect;

  const _CandidateButton({
    required this.candidates,
    required this.selectedIndex,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    if (candidates.isEmpty) {
      return const SizedBox.shrink();
    }
    return PopupMenuButton<int>(
      tooltip: '清晰度/来源',
      onSelected: (v) => onSelect(v),
      itemBuilder: (context) {
        return [
          for (int i = 0; i < candidates.length; i++)
            PopupMenuItem<int>(
              value: i,
              child: Row(
                children: [
                  Expanded(child: Text(assetDisplayName(candidates[i]))),
                  if (i == selectedIndex) const Icon(Icons.check, size: 18),
                ],
              ),
            ),
        ];
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(20),
        ),
        child: const Text(
          '来源',
          style: TextStyle(color: Colors.white, fontSize: 12),
        ),
      ),
    );
  }
}

class PlaybackSettingsPanel extends StatefulWidget {
  final PlaybackSettings settings;
  final ValueChanged<PlaybackSettings> onChanged;

  const PlaybackSettingsPanel({
    super.key,
    required this.settings,
    required this.onChanged,
  });

  @override
  State<PlaybackSettingsPanel> createState() => _PlaybackSettingsPanelState();
}

class _PlaybackSettingsPanelState extends State<PlaybackSettingsPanel> {
  late PlaybackSettings _s;

  @override
  void initState() {
    super.initState();
    _s = widget.settings;
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '播放设置',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text(
                '自动跳过片头片尾',
                style: TextStyle(color: Colors.white),
              ),
              value: _s.skipIntroOutro,
              onChanged: (v) =>
                  setState(() => _s = _s.copyWith(skipIntroOutro: v)),
            ),
            if (_s.skipIntroOutro) ...[
              _TimeRow(
                label: '片头时间',
                value: _s.introTime,
                onPick: (d) => setState(() => _s = _s.copyWith(introTime: d)),
              ),
              _TimeRow(
                label: '片尾时间',
                value: _s.outroTime,
                onPick: (d) => setState(() => _s = _s.copyWith(outroTime: d)),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text(
                  '同步应用到同系列所有剧集',
                  style: TextStyle(color: Colors.white),
                ),
                value: _s.applyToAllEpisodes,
                onChanged: (v) => setState(
                  () => _s = _s.copyWith(applyToAllEpisodes: v ?? false),
                ),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: () {
                      widget.onChanged(_s);
                      Navigator.of(context).pop();
                    },
                    child: const Text('保存'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _TimeRow extends StatelessWidget {
  final String label;
  final Duration value;
  final ValueChanged<Duration> onPick;

  const _TimeRow({
    required this.label,
    required this.value,
    required this.onPick,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(label, style: const TextStyle(color: Colors.white)),
      trailing: Text(
        formatDuration(value),
        style: const TextStyle(color: Colors.white70),
      ),
      onTap: () async {
        final picked = await showTimePicker(
          context: context,
          initialTime: TimeOfDay(
            hour: value.inHours,
            minute: (value.inMinutes % 60),
          ),
        );
        if (picked == null) return;
        onPick(Duration(hours: picked.hour, minutes: picked.minute));
      },
    );
  }
}
