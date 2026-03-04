import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import 'media_models.dart';
import 'widgets/media_card.dart';

class SearchPage extends ConsumerStatefulWidget {
  final String? initialKind;
  final String? initialTitle;
  final String? initialGenre;

  const SearchPage({
    super.key,
    this.initialKind,
    this.initialTitle,
    this.initialGenre,
  });

  @override
  ConsumerState<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends ConsumerState<SearchPage> {
  final _q = TextEditingController();
  List<HomeCardItem> _items = [];
  bool _loading = false;
  String? _error;
  // 分页状态
  int _page = 1;
  bool _hasMore = true;
  bool _loadingMore = false;
  String? _loadError;
  final ScrollController _controller = ScrollController();

  String _selectedType = '全部';
  String _selectedSort = '最新更新';
  String _selectedGenre = '全部';
  String _selectedRegion = '全部';
  String _selectedYear = '全部';

  // 1. 筛选条件：5类
  final List<String> _types = const [
    '全部',
    '电视剧',
    '电影',
    '动漫',
    '综艺',
    '演唱会',
    '纪录片',
  ];
  final List<String> _sorts = const ['最新更新', '最新上映', '影片评分'];
  final List<String> _genres = const [
    '全部',
    '剧情',
    '喜剧',
    '动作',
    '爱情',
    '惊悚',
    '犯罪',
    '悬疑',
    '科幻',
    '动画',
    '恐怖',
    '家庭',
    '奇幻',
    '冒险',
    '战争',
    '历史',
    '传记',
    '音乐',
    '歌舞',
    '西部',
    '纪录片',
  ];
  final List<String> _regions = const [
    '全部',
    '中国大陆',
    '中国香港',
    '中国台湾',
    '新加坡',
    '欧美',
    '日本',
    '韩国',
    '泰国',
    '印度',
    '其他',
  ];
  final List<String> _years = const [
    '全部',
    '2025',
    '2024',
    '2023',
    '2022',
    '2021',
    '2020',
    '2019',
    '2018',
    '2017',
    '2016',
    '2010年代',
    '2000年代',
    '90年代',
    '80年代',
    '更早',
  ];

  @override
  void initState() {
    super.initState();
    // 初始化筛选参数
    if (widget.initialKind != null) {
      if (widget.initialKind == 'movie') _selectedType = '电影';
      if (widget.initialKind == 'tv') _selectedType = '电视剧';
    }
    if (widget.initialTitle != null) {
      _q.text = widget.initialTitle!;
    }
    if (widget.initialGenre != null) {
      _selectedGenre = widget.initialGenre!;
    }
    // 初始加载
    _search();
    // 监听滚动以触发懒加载
    _controller.addListener(_onScroll);
  }

  Future<void> _search() async {
    setState(() {
      _loading = true;
      _error = null;
      // 重置分页
      _page = 1;
      _hasMore = true;
      _loadingMore = false;
      _loadError = null;
    });
    try {
      final api = ref.read(apiClientProvider);

      // 映射排序参数
      String? sort;
      if (_selectedSort == '最新更新') sort = 'updated';
      if (_selectedSort == '最新上映') sort = 'released';
      if (_selectedSort == '影片评分') sort = 'rating';

      // 映射类型参数 (movie|tv 或其他)
      String? kind = _selectedType;
      if (kind == '电影') kind = 'movie';
      if (kind == '电视剧') kind = 'tv';

      final res = await api.searchMedia(
        _q.text,
        page: _page,
        pageSize: 30,
        kind: kind,
        genres: [_selectedGenre],
        year: _selectedYear,
        region: _selectedRegion,
        sort: sort,
      );
      setState(() {
        _items = List.of(res.items);
        _hasMore = _items.length < res.total;
        _page += 1;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  void _onScroll() {
    if (_loading || _loadingMore || !_hasMore) return;
    if (!_controller.hasClients) return;
    final position = _controller.position;
    if (position.pixels >= position.maxScrollExtent - 200) {
      _loadMore();
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || !_hasMore) return;
    setState(() {
      _loadingMore = true;
      _loadError = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      // 映射排序与类型
      String? sort;
      if (_selectedSort == '最新更新') sort = 'updated';
      if (_selectedSort == '最新上映') sort = 'released';
      if (_selectedSort == '影片评分') sort = 'rating';
      String? kind = _selectedType;
      if (kind == '电影') kind = 'movie';
      if (kind == '电视剧') kind = 'tv';
      final res = await api.searchMedia(
        _q.text,
        page: _page,
        pageSize: 30,
        kind: kind,
        genres: [_selectedGenre],
        year: _selectedYear,
        region: _selectedRegion,
        sort: sort,
      );
      setState(() {
        _items.addAll(res.items);
        _hasMore = _items.length < res.total;
        _page += 1;
      });
    } catch (e) {
      setState(() {
        _loadError = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _loadingMore = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Padding(
          padding: const EdgeInsets.only(right: 16),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _q,
                  decoration: InputDecoration(
                    hintText: '输入影片名称搜索',
                    prefixIcon: const Icon(Icons.search),
                    contentPadding: const EdgeInsets.symmetric(
                      vertical: 0,
                      horizontal: 16,
                    ),
                    filled: true,
                    fillColor: Theme.of(
                      context,
                    ).colorScheme.surfaceContainerHighest,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: BorderSide.none,
                    ),
                  ),
                  onSubmitted: (_) => _search(),
                ),
              ),
              const SizedBox(width: 8),
              TextButton(onPressed: _search, child: const Text('搜索')),
            ],
          ),
        ),
        // backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Column(
        children: [
          // 1. 筛选条件区
          Container(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: Column(
              children: [
                _buildFilterRow(_types, _selectedType, (val) {
                  setState(() => _selectedType = val);
                  _search();
                }),
                _buildFilterRow(_sorts, _selectedSort, (val) {
                  setState(() => _selectedSort = val);
                  _search();
                }),
                _buildFilterRow(_genres, _selectedGenre, (val) {
                  setState(() => _selectedGenre = val);
                  _search();
                }, label: '类型'),
                _buildFilterRow(_regions, _selectedRegion, (val) {
                  setState(() => _selectedRegion = val);
                  _search();
                }, label: '地区'),
                _buildFilterRow(_years, _selectedYear, (val) {
                  setState(() => _selectedYear = val);
                  _search();
                }, label: '年份'),
              ],
            ),
          ),
          const Divider(height: 1),

          // 2. 内容列表区
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(child: Text('加载失败: $_error'))
                    : _items.isEmpty
                        ? const Center(child: Text('暂无相关内容'))
                        : GridView.builder(
                            controller: _controller,
                            padding: const EdgeInsets.all(12),
                            gridDelegate:
                                const SliverGridDelegateWithMaxCrossAxisExtent(
                              maxCrossAxisExtent: 150,
                              mainAxisExtent: 220,
                              mainAxisSpacing: 12,
                              crossAxisSpacing: 12,
                            ),
                            itemCount: _items.length + 1,
                            itemBuilder: (ctx, i) {
                              if (i == _items.length) {
                                return _buildFooter(ctx);
                              } else {
                                return MediaCard(
                                  item: _items[i],
                                  width: double.infinity,
                                  height: 220,
                                );
                              }
                            },
                          ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterRow(
    List<String> options,
    String selected,
    ValueChanged<String> onSelected, {
    String? label,
  }) {
    return SizedBox(
      height: 44,
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        scrollDirection: Axis.horizontal,
        itemCount: options.length + (label != null ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(width: 4),
        itemBuilder: (context, index) {
          // 如果有 label，第一个 item 显示 label 文本（如“类型”、“地区”）
          if (label != null && index == 0) {
            return Container(
              alignment: Alignment.center,
              padding: const EdgeInsets.only(right: 8),
              child: Text(
                label,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
              ),
            );
          }

          final optionIndex = label != null ? index - 1 : index;
          final option = options[optionIndex];
          final isSelected = option == selected;

          return Center(
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => onSelected(option),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: isSelected
                      ? Theme.of(context).colorScheme.primaryContainer
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(
                  option,
                  style: TextStyle(
                    color: isSelected
                        ? Theme.of(context).colorScheme.onPrimaryContainer
                        : Theme.of(context).colorScheme.onSurfaceVariant,
                    fontWeight:
                        isSelected ? FontWeight.bold : FontWeight.normal,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildFooter(BuildContext context) {
    if (_loadingMore) {
      return Center(
        child: Text(
          '加载更多...',
          style: Theme.of(
            context,
          ).textTheme.bodyMedium?.copyWith(color: Colors.white70),
        ),
      );
    }
    if (_loadError != null) {
      return Center(
        child: TextButton(onPressed: _loadMore, child: const Text('点击重试')),
      );
    }
    if (!_hasMore) {
      return Center(
        child: Text(
          '没有更多内容了',
          style: Theme.of(
            context,
          ).textTheme.bodyMedium?.copyWith(color: Colors.white54),
        ),
      );
    }
    return const SizedBox.shrink();
  }
}
