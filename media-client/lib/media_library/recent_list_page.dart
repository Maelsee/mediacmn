import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
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
      final api = ref.read(apiClientProvider);
      final raw = await api.getRecentRaw(
          page: _page, pageSize: 30, sort: 'updated_desc');
      final newItems = raw.map((e) => RecentCardItem.fromApi(e)).toList();
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
      appBar: AppBar(title: const Text('最近观看'), actions: [
        TextButton(onPressed: _toggleEdit, child: const Text('编辑'))
      ]),
      body: RefreshIndicator(
        onRefresh: _onRefresh,
        child: _loading && _items.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : _error != null && _items.isEmpty
                ? Center(child: Text(_error!))
                : GridView.builder(
                    controller: _controller,
                    padding: const EdgeInsets.all(12),
                    gridDelegate:
                        const SliverGridDelegateWithMaxCrossAxisExtent(
                      maxCrossAxisExtent: 300, // 限制最大宽度，使大屏下能显示多列，小屏显示1-2列
                      mainAxisSpacing: 12,
                      crossAxisSpacing: 12,
                      mainAxisExtent: 170, // 减小高度，去除多余垂直间隙 (适配 240x180 比例)
                    ),
                    itemBuilder: (ctx, i) {
                      final it = _items[i];
                      return Stack(
                        children: [
                          Center(
                            // 居中显示，宽度自适应但受限于卡片内部最大宽度或容器
                            child: RecentMediaCard(
                              item: it,
                              onPlayReturn: () {
                                _onRefresh();
                              },
                            ),
                          ),
                          if (_editing)
                            Positioned(
                              right: 8,
                              top: 8,
                              child: IconButton(
                                icon: const Icon(Icons.close,
                                    color: Colors.white),
                                style: ButtonStyle(
                                  backgroundColor:
                                      WidgetStateProperty.all(Colors.black45),
                                  padding: WidgetStateProperty.all(
                                      const EdgeInsets.all(4)),
                                ),
                                onPressed: () => _remove(it),
                              ),
                            ),
                        ],
                      );
                    },
                    itemCount: _items.length,
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
      final api = ref.read(apiClientProvider);
      await api.deletePlaybackProgress(fid);
      if (!mounted) return;
      setState(() {
        _items.removeWhere((e) => e.fileId == fid);
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('移除失败：$e')));
    }
  }
}
