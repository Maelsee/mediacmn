import 'package:flutter/material.dart';
import 'package:media_client/media_player/utils/track_formatter.dart';
import 'package:media_kit/media_kit.dart';

import '../widgets/panel_list_item.dart';

/// 音轨选择面板。
///
/// 音轨数据来自播放器的 `tracksStream`（视频本身内嵌的音轨）。
class AudioPanel extends StatefulWidget {
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
  State<AudioPanel> createState() => _AudioPanelState();
}

class _AudioPanelState extends State<AudioPanel> {
  final ScrollController _scrollController = ScrollController();
  late List<AudioTrack> _visibleAudios;

  @override
  void didUpdateWidget(AudioPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.audios != oldWidget.audios) {
      _visibleAudios = widget.audios
          .where((track) => track.id != 'no')
          .toList(growable: false);
    }
  }

  @override
  void initState() {
    super.initState();
    // 过滤播放器默认的 no 选项，保留 auto 和真实音轨。
    _visibleAudios = widget.audios
        .where((track) => track.id != 'no')
        .toList(growable: false);

    // 初始滚动到选中项
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.selectedAudio != null) {
        final index =
            _visibleAudios.indexWhere((t) => t.id == widget.selectedAudio!.id);
        if (index != -1 && _scrollController.hasClients) {
          // 假设每个 Item 高度约 56 (ListTile默认高度)
          const itemHeight = 56.0;
          final offset = index * itemHeight;
          final maxScroll = _scrollController.position.maxScrollExtent;
          _scrollController.jumpTo(offset > maxScroll ? maxScroll : offset);
        }
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
            '音轨选择',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        Expanded(
          child: _visibleAudios.isEmpty
              ? const Center(
                  child: Text(
                    '暂无可用音轨',
                    style: TextStyle(color: Colors.white70, fontSize: 14),
                  ),
                )
              : ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: _visibleAudios.length,
                  itemBuilder: (context, index) {
                    return _buildAudioOption(_visibleAudios[index]);
                  },
                ),
        ),
      ],
    );
  }

  /// 构建单个音轨选项。
  Widget _buildAudioOption(AudioTrack track) {
    // 使用 ID 进行严格对比，解决对象引用不一致导致的选中状态失效问题
    final isSelected = widget.selectedAudio?.id != null &&
        track.id == widget.selectedAudio!.id;
    return PanelListItem(
      isSelected: isSelected,
      onTap: () => widget.onAudioSelected(track),
      child: Text(
        TrackFormatter.audio(track),
        style: TextStyle(
          color: isSelected ? const Color(0xFFFFE796) : Colors.white,
          fontSize: 14,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
        ),
      ),
    );
  }
}
