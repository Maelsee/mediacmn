import 'package:flutter/material.dart';

import '../core/state/playback_state.dart';
import '../../media_library/media_models.dart';

const kDesktopSidePanelWidth = 340.0;

class DesktopPlayerSidePanel extends StatefulWidget {
  final bool visible;
  final PlaybackState state;
  final VoidCallback onClose;
  final Future<void> Function(int index) onEpisodeTap;

  const DesktopPlayerSidePanel({
    super.key,
    required this.visible,
    required this.state,
    required this.onClose,
    required this.onEpisodeTap,
  });

  @override
  State<DesktopPlayerSidePanel> createState() => _DesktopPlayerSidePanelState();
}

class _DesktopPlayerSidePanelState extends State<DesktopPlayerSidePanel> {
  final _scrollController = ScrollController();

  @override
  void didUpdateWidget(covariant DesktopPlayerSidePanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.visible && !oldWidget.visible) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _scrollToCurrent();
      });
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToCurrent() {
    final idx = _currentEpisodeIndex(widget.state);
    if (idx == null) return;
    if (!_scrollController.hasClients) return;

    // 估算高度：Header(110) + Item(80) * idx
    // 简单滚动
    const itemExtent = 84.0;
    final offset = (idx * itemExtent) - itemExtent;
    final target =
        offset.clamp(0.0, _scrollController.position.maxScrollExtent);
    _scrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 240),
      curve: Curves.easeOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    // 仅在 visible 为 true 时显示内容，外部通过 Row/Expanded 控制布局变化
    // 这里只负责显示侧边栏本体，不负责遮罩或动画位置（交由 Layout 处理）
    if (!widget.visible) return const SizedBox.shrink();

    final episodes = widget.state.episodes;
    final currentIdx = _currentEpisodeIndex(widget.state);

    return Container(
      width: kDesktopSidePanelWidth,
      color: const Color(0xFF141414),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 顶部标题 "选集"
          Container(
            height: 48,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            alignment: Alignment.centerLeft,
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: Color(0xFF2A2A2A), width: 1),
              ),
            ),
            child: const Text(
              '选集',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),

          // 选集标题栏 (S02 | 全部)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Row(
              children: [
                const Text(
                  'S02', // 占位：实际应从 state 获取季信息
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                InkWell(
                  onTap: () {},
                  child: const Row(
                    children: [
                      Text('全部',
                          style:
                              TextStyle(color: Colors.white70, fontSize: 13)),
                      Icon(Icons.arrow_drop_down,
                          color: Colors.white70, size: 18),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // 列表区域
          Expanded(
            child: Builder(
              builder: (context) {
                if (widget.state.episodesLoading) {
                  return const Center(
                    child: SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  );
                }
                if (episodes.isEmpty) {
                  return const Center(
                    child:
                        Text('暂无选集', style: TextStyle(color: Colors.white70)),
                  );
                }

                return ListView.builder(
                  controller: _scrollController,
                  itemCount: episodes.length,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemBuilder: (context, index) {
                    final ep = episodes[index];
                    final selected = currentIdx == index;
                    return _buildEpisodeItem(ep, selected, index);
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEpisodeItem(EpisodeDetail ep, bool selected, int index) {
    // 模拟缩略图：实际项目中应使用 ep.stillPath 加载图片
    // 这里使用带颜色的 Container 占位
    final hasImage = ep.stillPath != null && ep.stillPath!.isNotEmpty;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        onTap: () async {
          await widget.onEpisodeTap(index);
          // 点击后不自动关闭，方便连续选集
        },
        borderRadius: BorderRadius.circular(8),
        child: Container(
          height: 72,
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF1F2A3A) : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: selected
                ? Border.all(
                    color: const Color(0xFF1F7AE0).withValues(alpha: 0.5))
                : null,
          ),
          child: Row(
            children: [
              // 缩略图区域
              Container(
                width: 128,
                height: 72,
                decoration: BoxDecoration(
                  color: Colors.white10,
                  borderRadius: BorderRadius.circular(8),
                  image: hasImage
                      ? DecorationImage(
                          image: NetworkImage(ep.stillPath!), // 需配合图片加载库
                          fit: BoxFit.cover,
                        )
                      : null,
                ),
                child: Stack(
                  children: [
                    if (!hasImage)
                      const Center(
                          child: Icon(Icons.movie,
                              color: Colors.white24, size: 24)),
                    // 播放中遮罩
                    if (selected)
                      Container(
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.5),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Center(
                          child: Icon(Icons.play_arrow,
                              color: Colors.white, size: 24),
                        ),
                      ),
                    // 时长/进度标签
                    Positioned(
                      right: 4,
                      bottom: 4,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 4, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.7),
                          borderRadius: BorderRadius.circular(2),
                        ),
                        child: Text(
                          ep.runtimeText ?? '00:00',
                          style: const TextStyle(
                              color: Colors.white, fontSize: 10),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              // 标题区域
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      ep.title.isEmpty
                          ? '第${ep.episodeNumber}集'
                          : '第${ep.episodeNumber}集 ${ep.title}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color:
                            selected ? const Color(0xFF1F7AE0) : Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        height: 1.2,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '未观看', // 占位状态
                      style: TextStyle(
                        color: selected
                            ? const Color(0xFF1F7AE0).withValues(alpha: 0.7)
                            : Colors.white38,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  int? _currentEpisodeIndex(PlaybackState s) {
    final currentFileId = s.currentEpisodeFileId ?? s.fileId;
    if (currentFileId == null) return null;
    final eps = s.episodes;
    for (var i = 0; i < eps.length; i++) {
      final assets = eps[i].assets;
      if (assets.isEmpty) continue;
      if (assets.first.fileId == currentFileId) return i;
    }
    return null;
  }
}

/// 侧边栏呼出/隐藏手柄
class DesktopSidePanelHandle extends StatelessWidget {
  final bool visible;
  final bool expanded;
  final VoidCallback onToggle;

  const DesktopSidePanelHandle({
    super.key,
    required this.visible,
    required this.expanded,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();

    // 垂直居中于播放区域右侧
    // 由于 Handle 位于播放区域 Stack 内，且播放区域会随侧边栏挤压而缩小，
    // 所以此处始终居右即可 (right: 0)
    return Positioned(
      right: 0,
      top: 0,
      bottom: 0,
      child: Center(
        child: InkWell(
          onTap: onToggle,
          child: Container(
            width: 24,
            height: 48,
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.6),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(8),
                bottomLeft: Radius.circular(8),
              ),
            ),
            child: Icon(
              expanded ? Icons.chevron_right : Icons.chevron_left,
              color: Colors.white70,
              size: 20,
            ),
          ),
        ),
      ),
    );
  }
}
