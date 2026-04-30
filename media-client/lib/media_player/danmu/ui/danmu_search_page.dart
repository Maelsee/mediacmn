import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../provider/danmu_provider.dart';
import '../models/danmu_models.dart';
import '../../../core/api_client.dart';
import '../api/danmu_api.dart';

class DanmuSearchPage extends ConsumerStatefulWidget {
  final String fileId;

  const DanmuSearchPage({super.key, required this.fileId});

  @override
  ConsumerState<DanmuSearchPage> createState() => _DanmuSearchPageState();
}

class _DanmuSearchPageState extends ConsumerState<DanmuSearchPage> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onSearch() {
    final keyword = _searchController.text.trim();
    if (keyword.isEmpty) return;
    ref.read(danmuProvider(widget.fileId).notifier).search(keyword);
  }

  void _goToBangumiDetail(DanmuSearchItem item) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => _DanmuBangumiPage(
        fileId: widget.fileId,
        animeId: item.animeId,
        title: item.animeTitle,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(danmuProvider(widget.fileId));

    return Scaffold(
      backgroundColor: const Color(0xFF1E1E1E),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: TextField(
          controller: _searchController,
          style: const TextStyle(color: Colors.white),
          decoration: const InputDecoration(
            hintText: '输入影视名称搜索弹幕',
            hintStyle: TextStyle(color: Colors.white54),
            border: InputBorder.none,
          ),
          onSubmitted: (_) => _onSearch(),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: _onSearch,
          ),
        ],
      ),
      body: state.searchLoading
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              itemCount: state.searchResults.length,
              itemBuilder: (context, index) {
                final item = state.searchResults[index];
                return ListTile(
                  leading: item.imageUrl.isNotEmpty
                      ? Image.network(item.imageUrl,
                          width: 50, height: 70, fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) =>
                              const SizedBox(width: 50, height: 70))
                      : const SizedBox(width: 50, height: 70),
                  title: Text(item.animeTitle,
                      style: const TextStyle(color: Colors.white)),
                  subtitle: Text(
                      '${item.typeDescription} · 共${item.episodeCount}集',
                      style: const TextStyle(color: Colors.white54)),
                  onTap: () => _goToBangumiDetail(item),
                );
              },
            ),
    );
  }
}

class _DanmuBangumiPage extends ConsumerStatefulWidget {
  final String fileId;
  final int animeId;
  final String title;

  const _DanmuBangumiPage({
    required this.fileId,
    required this.animeId,
    required this.title,
  });

  @override
  ConsumerState<_DanmuBangumiPage> createState() => _DanmuBangumiPageState();
}

class _DanmuBangumiPageState extends ConsumerState<_DanmuBangumiPage> {
  bool _loading = true;
  DanmuBangumi? _bangumi;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadBangumi();
  }

  Future<void> _loadBangumi() async {
    try {
      final api = ref.read(apiClientProvider);
      final bangumi = await api.getDanmuBangumi(widget.animeId);
      setState(() {
        _bangumi = bangumi;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _selectEpisode(DanmuEpisode episode) {
    ref
        .read(danmuProvider(widget.fileId).notifier)
        .selectEpisode(episode.episodeId);
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1E1E1E),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(widget.title),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Text('加载失败: $_error',
                      style: const TextStyle(color: Colors.red)))
              : _bangumi == null
                  ? const SizedBox.shrink()
                  : ListView(
                      children: [
                        for (final season in _bangumi!.seasons) ...[
                          Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                                '${season.name} (${season.episodeCount}集)',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold)),
                          ),
                          ..._bangumi!.episodes
                              .where((e) => e.seasonId == season.id)
                              .map((episode) => ListTile(
                                    title: Text(episode.episodeTitle,
                                        style: const TextStyle(
                                            color: Colors.white70)),
                                    onTap: () => _selectEpisode(episode),
                                  ))
                        ]
                      ],
                    ),
    );
  }
}
