import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/playback_history/providers.dart';
import 'media_models.dart';
import 'widgets/recent_media_card.dart';

class RecentListPage extends ConsumerStatefulWidget {
  const RecentListPage({super.key});
  @override
  ConsumerState<RecentListPage> createState() => _RecentListPageState();
}

class _RecentListPageState extends ConsumerState<RecentListPage> {
  /// 当前已加载的最近观看条目（滚动分页加载）
  final List<RecentCardItem> _items = [];

  /// 是否正在加载下一页
  bool _loading = false;

  /// 错误提示文本（加载失败时显示）
  String? _error;

  /// 当前页码（从 1 开始）
  int _page = 1;

  /// 是否还有更多数据（用于触底加载）
  bool _hasMore = true;

  /// 列表滚动控制器（监听触底事件）
  final ScrollController _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    _load();
    _controller.addListener(_onScroll);
  }

  /// 加载一页最近观看记录
  Future<void> _load() async {
    if (_loading || !_hasMore) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(recentRepositoryProvider);
      final newItems = await repo.fetchRecentPage(
        page: _page,
        pageSize: 30,
        sort: 'updated_desc',
      );
      setState(() {
        _items.addAll(newItems);
        _page += 1;
        _hasMore = newItems.isNotEmpty;
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _hasMore = false;
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  /// 触底时自动加载下一页
  void _onScroll() {
    if (_controller.position.pixels >=
        _controller.position.maxScrollExtent - 300) {
      _load();
    }
  }

  /// 下拉刷新，重置分页并重新加载
  Future<void> _onRefresh() async {
    _items.clear();
    _page = 1;
    _hasMore = true;
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('最近观看'),
        // backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [TextButton(onPressed: _toggleEdit, child: const Text('编辑'))],
      ),
      body: RefreshIndicator(
        onRefresh: _onRefresh,
        child: _loading && _items.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : _error != null && _items.isEmpty
                ? Center(child: Text(_error!))
                : LayoutBuilder(
                    builder: (context, constraints) {
                      final width = constraints.maxWidth;
                      const padding = 12.0;
                      const spacing = 12.0;
                      const maxCrossAxisExtent = 300.0;
                      final crossAxisCount =
                          (width / maxCrossAxisExtent).ceil().clamp(1, 10);
                      final totalSpacing =
                          (crossAxisCount - 1) * spacing + padding * 2;
                      final itemWidth = (width - totalSpacing) / crossAxisCount;
                      // Image(16:9) + Spacing(8) + Text(~24) = ~32px extra
                      final itemHeight = itemWidth * 9 / 16 + 32;
                      final childAspectRatio = itemWidth / itemHeight;

                      return GridView.builder(
                        controller: _controller,
                        padding: const EdgeInsets.all(padding),
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: crossAxisCount,
                          mainAxisSpacing: spacing,
                          crossAxisSpacing: spacing,
                          childAspectRatio: childAspectRatio,
                        ),
                        itemBuilder: (ctx, i) {
                          final it = _items[i];
                          return Stack(
                            children: [
                              RecentMediaCard(
                                item: it,
                                onPlayReturn: () {
                                  _onRefresh();
                                },
                              ),
                              if (_editing)
                                Positioned(
                                  right: 8,
                                  top: 8,
                                  child: IconButton(
                                    icon: const Icon(
                                      Icons.close,
                                      color: Colors.white,
                                    ),
                                    style: ButtonStyle(
                                      backgroundColor: WidgetStateProperty.all(
                                        Colors.black45,
                                      ),
                                      padding: WidgetStateProperty.all(
                                        const EdgeInsets.all(4),
                                      ),
                                    ),
                                    onPressed: () => _remove(it),
                                  ),
                                ),
                            ],
                          );
                        },
                        itemCount: _items.length,
                      );
                    },
                  ),
      ),
    );
  }

  /// 是否处于编辑模式（支持从最近列表移除项）
  bool _editing = false;

  /// 切换编辑模式
  void _toggleEdit() {
    setState(() => _editing = !_editing);
  }

  /// 移除一条最近观看记录
  /// 调用后端 `DELETE /api/playback/progress/{file_id}` 并更新当前列表
  Future<void> _remove(RecentCardItem it) async {
    final fid = it.fileId;
    if (fid == null) return;
    try {
      final repo = ref.read(playbackProgressRepositoryProvider);
      await repo.deleteProgress(fileId: fid);
      if (!mounted) return;
      setState(() {
        _items.removeWhere((e) => e.fileId == fid);
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('移除失败：$e')));
    }
  }
}
