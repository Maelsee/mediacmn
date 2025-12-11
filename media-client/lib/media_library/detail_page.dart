import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'media_models.dart';
import '../core/api_client.dart';
import 'detail_widgets.dart';

/// 媒体详情页组件，展示电影或剧集的详细信息并提供播放入口。
/// 入口参数为 `mediaId`，通过 Provider 拉取 `MediaDetail` 并渲染。
class MediaDetailPage extends ConsumerStatefulWidget {
  final int mediaId;
  final HomeCardItem? previewItem;
  const MediaDetailPage({super.key, required this.mediaId, this.previewItem});

  @override
  ConsumerState<MediaDetailPage> createState() => _MediaDetailPageState();
}

/// 详情页本地状态：维护剧情简介展开、季/集/资源选择索引与播放进度等。
class _MediaDetailPageState extends ConsumerState<MediaDetailPage> {
  int? _selectedSeasonIndex;
  int? _selectedEpisodeIndex;
  int? _selectedVersionIndex;
  Color? _backgroundColor;

  @override

  /// 构建详情页：
  /// - 通过 Provider 异步拉取 `MediaDetail`
  /// - 顶部使用 `SliverToBoxAdapter` 放置背景模块，使其与内容**整体上滑**
  /// - 使用 `Stack` 在最上层覆盖透明 `AppBar`，保留返回与操作按钮
  /// - `Scaffold.backgroundColor` 取自背景图提取的主色，保证“无限向下延伸”
  Widget build(BuildContext context) {
    final AsyncValue<MediaDetail> detail =
        ref.watch(_detailProvider(widget.mediaId));

    return Scaffold(
      backgroundColor:
          _backgroundColor ?? Theme.of(context).colorScheme.surface,
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, st) => Center(child: Text('加载失败：$e')),
        data: (d) {
          // Ensure indices are valid
          // 初始化选择索引：
          // - 剧集：默认选中第 0 季与第 0 集
          // - 电影：默认选中第 0 版本
          if (d.mediaType == 'movie') {
            if (_selectedVersionIndex == null &&
                d.versions != null &&
                d.versions!.isNotEmpty) {
              _selectedVersionIndex = 0;
            }
          }
          if (d.mediaType == 'tv' || d.mediaType == 'animation') {
            if (_selectedSeasonIndex == null &&
                d.seasons != null &&
                d.seasons!.isNotEmpty) {
              _selectedSeasonIndex = 0;
            }
            if (_selectedEpisodeIndex == null &&
                d.seasons != null &&
                d.seasons!.isNotEmpty) {
              // Reset episode when season changes or init
              _selectedEpisodeIndex = 0;
            }
          }
          

          return Stack(
            children: [
              CustomScrollView(
                slivers: [
                  // 1. Background Image Section (Moves with content)
                  // 将背景作为列表首项，确保与内容整体同速滑动，无视差与折叠。
                  SliverToBoxAdapter(
                    child: SizedBox(
                      height: MediaQuery.of(context).size.height * 0.6,
                      child: DetailBackground(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                        onColorChanged: (color) {
                          if (_backgroundColor != color) {
                            setState(() {
                              _backgroundColor = color;
                            });
                          }
                        },
                      ),
                    ),
                  ),

                  // 2. Content List
                  SliverList(
                    delegate: SliverChildListDelegate([
                      // 2. Title Module
                      DetailTitle(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                      ),

                      // 3. Info Module
                      DetailInfo(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                      ),

                      // 7. Play Button Module
                      DetailPlayButton(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                        selectedEpisodeIndex: _selectedEpisodeIndex,
                        selectedVersionIndex: _selectedVersionIndex,
                      ),

                      // 9. Seasons & Episodes Module (TV Only)
                      DetailSeasonsEpisodes(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex ?? 0,
                        selectedEpisodeIndex: _selectedEpisodeIndex ?? 0,
                        onSeasonSelected: (index) {
                          setState(() {
                            _selectedSeasonIndex = index;
                            _selectedEpisodeIndex = 0; // Reset episode
                          });
                        },
                        onEpisodeSelected: (index) {
                          setState(() {
                            _selectedEpisodeIndex = index;
                          });
                        },
                      ),

                      // 8. Versions Module (Movie Only)
                      // Moved before overview as requested
                      DetailVersions(
                        detail: d,
                        selectedVersionIndex: _selectedVersionIndex ?? 0,
                        onVersionSelected: (index) {
                          setState(() {
                            _selectedVersionIndex = index;
                          });
                        },
                      ),

                      // 4. Overview Module
                      DetailOverview(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                      ),

                      // 5. Cast Module
                      DetailCast(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                      ),

                      // 6. Path Module
                      DetailPath(
                        detail: d,
                        selectedSeasonIndex: _selectedSeasonIndex,
                        selectedEpisodeIndex: _selectedEpisodeIndex,
                        selectedVersionIndex: _selectedVersionIndex,
                      ),

                      const SizedBox(height: 32),
                    ]),
                  ),
                ],
              ),

              // Floating App Bar (Back button & Actions)
              // 顶部悬浮的透明 AppBar，覆盖在内容之上，不参与滚动。
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: AppBar(
                  backgroundColor: Colors.transparent,
                  elevation: 0,
                  leading: IconButton(
                    icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
                    onPressed: () => context.pop(),
                  ),
                  actions: [
                    IconButton(
                      icon: const Icon(Icons.download_for_offline_outlined,
                          color: Colors.white),
                      onPressed: () {},
                    ),
                    IconButton(
                      icon: const Icon(Icons.more_horiz, color: Colors.white),
                      onPressed: () {},
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// 详情数据 Provider：按媒体 ID 拉取 `MediaDetail`。
final _detailProvider =
    FutureProvider.family<MediaDetail, int>((ref, id) async {
  final api = ref.read(apiClientProvider);
  return api.getMediaDetail(id);
});
