import 'package:flutter/material.dart';
import '../../../../../../media_library/media_models.dart';

/// 移动端选集列表面板。
class EpisodePanel extends StatelessWidget {
  /// 选集列表。
  final List<EpisodeDetail> episodes;

  /// 是否正在加载选集列表。
  final bool loading;

  /// 加载错误文案。
  final String? errorText;

  /// 当前播放中的选集索引。
  final int currentEpisodeIndex;

  /// 点击选集回调。
  final ValueChanged<int> onEpisodeSelected;

  /// 点击选集后是否自动关闭当前面板。
  final bool closeOnSelect;

  const EpisodePanel({
    super.key,
    required this.episodes,
    required this.loading,
    required this.errorText,
    required this.currentEpisodeIndex,
    required this.onEpisodeSelected,
    this.closeOnSelect = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF1E1E1E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  '选集',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  '共${episodes.length}个',
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (loading && episodes.isEmpty) {
      return const Center(
        child: SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }

    if (episodes.isEmpty) {
      return Center(
        child: Text(
          errorText?.isNotEmpty == true ? errorText! : '暂无选集数据',
          style: const TextStyle(color: Colors.white70, fontSize: 13),
          textAlign: TextAlign.center,
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: episodes.length,
      itemBuilder: (context, index) {
        final episode = episodes[index];
        final isSelected = index == currentEpisodeIndex;
        final assetName = episode.assets.isNotEmpty
            ? episode.assets.first.path.split('/').last
            : null;
        return InkWell(
          onTap: () {
            onEpisodeSelected(index);
            if (closeOnSelect) {
              Navigator.of(context).maybePop();
            }
          },
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: isSelected
                  ? Colors.white.withValues(alpha: 0.1)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(6),
              border: isSelected
                  ? Border.all(color: const Color(0xFFFFD700))
                  : null,
            ),
            child: Row(
              children: [
                _EpisodeThumbnail(url: episode.stillPath, selected: isSelected),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        episode.title.isNotEmpty
                            ? episode.title
                            : '第 ${episode.episodeNumber} 集',
                        style: TextStyle(
                          color: isSelected
                              ? const Color(0xFFFFD700)
                              : Colors.white,
                          fontSize: 14,
                          fontWeight:
                              isSelected ? FontWeight.w600 : FontWeight.w500,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      if (assetName != null)
                        Text(
                          assetName,
                          style: const TextStyle(
                            color: Colors.white54,
                            fontSize: 11,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// 选集封面缩略图。
class _EpisodeThumbnail extends StatelessWidget {
  /// 缩略图地址。
  final String? url;

  /// 当前条目是否被选中。
  final bool selected;

  const _EpisodeThumbnail({required this.url, required this.selected});

  @override
  Widget build(BuildContext context) {
    final border = BorderRadius.circular(4);
    return ClipRRect(
      borderRadius: border,
      child: Container(
        width: 80,
        height: 45,
        color: Colors.grey[850],
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (url != null && url!.isNotEmpty)
              Image.network(
                url!,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) {
                  return const _EpisodePlaceholder();
                },
              )
            else
              const _EpisodePlaceholder(),
            Align(
              alignment: Alignment.center,
              child: Icon(
                Icons.play_circle_outline,
                color: selected ? const Color(0xFFFFD700) : Colors.white70,
                size: 22,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EpisodePlaceholder extends StatelessWidget {
  const _EpisodePlaceholder();

  @override
  Widget build(BuildContext context) {
    return const ColoredBox(
      color: Color(0xFF2A2A2A),
      child: Center(
        child: Icon(Icons.image_not_supported, color: Colors.white30, size: 18),
      ),
    );
  }
}
