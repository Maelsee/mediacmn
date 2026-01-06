import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

/// 画质选择面板。
class QualityPanel extends StatelessWidget {
  /// 可用画质轨道列表。
  final List<VideoTrack> qualities;

  /// 当前选中的画质。
  final VideoTrack currentQuality;

  /// 选择画质回调。
  final ValueChanged<VideoTrack> onQualitySelected;

  const QualityPanel({
    super.key,
    required this.qualities,
    required this.currentQuality,
    required this.onQualitySelected,
  });

  @override
  Widget build(BuildContext context) {
    // 过滤播放器默认的 auto/no 选项，仅展示真实画质。
    final visibleQualities = qualities
        .where((track) => track.id != 'auto' && track.id != 'no')
        .toList(growable: false);
    return Container(
      // 移除固定宽度，由父组件控制
      color: const Color(0xFF1E1E1E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(16.0),
            child: Text(
              '画质选择',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          Expanded(
            child: visibleQualities.isEmpty
                ? const Center(
                    child: Text(
                      '暂无可用画质',
                      style: TextStyle(color: Colors.white70, fontSize: 14),
                    ),
                  )
                : ListView.builder(
                    itemCount: visibleQualities.length,
                    itemBuilder: (context, index) {
                      final quality = visibleQualities[index];
                      final isSelected = quality.id == currentQuality.id;
                      return ListTile(
                        title: Text(
                          _getTrackName(quality),
                          style: TextStyle(
                            color: isSelected
                                ? const Color(0xFFFFD700)
                                : Colors.white,
                            fontWeight: isSelected
                                ? FontWeight.bold
                                : FontWeight.normal,
                          ),
                        ),
                        trailing: isSelected
                            ? const Icon(Icons.check, color: Color(0xFFFFD700))
                            : null,
                        onTap: () => onQualitySelected(quality),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  String _getTrackName(VideoTrack track) {
    if (track.title != null && track.title!.isNotEmpty) {
      return track.title!;
    }
    if (track.w != null && track.h != null) {
      return '${track.w}x${track.h}';
    }
    return track.id;
  }
}
