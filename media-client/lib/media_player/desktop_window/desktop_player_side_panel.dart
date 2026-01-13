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

    const itemExtent = 56.0;
    final offset = (idx * itemExtent) - 3 * itemExtent;
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
    final episodes = widget.state.episodes;
    final currentIdx = _currentEpisodeIndex(widget.state);

    return Positioned.fill(
      child: Stack(
        children: [
          Positioned.fill(
            child: IgnorePointer(
              ignoring: !widget.visible,
              child: AnimatedOpacity(
                duration: const Duration(milliseconds: 180),
                opacity: widget.visible ? 1 : 0,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: widget.onClose,
                  child: Container(color: Colors.black.withValues(alpha: 0.35)),
                ),
              ),
            ),
          ),
          AnimatedPositioned(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
            top: 0,
            bottom: 0,
            right: widget.visible ? 0 : -kDesktopSidePanelWidth,
            width: kDesktopSidePanelWidth,
            child: Material(
              color: const Color(0xFF141414),
              child: Column(
                children: [
                  _SidePanelHeader(
                    title: _buildHeaderTitle(widget.state),
                    onClose: widget.onClose,
                  ),
                  const Divider(height: 1, color: Color(0xFF2A2A2A)),
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
                        if (widget.state.episodesError != null &&
                            episodes.isEmpty) {
                          return Center(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Text(
                                widget.state.episodesError!,
                                style: const TextStyle(
                                    color: Colors.white70, fontSize: 12),
                                textAlign: TextAlign.center,
                              ),
                            ),
                          );
                        }
                        if (episodes.isEmpty) {
                          return const Center(
                            child: Text('暂无选集',
                                style: TextStyle(color: Colors.white70)),
                          );
                        }

                        return ListView.builder(
                          controller: _scrollController,
                          itemCount: episodes.length,
                          itemExtent: 56,
                          itemBuilder: (context, index) {
                            final ep = episodes[index];
                            final selected = currentIdx == index;
                            final title = _formatEpisodeTitle(ep);
                            final subtitle = ep.runtimeText;

                            return InkWell(
                              onTap: () async {
                                await widget.onEpisodeTap(index);
                                if (mounted) widget.onClose();
                              },
                              child: Container(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 14),
                                decoration: BoxDecoration(
                                  color: selected
                                      ? const Color(0xFF1F2A3A)
                                      : Colors.transparent,
                                  border: const Border(
                                    bottom: BorderSide(
                                        color: Color(0xFF202020), width: 1),
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    Container(
                                      width: 6,
                                      height: 6,
                                      decoration: BoxDecoration(
                                        shape: BoxShape.circle,
                                        color: selected
                                            ? const Color(0xFFFFD700)
                                            : const Color(0xFF5A5A5A),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Column(
                                        mainAxisAlignment:
                                            MainAxisAlignment.center,
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            title,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(
                                              color: selected
                                                  ? Colors.white
                                                  : Colors.white70,
                                              fontSize: 13,
                                              fontWeight: selected
                                                  ? FontWeight.w600
                                                  : FontWeight.normal,
                                            ),
                                          ),
                                          if (subtitle != null &&
                                              subtitle.isNotEmpty)
                                            Text(
                                              subtitle,
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                              style: TextStyle(
                                                color: selected
                                                    ? Colors.white70
                                                    : Colors.white38,
                                                fontSize: 11,
                                              ),
                                            ),
                                        ],
                                      ),
                                    ),
                                    if (selected)
                                      const Icon(Icons.play_arrow,
                                          color: Color(0xFFFFD700), size: 18),
                                  ],
                                ),
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
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

  String _buildHeaderTitle(PlaybackState s) {
    final base = (s.detail?.title ?? s.title ?? '').trim();
    if (base.isNotEmpty) return base;
    return '选集';
  }

  String _formatEpisodeTitle(EpisodeDetail ep) {
    final num = ep.episodeNumber;
    final title = ep.title.trim();
    if (num > 0 && title.isNotEmpty) return '第$num集  $title';
    if (num > 0) return '第$num集';
    if (title.isNotEmpty) return title;
    return '未命名';
  }
}

class _SidePanelHeader extends StatelessWidget {
  final String title;
  final VoidCallback onClose;

  const _SidePanelHeader({
    required this.title,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: Row(
        children: [
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          IconButton(
            tooltip: '关闭',
            onPressed: onClose,
            icon: const Icon(Icons.close, color: Colors.white),
          ),
        ],
      ),
    );
  }
}

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
    return Positioned(
      right: expanded ? kDesktopSidePanelWidth : 0,
      top: 0,
      bottom: 0,
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 180),
        opacity: visible ? 1 : 0,
        child: IgnorePointer(
          ignoring: !visible,
          child: Center(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onToggle,
              child: Container(
                width: 22,
                height: 68,
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.35),
                  borderRadius: const BorderRadius.horizontal(
                    left: Radius.circular(10),
                  ),
                  border: Border.all(color: Colors.white12),
                ),
                child: Icon(
                  expanded ? Icons.chevron_right : Icons.chevron_left,
                  color: Colors.white70,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
