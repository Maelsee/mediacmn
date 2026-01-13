import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

import '../core/state/playback_state.dart';

class DesktopOverlayPanelHost extends StatelessWidget {
  final bool visible;
  final Widget child;
  final double? width;
  final double? right;

  const DesktopOverlayPanelHost({
    super.key,
    required this.visible,
    required this.child,
    this.width,
    this.right,
  });

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    // 统一位置：右下角，距离底部 bar 一定高度
    return Positioned(
      right: right ?? 16,
      bottom: 84,
      child: _OverlayCard(
        width: width,
        child: child,
      ),
    );
  }
}

class _OverlayCard extends StatelessWidget {
  final Widget child;
  final double? width;

  const _OverlayCard({required this.child, this.width});

  @override
  Widget build(BuildContext context) {
    // 统一最低高度和最大高度
    final maxHeight = MediaQuery.of(context).size.height * 0.62;
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxHeight: maxHeight,
        maxWidth: width ?? 320, // 允许覆盖宽度
        minWidth: width ?? 200, // 允许覆盖宽度
      ),
      child: Material(
        color: const Color(0xFF151515),
        borderRadius: BorderRadius.circular(12),
        elevation: 8,
        shadowColor: Colors.black54,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: child,
        ),
      ),
    );
  }
}

/// 音量控制面板（参考图3：竖向滑块）
class DesktopVolumeOverlayPanel extends StatefulWidget {
  final double volume; // 0.0 ~ 100.0
  final Future<void> Function(double volume) onVolumeChanged;

  const DesktopVolumeOverlayPanel({
    super.key,
    required this.volume,
    required this.onVolumeChanged,
  });

  @override
  State<DesktopVolumeOverlayPanel> createState() =>
      _DesktopVolumeOverlayPanelState();
}

class _DesktopVolumeOverlayPanelState extends State<DesktopVolumeOverlayPanel> {
  double? _dragValue;

  @override
  Widget build(BuildContext context) {
    final current = _dragValue ?? widget.volume;

    // 独立的小尺寸面板，用于音量调节
    return SizedBox(
      width: 60,
      height: 200,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 12),
          Text(
            '${current.round()}%',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.bold,
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: RotatedBox(
                quarterTurns: 3, // 旋转成竖向
                child: SliderTheme(
                  data: SliderTheme.of(context).copyWith(
                    trackHeight: 4,
                    thumbShape:
                        const RoundSliderThumbShape(enabledThumbRadius: 8),
                    overlayShape: SliderComponentShape.noOverlay,
                    activeTrackColor: Colors.white,
                    inactiveTrackColor: Colors.white24,
                    thumbColor: Colors.white,
                  ),
                  child: Slider(
                    value: current.clamp(0.0, 100.0),
                    min: 0,
                    max: 100,
                    onChanged: (v) {
                      setState(() => _dragValue = v);
                      widget.onVolumeChanged(v);
                    },
                    onChangeEnd: (v) {
                      setState(() => _dragValue = null);
                      widget.onVolumeChanged(v);
                    },
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
        ],
      ),
    );
  }
}

/// 倍速控制面板（参考图4：列表选择）
class DesktopSpeedOverlayPanel extends StatelessWidget {
  final double speed;
  final Future<void> Function(double speed) onSelect;

  const DesktopSpeedOverlayPanel({
    super.key,
    required this.speed,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    const options = [5.0, 3.0, 2.0, 1.5, 1.2, 1.0, 0.8];
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              children: [
                ...options.map((v) {
                  final selected = (v - speed).abs() < 0.01;
                  return InkWell(
                    onTap: () => onSelect(v),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          vertical: 10, horizontal: 16),
                      color: selected ? Colors.white10 : Colors.transparent,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            '${v}x',
                            style: TextStyle(
                              color: selected
                                  ? const Color(0xFFFFD700)
                                  : Colors.white70,
                              fontWeight: selected
                                  ? FontWeight.w600
                                  : FontWeight.normal,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }),
                const Divider(height: 1, color: Colors.white10),
                InkWell(
                  onTap: () {},
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        vertical: 12, horizontal: 16),
                    alignment: Alignment.center,
                    child: const Text('自定义',
                        style: TextStyle(color: Colors.white70, fontSize: 14)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// 音轨控制面板
class DesktopAudioTrackOverlayPanel extends StatelessWidget {
  final PlaybackState state;
  final Future<void> Function(AudioTrack track) onSelect;

  const DesktopAudioTrackOverlayPanel({
    super.key,
    required this.state,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final tracks = state.audioTracks;
    final selected = state.selectedAudioTrack;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text('音轨选择',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.bold)),
        ),
        const Divider(height: 1, color: Colors.white10),
        Expanded(
          child: SingleChildScrollView(
            child: Column(
              children: tracks.map((t) {
                final isSelected = selected?.id == t.id;
                return InkWell(
                  onTap: () => onSelect(t),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    color: isSelected ? Colors.white10 : Colors.transparent,
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            t.title ?? t.language ?? t.id,
                            style: TextStyle(
                              color: isSelected
                                  ? const Color(0xFF1F7AE0)
                                  : Colors.white70,
                              fontSize: 14,
                            ),
                          ),
                        ),
                        if (isSelected)
                          const Icon(Icons.check,
                              color: Color(0xFF1F7AE0), size: 16),
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
      ],
    );
  }
}

/// 画质控制面板
class DesktopQualityOverlayPanel extends StatelessWidget {
  final PlaybackState state;
  // 注意：实际项目中画质切换可能涉及切换源或 track，这里暂以 String 模拟
  final Future<void> Function(String quality) onSelect;

  const DesktopQualityOverlayPanel({
    super.key,
    required this.state,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    // 模拟画质列表
    const qualities = ['至臻画质', '超清 1080P', '高清 720P', '标清 360P'];
    const current = '至臻画质'; // 暂写死

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              children: qualities.map((q) {
                final isSelected = q == current;
                return InkWell(
                  onTap: () => onSelect(q),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        vertical: 10, horizontal: 16),
                    color: isSelected ? Colors.white10 : Colors.transparent,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          q,
                          style: TextStyle(
                            color: isSelected
                                ? const Color(0xFFFFD700)
                                : Colors.white70,
                            fontWeight: isSelected
                                ? FontWeight.w600
                                : FontWeight.normal,
                            fontSize: 14,
                          ),
                        ),
                        if (q == '至臻画质' || q == '超清 1080P') ...[
                          const SizedBox(width: 4),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 4, vertical: 1),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFFD700),
                              borderRadius: BorderRadius.circular(2),
                            ),
                            child: const Text(
                              'SVIP',
                              style: TextStyle(
                                  color: Colors.black,
                                  fontSize: 8,
                                  fontWeight: FontWeight.bold),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
      ],
    );
  }
}

/// 字幕控制面板（参考图5：内嵌/外挂/AI/设置）
class DesktopSubtitleOverlayPanel extends StatelessWidget {
  final PlaybackState state;
  final Future<void> Function(SubtitleTrack track) onSelect;

  const DesktopSubtitleOverlayPanel({
    super.key,
    required this.state,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final tracks = state.subtitleTracks;
    final selected = state.selectedSubtitleTrack;
    final hasSubtitle = selected != null && selected.id != 'no';

    // 分组逻辑（示例）
    final embedded = tracks
        .where((t) => t.id != 'auto' && t.id != 'no') // 假设这里只展示内嵌
        .toList();
    // 实际项目中可以根据 track.id 或 title 特征区分外挂

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildGroupTile(context, '内嵌字幕', embedded, selected),
        const Divider(height: 1, color: Colors.white10),
        _buildActionTile('外挂字幕', Icons.chevron_right, () {}),
        _buildActionTile('AI字幕', Icons.chevron_right, () {}),
        const Divider(height: 1, color: Colors.white10),
        _buildActionTile('字幕设置', null, () {}),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          color: const Color(0xFF202020),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('显示字幕',
                  style: TextStyle(color: Colors.white, fontSize: 14)),
              Switch(
                value: hasSubtitle,
                onChanged: (v) async {
                  if (!v) {
                    await onSelect(SubtitleTrack.no());
                  } else {
                    if (embedded.isNotEmpty) {
                      await onSelect(embedded.first);
                    } else {
                      await onSelect(SubtitleTrack.auto());
                    }
                  }
                },
                activeThumbColor: Colors.white,
                activeTrackColor: const Color(0xFF1F7AE0),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildGroupTile(BuildContext context, String title,
      List<SubtitleTrack> tracks, SubtitleTrack? selected) {
    return ExpansionTile(
      title: Text(title,
          style: const TextStyle(color: Colors.white70, fontSize: 14)),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (selected != null &&
              selected.id != 'no' &&
              tracks.any((t) => t.id == selected.id))
            Text(_getSubtitleName(selected),
                style: const TextStyle(color: Color(0xFF1F7AE0), fontSize: 12)),
          const Icon(Icons.keyboard_arrow_right, color: Colors.white70),
        ],
      ),
      children: tracks.map((t) {
        final isSelected = selected?.id == t.id;
        return InkWell(
          onTap: () => onSelect(t),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 10),
            color: isSelected ? Colors.white10 : Colors.transparent,
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _getSubtitleName(t),
                    style: TextStyle(
                      color:
                          isSelected ? const Color(0xFF1F7AE0) : Colors.white70,
                      fontSize: 13,
                    ),
                  ),
                ),
                if (isSelected)
                  const Icon(Icons.check, color: Color(0xFF1F7AE0), size: 16),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildActionTile(String title, IconData? icon, VoidCallback onTap) {
    return ListTile(
      title: Text(title,
          style: const TextStyle(color: Colors.white70, fontSize: 14)),
      trailing:
          icon != null ? Icon(icon, color: Colors.white70, size: 20) : null,
      onTap: onTap,
      dense: true,
    );
  }

  String _getSubtitleName(SubtitleTrack track) {
    if (track.title != null && track.title!.isNotEmpty) {
      return track.title!;
    }
    if (track.language != null && track.language!.isNotEmpty) {
      const map = {
        'chi': '中文',
        'zho': '中文',
        'eng': 'English',
        'jpn': '日本語',
        'kor': '한국어',
      };
      return map[track.language!] ?? track.language!;
    }
    return track.id;
  }
}

/// 设置面板（通用设置）
class DesktopSettingsOverlayPanel extends StatelessWidget {
  final PlaybackSettings settings;
  final Future<void> Function(PlaybackSettings settings) onChanged;

  const DesktopSettingsOverlayPanel({
    super.key,
    required this.settings,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text('播放设置',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.bold)),
        ),
        const Divider(height: 1, color: Colors.white10),
        SwitchListTile(
          title: const Text('自动跳过片头片尾',
              style: TextStyle(color: Colors.white70, fontSize: 14)),
          value: settings.skipIntroOutro,
          onChanged: (v) => onChanged(settings.copyWith(skipIntroOutro: v)),
          activeThumbColor: Colors.white,
          activeTrackColor: const Color(0xFF1F7AE0),
        ),
      ],
    );
  }
}
