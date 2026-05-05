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
  final _focusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onSearch() {
    final keyword = _searchController.text.trim();
    if (keyword.isEmpty) return;
    _focusNode.unfocus();
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
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Container(
          height: 40,
          decoration: BoxDecoration(
            color: Colors.white.withAlpha(26),
            borderRadius: BorderRadius.circular(20),
          ),
          child: TextField(
            controller: _searchController,
            focusNode: _focusNode,
            style: const TextStyle(color: Colors.white, fontSize: 15),
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: '搜索影视名称...',
              hintStyle: TextStyle(color: Colors.white.withAlpha(102)),
              prefixIcon: Icon(Icons.search,
                  color: Colors.white.withAlpha(102), size: 20),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: Icon(Icons.clear,
                          color: Colors.white.withAlpha(102), size: 18),
                      onPressed: () {
                        _searchController.clear();
                        setState(() {});
                      },
                    )
                  : null,
              border: InputBorder.none,
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => _onSearch(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _onSearch,
            child: const Text('搜索',
                style: TextStyle(color: Color(0xFFFFE796), fontSize: 15)),
          ),
        ],
      ),
      body: state.searchLoading
          ? const Center(child: CircularProgressIndicator())
          : state.searchResults.isEmpty
              ? SingleChildScrollView(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 80),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.search,
                              size: 64, color: Colors.white.withAlpha(51)),
                          const SizedBox(height: 16),
                          Text(
                            '输入影视名称搜索弹幕源',
                            style: TextStyle(
                                color: Colors.white.withAlpha(102),
                                fontSize: 15),
                          ),
                        ],
                      ),
                    ),
                  ),
                )
              : ListView.separated(
                  itemCount: state.searchResults.length,
                  separatorBuilder: (_, __) =>
                      Divider(height: 1, color: Colors.white.withAlpha(13)),
                  itemBuilder: (context, index) {
                    final item = state.searchResults[index];
                    return ListTile(
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 8),
                      leading: ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: item.imageUrl.isNotEmpty
                            ? Image.network(item.imageUrl,
                                width: 48,
                                height: 64,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) =>
                                    Container(
                                        width: 48,
                                        height: 64,
                                        color: Colors.white.withAlpha(13)))
                            : Container(
                                width: 48,
                                height: 64,
                                color: Colors.white.withAlpha(13),
                                child: const Icon(Icons.movie,
                                    color: Colors.white38, size: 24)),
                      ),
                      title: Text(item.animeTitle,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 15)),
                      subtitle: Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Row(
                          children: [
                            if (item.typeDescription.isNotEmpty)
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 6, vertical: 2),
                                margin: const EdgeInsets.only(right: 8),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFFFE796).withAlpha(26),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(item.typeDescription,
                                    style: const TextStyle(
                                        color: Color(0xFFFFE796),
                                        fontSize: 11)),
                              ),
                            Text('共${item.episodeCount}集',
                                style: const TextStyle(
                                    color: Colors.white54, fontSize: 12)),
                          ],
                        ),
                      ),
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
        .selectEpisodeFromBangumi(
          episodeId: episode.episodeId,
          animeId: widget.animeId,
          animeTitle: widget.title,
          episodeTitle: episode.episodeTitle,
          type: _bangumi?.type ?? '',
          typeDescription: _bangumi?.type ?? '',
          imageUrl: _bangumi?.imageUrl ?? '',
        );
    // pop bangumi page + search page，回到播放器
    Navigator.of(context).pop();
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1E1E1E),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(widget.title,
            style: const TextStyle(color: Colors.white, fontSize: 16)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline,
                          color: Colors.white38, size: 48),
                      const SizedBox(height: 12),
                      Text('加载失败: $_error',
                          style: const TextStyle(color: Colors.white54)),
                    ],
                  ),
                )
              : _bangumi == null
                  ? const SizedBox.shrink()
                  : ListView(
                      children: [
                        if (_bangumi!.imageUrl.isNotEmpty)
                          Container(
                            height: 180,
                            width: double.infinity,
                            decoration: BoxDecoration(
                              image: DecorationImage(
                                image: NetworkImage(_bangumi!.imageUrl),
                                fit: BoxFit.cover,
                                onError: (_, __) {},
                              ),
                            ),
                            child: Container(
                              decoration: const BoxDecoration(
                                gradient: LinearGradient(
                                  begin: Alignment.topCenter,
                                  end: Alignment.bottomCenter,
                                  colors: [Colors.transparent, Color(0xFF1E1E1E)],
                                ),
                              ),
                              alignment: Alignment.bottomLeft,
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(_bangumi!.animeTitle,
                                      style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 18,
                                          fontWeight: FontWeight.bold)),
                                  if (_bangumi!.type.isNotEmpty)
                                    Padding(
                                      padding: const EdgeInsets.only(top: 4),
                                      child: Text(_bangumi!.type,
                                          style: const TextStyle(
                                              color: Colors.white54,
                                              fontSize: 13)),
                                    ),
                                ],
                              ),
                            ),
                          ),
                        for (final season in _bangumi!.seasons) ...[
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                            child: Row(
                              children: [
                                Text(season.name,
                                    style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.w600)),
                                const SizedBox(width: 8),
                                Text('${season.episodeCount}集',
                                    style: const TextStyle(
                                        color: Colors.white54, fontSize: 13)),
                              ],
                            ),
                          ),
                          ..._bangumi!.episodes
                              .where((e) => e.seasonId == season.id)
                              .map((episode) => ListTile(
                                    contentPadding: const EdgeInsets.symmetric(
                                        horizontal: 16, vertical: 2),
                                    leading: Container(
                                      width: 36,
                                      height: 36,
                                      alignment: Alignment.center,
                                      decoration: BoxDecoration(
                                        color: Colors.white.withAlpha(13),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Text(
                                        episode.episodeNumber,
                                        style: const TextStyle(
                                            color: Colors.white70,
                                            fontSize: 13),
                                      ),
                                    ),
                                    title: Text(episode.episodeTitle,
                                        style: const TextStyle(
                                            color: Colors.white70,
                                            fontSize: 14)),
                                    onTap: () => _selectEpisode(episode),
                                  )),
                        ],
                        const SizedBox(height: 32),
                      ],
                    ),
    );
  }
}
