import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

/// 音轨选择面板。
///
/// 音轨数据来自播放器的 `tracksStream`（视频本身内嵌的音轨）。
class AudioPanel extends StatelessWidget {
  /// 可用音轨列表。
  final List<AudioTrack> audios;

  /// 当前选中的音轨（可能为空）。
  final AudioTrack? selectedAudio;

  /// 选择音轨回调。
  final ValueChanged<AudioTrack> onAudioSelected;

  const AudioPanel({
    super.key,
    required this.audios,
    required this.selectedAudio,
    required this.onAudioSelected,
  });

  @override
  Widget build(BuildContext context) {
    // 过滤播放器默认的 auto/no 选项，仅展示真实音轨。
    final visibleAudios = audios
        .where((track) => track.id != 'auto' && track.id != 'no')
        .toList(growable: false);
    return Container(
      color: const Color(0xFF1E1E1E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(16.0),
            child: Text(
              '音轨选择',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          Expanded(
            child: visibleAudios.isEmpty
                ? const Center(
                    child: Text(
                      '暂无可用音轨',
                      style: TextStyle(color: Colors.white70, fontSize: 14),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: visibleAudios.length,
                    itemBuilder: (context, index) {
                      return _buildAudioOption(visibleAudios[index]);
                    },
                  ),
          ),
        ],
      ),
    );
  }

  /// 构建单个音轨选项。
  Widget _buildAudioOption(AudioTrack track) {
    final isSelected =
        selectedAudio?.id != null && track.id == selectedAudio!.id;
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
      onTap: () => onAudioSelected(track),
    );
  }

  /// 获取音轨展示名称。
  String _getTrackName(AudioTrack track) {
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
