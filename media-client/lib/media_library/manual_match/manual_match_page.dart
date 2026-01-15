import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../media_detail_provider.dart';
import '../media_models.dart';
import 'manual_match_models.dart';
import 'manual_match_notifier.dart';
import 'manual_match_provider.dart';
import 'manual_match_state.dart';
import 'widgets/episode_picker_sheet.dart';
import 'widgets/tmdb_search_result_tile.dart';

class ManualMatchPage extends ConsumerStatefulWidget {
  final int mediaId;
  final MediaDetail? snapshot;
  final int seasonIndex;
  final int versionIndex;

  const ManualMatchPage({
    super.key,
    required this.mediaId,
    this.snapshot,
    this.seasonIndex = 0,
    this.versionIndex = 0,
  });

  @override
  ConsumerState<ManualMatchPage> createState() => _ManualMatchPageState();
}

class _ManualMatchPageState extends ConsumerState<ManualMatchPage> {
  final TextEditingController _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    // 初始化文件列表
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initFiles();
    });
  }

  void _initFiles() {
    // 优先使用 snapshot，否则尝试从 provider 读
    MediaDetail? detail = widget.snapshot;
    if (detail == null) {
      final asyncValue = ref.read(mediaDetailProvider(widget.mediaId));
      detail = asyncValue.value;
    }

    if (detail != null) {
      ref.read(manualMatchProvider(widget.mediaId).notifier).initFiles(
            detail,
            seasonIndex: widget.seasonIndex,
            versionIndex: widget.versionIndex,
          );
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(manualMatchProvider(widget.mediaId));
    final notifier = ref.read(manualMatchProvider(widget.mediaId).notifier);

    // 监听保存错误
    ref.listen(manualMatchProvider(widget.mediaId), (prev, next) {
      if (next.saveError != null && next.saveError != prev?.saveError) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(next.saveError!)));
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('编辑信息'),
        actions: [
          TextButton(
            onPressed: (state.saving ||
                    state.selectedTmdbItem == null ||
                    (state.selectedTmdbItem?.type == 'tv' &&
                        state.selectedSeason == null))
                ? null
                : () async {
                    final success = await notifier.save();
                    if (!context.mounted) return;

                    if (success) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('保存成功，正在刷新...')),
                      );
                      // 刷新详情页数据
                      ref.invalidate(mediaDetailProvider(widget.mediaId));
                      context.pop();
                    }
                  },
            child: state.saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('保存'),
          ),
        ],
      ),
      body: Column(
        children: [
          // 顶部路径信息（可选，简单展示首个文件的路径摘要）
          if (state.fileItems.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: Theme.of(
                context,
              ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(
                        Icons.description_outlined,
                        size: 14,
                        color: Colors.grey,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '${state.fileItems.length} 个文件',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  if (state.filePathHint?.isNotEmpty == true) ...[
                    const SizedBox(height: 4),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 2),
                          child: Icon(
                            Icons.folder_open,
                            size: 14,
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            state.filePathHint!,
                            style: Theme.of(context).textTheme.bodySmall,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),

          // 搜索区域
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '搜索并匹配影片',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                if (state.selectedTmdbItem == null)
                  TextField(
                    controller: _searchController,
                    decoration: InputDecoration(
                      hintText: '请输入完整的电影或电视剧名称',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: TextButton(
                        onPressed: () =>
                            notifier.search(_searchController.text),
                        child: const Text('搜索'),
                      ),
                      filled: true,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                      ),
                    ),
                    onSubmitted: notifier.search,
                  )
                else
                  // 已选中状态：展示选中卡片 + 取消按钮
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Theme.of(context)
                          .colorScheme
                          .surfaceContainerHighest
                          .withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        // 小海报
                        ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: SizedBox(
                            width: 40,
                            height: 60,
                            child: state.selectedTmdbItem?.posterPath != null
                                ? Image.network(
                                    'https://image.tmdb.org/t/p/w200${state.selectedTmdbItem!.posterPath}',
                                    fit: BoxFit.cover,
                                    errorBuilder: (_, __, ___) =>
                                        Container(color: Colors.grey),
                                  )
                                : Container(color: Colors.grey),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                state.selectedTmdbItem!.title,
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              Text(
                                '${state.selectedTmdbItem!.type == 'movie' ? '电影' : '剧集'} · ${state.selectedTmdbItem!.releaseDate?.split('-').first ?? ''}',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: () {
                            notifier.clearSelection();
                          },
                          child: const Text('取消'),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),

          // 搜索结果列表 (未选中时显示)
          if (state.selectedTmdbItem == null)
            Expanded(
              child: state.searching
                  ? const Center(child: CircularProgressIndicator())
                  : state.searchError != null
                      ? Center(child: Text(state.searchError!))
                      : state.searchResults.isEmpty
                          ? Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: const [
                                  Icon(
                                    Icons.movie_filter,
                                    size: 48,
                                    color: Colors.grey,
                                  ),
                                  SizedBox(height: 16),
                                  Text(
                                    '仅搜索影片名，暂不支持搜索演员',
                                    style: TextStyle(color: Colors.grey),
                                  ),
                                ],
                              ),
                            )
                          : ListView.builder(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 16),
                              itemCount: state.searchResults.length,
                              itemBuilder: (context, index) {
                                final item = state.searchResults[index];
                                return TmdbSearchResultTile(
                                  item: item,
                                  isSelected: false,
                                  onTap: () => notifier.selectTmdbItem(item),
                                );
                              },
                            ),
            ),

          // 匹配配置区域 (选中后显示)
          if (state.selectedTmdbItem != null)
            Expanded(
              child: Column(
                children: [
                  // TV: 选择季
                  if (state.selectedTmdbItem!.type == 'tv')
                    ListTile(
                      title: const Text('选择季'),
                      subtitle: Text(state.selectedSeason?.name ?? '请选择 >'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () {
                        if (state.loadingSeasons) return;
                        _showSeasonPicker(context, state, notifier);
                      },
                    ),

                  const Divider(height: 1),

                  // 文件列表
                  if (state.selectedTmdbItem!.type == 'movie' ||
                      (state.selectedTmdbItem!.type == 'tv' &&
                          state.selectedSeason != null))
                    Expanded(
                      child: state.loadingEpisodes
                          ? const Center(child: CircularProgressIndicator())
                          : ListView.separated(
                              itemCount: state.fileItems.length,
                              separatorBuilder: (_, __) =>
                                  const Divider(height: 1, indent: 16),
                              itemBuilder: (context, index) {
                                final file = state.fileItems[index];
                                final choice = state.draftChoices[file.fileId];

                                return ListTile(
                                  title: Text(
                                    file.displayName,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  subtitle: Text(
                                    file.path,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontSize: 10,
                                      color: Colors.grey,
                                    ),
                                  ),
                                  trailing: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      _buildChoiceChip(context, choice, file),
                                      const Icon(
                                        Icons.chevron_right,
                                        size: 16,
                                        color: Colors.grey,
                                      ),
                                    ],
                                  ),
                                  onTap: () {
                                    // 打开选集面板
                                    _showEpisodePicker(
                                      context,
                                      state,
                                      notifier,
                                      file,
                                      choice,
                                    );
                                  },
                                );
                              },
                            ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildChoiceChip(
    BuildContext context,
    ManualMatchChoice? choice,
    ManualMatchFileItem file,
  ) {
    String label = '暂不改动';
    Color color = Colors.grey;

    if (choice != null) {
      if (choice.action == 'keep') {
        label = '暂不改动';
      } else if (choice.action == 'other') {
        label = '其他';
        color = Colors.orange;
      } else if (choice.action == 'bind_movie') {
        label = '已绑定新电影';
        color = Colors.blue;
      } else if (choice.action == 'bind_episode') {
        label = '第 ${choice.episodeNumber} 集';
        color = Colors.green;
      }
    } else {
      // 默认展示原状态
      if (file.currentEpisodeNumber != null) {
        label = '原: 第 ${file.currentEpisodeNumber} 集';
      }
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(label, style: TextStyle(fontSize: 12, color: color)),
    );
  }

  void _showSeasonPicker(
    BuildContext context,
    ManualMatchState state,
    ManualMatchNotifier notifier,
  ) {
    showModalBottomSheet(
      context: context,
      builder: (context) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                '选择季',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
            Expanded(
              child: ListView.builder(
                itemCount: state.seasonList.length,
                itemBuilder: (context, index) {
                  final s = state.seasonList[index];
                  return ListTile(
                    title: Text(s.name),
                    subtitle: Text('${s.episodeCount} 集 | ${s.airDate ?? ''}'),
                    onTap: () {
                      notifier.selectSeason(s);
                      Navigator.pop(context);
                    },
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }

  void _showEpisodePicker(
    BuildContext context,
    ManualMatchState state,
    ManualMatchNotifier notifier,
    ManualMatchFileItem file,
    ManualMatchChoice? currentChoice,
  ) {
    // 如果是电影，不需要选集，直接是“绑定/不绑定”？
    // 简化处理：电影也弹窗，但只有 keep/other/bind_movie

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return EpisodePickerSheet(
          file: file,
          season: state.selectedSeason,
          episodes: state.episodeList,
          currentChoice: currentChoice,
          tmdbTvId: state.selectedTmdbItem?.tmdbId,
          tmdbSeasonId: state.selectedSeason?.tmdbSeasonId,
          onSelected: (choice) {
            notifier.updateChoice(file.fileId, choice);
          },
        );
      },
    );
  }
}
