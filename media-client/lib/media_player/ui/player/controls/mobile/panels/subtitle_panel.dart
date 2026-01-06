import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

class SubtitlePanel extends StatelessWidget {
  final bool showSubtitles;
  final ValueChanged<bool> onToggleShowSubtitles;
  final List<SubtitleTrack> subtitles;
  final SubtitleTrack selectedSubtitle;
  final ValueChanged<SubtitleTrack> onSubtitleSelected;

  const SubtitlePanel({
    super.key,
    required this.showSubtitles,
    required this.onToggleShowSubtitles,
    required this.subtitles,
    required this.selectedSubtitle,
    required this.onSubtitleSelected,
  });

  @override
  Widget build(BuildContext context) {
    final visibleSubtitles = subtitles
        .where((track) => track.id != 'auto' && track.id != 'no')
        .toList(growable: false);
    return Container(
      // 移除固定宽度，由父组件控制
      color: const Color(0xFF1E1E1E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              children: [
                const Text(
                  '显示字幕',
                  style: TextStyle(color: Colors.white, fontSize: 16),
                ),
                const Spacer(),
                Switch(
                  value: showSubtitles,
                  onChanged: onToggleShowSubtitles,
                  activeTrackColor: const Color(0xFFFFD700),
                ),
              ],
            ),
          ),
          if (showSubtitles) ...[
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: Row(
                children: [
                  Text(
                    '可用字幕',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.bold),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                itemCount: visibleSubtitles.length,
                itemBuilder: (context, index) {
                  return _buildSubtitleOption(visibleSubtitles[index]);
                },
              ),
            ),
          ],
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              children: [
                const Text('外挂字幕',
                    style: TextStyle(color: Colors.white, fontSize: 14)),
                const Spacer(),
                const Icon(Icons.input, size: 16, color: Colors.white70),
                const SizedBox(width: 4),
                GestureDetector(
                  onTap: () {
                    // TODO: Import subtitle
                  },
                  child: const Text('导入',
                      style: TextStyle(color: Colors.white70, fontSize: 12)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSubtitleOption(SubtitleTrack track) {
    final isSelected = track == selectedSubtitle;
    return ListTile(
      title: Text(
        _getTrackName(track),
        style: TextStyle(
          color: isSelected ? const Color(0xFFFFD700) : Colors.white70,
          fontSize: 14,
        ),
      ),
      trailing: isSelected
          ? const Icon(Icons.check, color: Color(0xFFFFD700), size: 16)
          : null,
      onTap: () => onSubtitleSelected(track),
    );
  }

  String _getTrackName(SubtitleTrack track) {
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
