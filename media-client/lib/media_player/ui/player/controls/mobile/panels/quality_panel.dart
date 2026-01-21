import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

/// 画质选择面板。
class QualityPanel extends StatefulWidget {
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
  State<QualityPanel> createState() => _QualityPanelState();
}

class _QualityPanelState extends State<QualityPanel> {
  final ScrollController _scrollController = ScrollController();
  late List<VideoTrack> _visibleQualities;

  @override
  void didUpdateWidget(QualityPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.qualities != oldWidget.qualities) {
      _visibleQualities = widget.qualities
          .where((track) => track.id != 'no')
          .toList(growable: false);
    }
  }

  @override
  void initState() {
    super.initState();
    // 过滤播放器默认的 no 选项，保留 auto 和真实画质。
    _visibleQualities = widget.qualities
        .where((track) => track.id != 'no')
        .toList(growable: false);

    // 初始滚动到选中项
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final index =
          _visibleQualities.indexWhere((t) => t.id == widget.currentQuality.id);
      if (index != -1 && _scrollController.hasClients) {
        const itemHeight = 56.0;
        final offset = index * itemHeight;
        final maxScroll = _scrollController.position.maxScrollExtent;
        _scrollController.jumpTo(offset > maxScroll ? maxScroll : offset);
      }
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
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
          child: _visibleQualities.isEmpty
              ? const Center(
                  child: Text(
                    '暂无可用画质',
                    style: TextStyle(color: Colors.white70, fontSize: 14),
                  ),
                )
              : ListView.builder(
                  controller: _scrollController,
                  itemCount: _visibleQualities.length,
                  itemBuilder: (context, index) {
                    final quality = _visibleQualities[index];
                    // 使用 ID 对比确保选中状态正确
                    final isSelected = quality.id == widget.currentQuality.id;
                    return GestureDetector(
                      onTap: () => widget.onQualitySelected(quality),
                      child: Container(
                        // margin: const EdgeInsets.symmetric(vertical: 4),
                        // padding: const EdgeInsets.symmetric(vertical: 14),
                        margin: const EdgeInsets.symmetric(
                            vertical: 4, horizontal: 16),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF666666).withValues(alpha: 0.3),
                          borderRadius: BorderRadius.circular(12),
                          border: isSelected
                              ? Border.all(
                                  color: const Color(0xFFFFE796), width: 1)
                              : null,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          _getTrackName(quality),
                          style: TextStyle(
                            color: isSelected
                                ? const Color(0xFFFFE796)
                                : Colors.white,
                            fontSize: 14,
                            fontWeight: isSelected
                                ? FontWeight.bold
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  String _getTrackName(VideoTrack track) {
    if (track.id == 'auto') return '自动';
    if (track.title != null && track.title!.isNotEmpty) {
      return track.title!;
    }
    if (track.w != null && track.h != null) {
      return '${track.w}x${track.h}';
    }
    return track.id;
  }
}
