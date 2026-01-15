import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'media_models.dart';
import 'widgets/media_card.dart';
import '../source_library/tasks/task_provider.dart';

class MediaKindPage extends ConsumerStatefulWidget {
  final String? title;
  final String? kind;
  final List<String>? genres;
  const MediaKindPage({super.key, this.title, this.kind, this.genres});

  @override
  ConsumerState<MediaKindPage> createState() => _MediaKindPageState();
}

class _MediaKindPageState extends ConsumerState<MediaKindPage> {
  final List<HomeCardItem> _items = [];
  int _page = 1;
  bool _hasMore = true;
  bool _loading = false;
  String? _error;
  final ScrollController _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    _load();
    _controller.addListener(_onScroll);
  }

  Future<void> _load() async {
    if (_loading || !_hasMore) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final res = await api.searchMedia(
        '',
        page: _page,
        pageSize: 30,
        kind: widget.kind,
        genres: widget.genres,
      );
      setState(() {
        _items.addAll(res.items);
        _page += 1;
        _hasMore = _items.length < res.total;
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _hasMore = false;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _onScroll() {
    if (_controller.position.pixels >=
        _controller.position.maxScrollExtent - 300) {
      _load();
    }
  }

  Future<void> _onRefresh() async {
    _items.clear();
    _page = 1;
    _hasMore = true;
    await _load();
  }

  @override
  void dispose() {
    _controller.removeListener(_onScroll);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title ?? '全部'),
        // backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Column(
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text('加载失败：$_error'),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _onRefresh,
              child: GridView.builder(
                controller: _controller,
                padding: const EdgeInsets.all(12),
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 150,
                  mainAxisExtent: 220,
                  mainAxisSpacing: 8,
                  crossAxisSpacing: 12,
                ),
                itemCount: _items.length + (_loading ? 9 : 0),
                itemBuilder: (ctx, i) {
                  if (i < _items.length) {
                    final it = _items[i];
                    return MediaCard(
                      item: it,
                      width: double.infinity,
                      height: 220,
                    );
                  }
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: AspectRatio(
                          aspectRatio: 0.68,
                          child: Container(color: Colors.grey.shade300),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Container(
                        height: 14,
                        width: 80,
                        color: Colors.grey.shade300,
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
