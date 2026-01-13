import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

import '../core/state/playback_state.dart';

class DesktopOverlayPanelHost extends StatelessWidget {
  final bool visible;
  final Widget child;

  const DesktopOverlayPanelHost({
    super.key,
    required this.visible,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    return Positioned(
      right: 16,
      bottom: 84,
      child: _OverlayCard(child: child),
    );
  }
}

class _OverlayCard extends StatelessWidget {
  final Widget child;

  const _OverlayCard({required this.child});

  @override
  Widget build(BuildContext context) {
    final maxHeight = MediaQuery.of(context).size.height * 0.62;
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxHeight: maxHeight,
        maxWidth: 320,
      ),
      child: Material(
        color: const Color(0xFF151515),
        borderRadius: BorderRadius.circular(12),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: child,
        ),
      ),
    );
  }
}

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
    const options = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0];
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const _OverlayHeader(title: '倍速'),
        Expanded(
          child: ListView.builder(
            itemCount: options.length,
            itemBuilder: (context, index) {
              final v = options[index];
              final selected = (v - speed).abs() < 0.01;
              return ListTile(
                title: Text(
                  '${v}x',
                  style: TextStyle(
                    color:
                        selected ? const Color(0xFFFFD700) : Colors.white70,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
                trailing: selected
                    ? const Icon(Icons.check, color: Color(0xFFFFD700), size: 18)
                    : null,
                onTap: () => onSelect(v),
              );
            },
          ),
        ),
        const Divider(height: 1),
        ListTile(
          title: const Text('自定义（占位）',
              style: TextStyle(color: Colors.white70)),
          onTap: () {},
        ),
      ],
    );
  }
}

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
    final visible = state.subtitleTracks
        .where((t) => t.id != 'auto' && t.id != 'no')
        .toList(growable: false);
    final selected = state.selectedSubtitleTrack;
    final hasSubtitle = selected != null && selected.id != 'no';

    return Column(
      children: [
        _OverlayHeader(
          title: '字幕',
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('显示', style: TextStyle(color: Colors.white70)),
              Switch(
                value: hasSubtitle,
                onChanged: (v) async {
                  if (!v) {
                    await onSelect(SubtitleTrack.no());
                  } else {
                    if (visible.isNotEmpty) {
                      await onSelect(visible.first);
                    } else {
                      await onSelect(SubtitleTrack.auto());
                    }
                  }
                },
                activeTrackColor: const Color(0xFFFFD700),
              ),
            ],
          ),
        ),
        Expanded(
          child: visible.isEmpty
              ? const Center(
                  child: Text('暂无可用字幕',
                      style: TextStyle(color: Colors.white70)),
                )
              : ListView.builder(
                  itemCount: visible.length,
                  itemBuilder: (context, index) {
                    final t = visible[index];
                    final isSelected = selected?.id == t.id;
                    return ListTile(
                      title: Text(
                        _getSubtitleName(t),
                        style: TextStyle(
                          color: isSelected
                              ? const Color(0xFFFFD700)
                              : Colors.white70,
                        ),
                      ),
                      trailing: isSelected
                          ? const Icon(Icons.check,
                              color: Color(0xFFFFD700), size: 18)
                          : null,
                      onTap: () => onSelect(t),
                    );
                  },
                ),
        ),
        const Divider(height: 1),
        ListTile(
          title: const Text('外挂字幕导入（占位）',
              style: TextStyle(color: Colors.white70)),
          leading: const Icon(Icons.input, color: Colors.white70, size: 18),
          onTap: () {},
        ),
      ],
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
        'fre': 'Français',
        'ger': 'Deutsch',
        'spa': 'Español',
        'ita': 'Italiano',
        'rus': 'Русский',
      };
      return map[track.language!] ?? track.language!;
    }
    return track.id;
  }
}

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
      children: [
        const _OverlayHeader(title: '设置'),
        Expanded(
          child: ListView(
            children: [
              SwitchListTile(
                title: const Text('自动跳过片头片尾',
                    style: TextStyle(color: Colors.white70)),
                value: settings.skipIntroOutro,
                onChanged: (v) => onChanged(settings.copyWith(skipIntroOutro: v)),
              ),
              ListTile(
                title: const Text('画面比例（占位）',
                    style: TextStyle(color: Colors.white70)),
                onTap: () {},
              ),
              ListTile(
                title: const Text('快捷键（占位）',
                    style: TextStyle(color: Colors.white70)),
                onTap: () {},
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _OverlayHeader extends StatelessWidget {
  final String title;
  final Widget? trailing;

  const _OverlayHeader({
    required this.title,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      color: const Color(0xFF1E1E1E),
      child: Row(
        children: [
          Text(title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              )),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

