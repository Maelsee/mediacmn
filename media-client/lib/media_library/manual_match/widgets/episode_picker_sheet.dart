import 'package:flutter/material.dart';
import '../manual_match_models.dart';

class EpisodePickerSheet extends StatefulWidget {
  final ManualMatchFileItem file;
  final TmdbSeasonItem? season; // 仅 TV 有效
  final List<TmdbEpisodeItem> episodes; // 仅 TV 有效
  final ManualMatchChoice? currentChoice;
  final Function(ManualMatchChoice) onSelected;
  final int? tmdbTvId; // TV ID
  final int? tmdbSeasonId; // Season ID

  const EpisodePickerSheet({
    super.key,
    required this.file,
    this.season,
    this.episodes = const [],
    this.currentChoice,
    required this.onSelected,
    this.tmdbTvId,
    this.tmdbSeasonId,
  });

  @override
  State<EpisodePickerSheet> createState() => _EpisodePickerSheetState();
}

class _EpisodePickerSheetState extends State<EpisodePickerSheet> {
  late ManualMatchChoice _selected;

  @override
  void initState() {
    super.initState();
    _selected = widget.currentChoice ?? ManualMatchChoice.keep();
  }

  @override
  Widget build(BuildContext context) {
    final height = MediaQuery.sizeOf(context).height;

    return SizedBox(
      height: height * 0.82,
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
        ),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const SizedBox(width: 40),
                  const Text(
                    '选择集',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('文件信息：', style: TextStyle(color: Colors.grey)),
                  const SizedBox(height: 4),
                  Text(
                    widget.file.displayName,
                    style: const TextStyle(fontWeight: FontWeight.w500),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                children: [
                  _buildRadioItem(
                    title: '暂不改动',
                    subtitle: '维持该文件原匹配信息',
                    value: 'keep',
                    isSelected: _selected.action == 'keep',
                    onTap: () {
                      widget.onSelected(ManualMatchChoice.keep());
                      Navigator.pop(context);
                    },
                  ),
                  _buildRadioItem(
                    title: '其他',
                    subtitle: '该文件将被归入“其他”',
                    value: 'other',
                    isSelected: _selected.action == 'other',
                    onTap: () {
                      widget.onSelected(ManualMatchChoice.other());
                      Navigator.pop(context);
                    },
                  ),
                  if (widget.episodes.isNotEmpty && widget.season != null)
                    ...widget.episodes.map((ep) {
                      final isSelected = _selected.action == 'bind_episode' &&
                          _selected.episodeNumber == ep.episodeNumber;
                      return _buildRadioItem(
                        title: '第 ${ep.episodeNumber} 集 ${ep.name}',
                        value: 'ep_${ep.episodeNumber}',
                        isSelected: isSelected,
                        onTap: () {
                          widget.onSelected(
                            ManualMatchChoice.bindEpisode(
                              tmdbTvId: widget.tmdbTvId!,
                              tmdbSeasonId: widget.tmdbSeasonId ?? 0,
                              tmdbEpisodeId: ep.tmdbEpisodeId,
                              seasonNumber: widget.season!.seasonNumber,
                              episodeNumber: ep.episodeNumber,
                            ),
                          );
                          Navigator.pop(context);
                        },
                      );
                    }),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRadioItem({
    required String title,
    String? subtitle,
    required String value,
    required bool isSelected,
    VoidCallback? onTap,
  }) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 15,
                      color: isSelected
                          ? Theme.of(context).colorScheme.primary
                          : null,
                    ),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey.shade600,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Icon(
              isSelected ? Icons.radio_button_checked : Icons.radio_button_off,
              color: isSelected
                  ? Theme.of(context).colorScheme.primary
                  : Theme.of(context).disabledColor,
            ),
          ],
        ),
      ),
    );
  }
}
