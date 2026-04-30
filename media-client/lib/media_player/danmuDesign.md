# 弹幕功能模块 — 详细开发方案

## 一、模块目录结构

```
media-client/lib/media_player/
├── danmu/
│   ├── models/
│   │   └── danmu_models.dart              # 弹幕数据模型
│   ├── engine/
│   │   ├── danmu_item.dart                # 弹幕实体（含布局坐标）
│   │   ├── danmu_track_manager.dart       # 轨道调度器
│   │   ├── danmu_renderer.dart            # CustomPainter 渲染器
│   │   └── danmu_controller.dart          # 弹幕引擎控制器（生命周期管理）
│   ├── provider/
│   │   └── danmu_provider.dart            # Riverpod 状态管理
│   ├── api/
│   │   └── danmu_api.dart                 # API 扩展方法（ApiClient mixin）
│   └── ui/
│       ├── danmu_overlay.dart             # 弹幕渲染层（嵌入 Stack）
│       ├── danmu_panel.dart               # 右下角弹幕控制面板
│       └── danmu_search_page.dart         # 手动搜索页面
```

---

## 二、数据模型层 (danmu_models.dart)

```dart
/// 单条弹幕
class DanmuComment {
  final int cid;
  final double time;      // 秒，从 p 字段解析
  final int mode;         // 1=滚动 4=底部 5=顶部
  final int color;        // 十进制颜色
  final String source;    // [qiyi] 等
  final String content;

  DanmuComment({required this.cid, required this.time, required this.mode,
    required this.color, required this.source, required this.content});

  factory DanmuComment.fromJson(Map<String, dynamic> json) {
    final p = (json['p'] as String? ?? '').split(',');
    return DanmuComment(
      time: double.tryParse(p.isNotEmpty ? p[0] : '0') ?? 0,
      mode: p.length > 1 ? (int.tryParse(p[1]) ?? 1) : 1,
      color: p.length > 2 ? (int.tryParse(p[2]) ?? 16777215) : 16777215,
      source: p.length > 3 ? p[3] : '',
      content: json['m'] as String? ?? '',
      cid: json['cid'] as int? ?? 0,
    );
  }
}

/// 分片信息
class DanmuSegment {
  final String type;
  final double segmentStart;
  final double segmentEnd;
  final String url;

  DanmuSegment({required this.type, required this.segmentStart,
    required this.segmentEnd, required this.url});

  factory DanmuSegment.fromJson(Map<String, dynamic> json) => DanmuSegment(
    type: json['type'] as String? ?? '',
    segmentStart: (json['segment_start'] as num?)?.toDouble() ?? 0,
    segmentEnd: (json['segment_end'] as num?)?.toDouble() ?? 0,
    url: json['url'] as String? ?? '',
  );
}

/// 弹幕数据响应
class DanmuData {
  final int episodeId;
  final int count;
  final List<DanmuComment> comments;
  final double videoDuration;
  final String loadMode;
  final List<DanmuSegment> segmentList;

  DanmuData({required this.episodeId, required this.count,
    required this.comments, required this.videoDuration,
    required this.loadMode, required this.segmentList});

  factory DanmuData.fromJson(Map<String, dynamic> json) => DanmuData(
    episodeId: json['episode_id'] as int? ?? 0,
    count: json['count'] as int? ?? 0,
    comments: (json['comments'] as List?)
        ?.map((e) => DanmuComment.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
    videoDuration: (json['video_duration'] as num?)?.toDouble() ?? 0,
    loadMode: json['load_mode'] as String? ?? 'full',
    segmentList: (json['segment_list'] as List?)
        ?.map((e) => DanmuSegment.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
  );
}

/// 匹配源
class DanmuSource {
  final int episodeId;
  final int animeId;
  final String animeTitle;
  final String episodeTitle;
  final String type;
  final String typeDescription;
  final int shift;
  final String imageUrl;

  DanmuSource({required this.episodeId, required this.animeId,
    required this.animeTitle, required this.episodeTitle,
    required this.type, required this.typeDescription,
    required this.shift, required this.imageUrl});

  factory DanmuSource.fromJson(Map<String, dynamic> json) => DanmuSource(
    episodeId: json['episodeId'] as int? ?? 0,
    animeId: json['animeId'] as int? ?? 0,
    animeTitle: json['animeTitle'] as String? ?? '',
    episodeTitle: json['episodeTitle'] as String? ?? '',
    type: json['type'] as String? ?? '',
    typeDescription: json['typeDescription'] as String? ?? '',
    shift: json['shift'] as int? ?? 0,
    imageUrl: json['imageUrl'] as String? ?? '',
  );
}

/// 自动匹配结果
class DanmuMatchResult {
  final bool isMatched;
  final double confidence;
  final List<DanmuSource> sources;
  final DanmuSource? bestMatch;
  final DanmuBinding? binding;
  final DanmuData? danmuData;

  DanmuMatchResult({required this.isMatched, required this.confidence,
    required this.sources, this.bestMatch, this.binding, this.danmuData});

  factory DanmuMatchResult.fromJson(Map<String, dynamic> json) =>
    DanmuMatchResult(
      isMatched: json['is_matched'] as bool? ?? false,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      sources: (json['sources'] as List?)
          ?.map((e) => DanmuSource.fromJson(e as Map<String, dynamic>))
          .toList() ?? const [],
      bestMatch: json['best_match'] != null
          ? DanmuSource.fromJson(json['best_match'] as Map<String, dynamic>)
          : null,
      binding: json['binding'] != null
          ? DanmuBinding.fromJson(json['binding'] as Map<String, dynamic>)
          : null,
      danmuData: json['danmu_data'] != null
          ? DanmuData.fromJson(json['danmu_data'] as Map<String, dynamic>)
          : null,
    );
}

/// 搜索结果项
class DanmuSearchItem {
  final int animeId;
  final String animeTitle;
  final String type;
  final String typeDescription;
  final String imageUrl;
  final int episodeCount;
  final double rating;

  DanmuSearchItem({required this.animeId, required this.animeTitle,
    required this.type, required this.typeDescription,
    required this.imageUrl, required this.episodeCount,
    required this.rating});

  factory DanmuSearchItem.fromJson(Map<String, dynamic> json) =>
    DanmuSearchItem(
      animeId: json['animeId'] as int? ?? 0,
      animeTitle: json['animeTitle'] as String? ?? '',
      type: json['type'] as String? ?? '',
      typeDescription: json['typeDescription'] as String? ?? '',
      imageUrl: json['imageUrl'] as String? ?? '',
      episodeCount: json['episodeCount'] as int? ?? 0,
      rating: (json['rating'] as num?)?.toDouble() ?? 0,
    );
}

/// Bangumi 详情
class DanmuBangumi {
  final int animeId;
  final String animeTitle;
  final String type;
  final String imageUrl;
  final List<DanmuSeason> seasons;
  final List<DanmuEpisode> episodes;

  DanmuBangumi({required this.animeId, required this.animeTitle,
    required this.type, required this.imageUrl,
    required this.seasons, required this.episodes});

  factory DanmuBangumi.fromJson(Map<String, dynamic> json) => DanmuBangumi(
    animeId: json['animeId'] as int? ?? 0,
    animeTitle: json['animeTitle'] as String? ?? '',
    type: json['type'] as String? ?? '',
    imageUrl: json['imageUrl'] as String? ?? '',
    seasons: (json['seasons'] as List?)
        ?.map((e) => DanmuSeason.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
    episodes: (json['episodes'] as List?)
        ?.map((e) => DanmuEpisode.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
  );
}

class DanmuSeason {
  final String id;
  final String name;
  final int episodeCount;

  DanmuSeason({required this.id, required this.name, required this.episodeCount});

  factory DanmuSeason.fromJson(Map<String, dynamic> json) => DanmuSeason(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    episodeCount: json['episodeCount'] as int? ?? 0,
  );
}

class DanmuEpisode {
  final String seasonId;
  final int episodeId;
  final String episodeTitle;
  final String episodeNumber;

  DanmuEpisode({required this.seasonId, required this.episodeId,
    required this.episodeTitle, required this.episodeNumber});

  factory DanmuEpisode.fromJson(Map<String, dynamic> json) => DanmuEpisode(
    seasonId: json['seasonId'] as String? ?? '',
    episodeId: json['episodeId'] as int? ?? 0,
    episodeTitle: json['episodeTitle'] as String? ?? '',
    episodeNumber: json['episodeNumber'] as String? ?? '',
  );
}

/// 绑定信息
class DanmuBinding {
  final int id;
  final String fileId;
  final int episodeId;
  final int animeId;
  final String animeTitle;
  final String episodeTitle;
  final double offset;
  final bool isManual;

  DanmuBinding({required this.id, required this.fileId, required this.episodeId,
    required this.animeId, required this.animeTitle, required this.episodeTitle,
    required this.offset, required this.isManual});

  factory DanmuBinding.fromJson(Map<String, dynamic> json) => DanmuBinding(
    id: json['id'] as int? ?? 0,
    fileId: json['file_id'] as String? ?? '',
    episodeId: (json['episode_id'] as num?)?.toInt() ?? 0,
    animeId: (json['anime_id'] as num?)?.toInt() ?? 0,
    animeTitle: json['anime_title'] as String? ?? '',
    episodeTitle: json['episode_title'] as String? ?? '',
    offset: (json['offset'] as num?)?.toDouble() ?? 0,
    isManual: json['is_manual'] as bool? ?? false,
  );
}
```

---

## 三、弹幕渲染引擎（核心，高性能设计）

这是整个模块最关键的部分。核心原则：**零 Widget 开销、单 Canvas 绘制、主线程零布局计算**。

### 3.1 弹幕实体 (danmu_item.dart)

```dart
class DanmuItem {
  final DanmuComment comment;
  // 布局结果（由 TrackManager 计算后填入）
  double x = 0;
  double y = 0;
  double width = 0;
  double height = 0;
  double speed = 0;        // 像素/秒
  double opacity = 1.0;
  bool alive = true;

  DanmuItem(this.comment);

  /// 当前帧的屏幕 x 坐标
  double screenX(double elapsed) => x - speed * elapsed;

  /// 是否还在可视区域内
  bool isVisible(double elapsed, double viewWidth) {
    final sx = screenX(elapsed);
    return sx + width > 0 && sx < viewWidth;
  }
}
```

### 3.2 轨道调度器 (danmu_track_manager.dart)

```dart
/// 轨道管理器：将弹幕分配到不重叠的水平轨道
class DanmuTrackManager {
  final double viewWidth;
  final double viewHeight;
  final double itemHeight;  // 单行弹幕高度
  final int maxTracks;

  // 每条轨道记录：最后一条弹幕完全离开屏幕的时间
  final List<double> _trackFreeAt = [];
  // 每条轨道的 y 坐标
  final List<double> _trackY = [];

  DanmuTrackManager({
    required this.viewWidth,
    required this.viewHeight,
    this.itemHeight = 28,
  }) : maxTracks = (viewHeight / itemHeight).floor() {
    for (int i = 0; i < maxTracks; i++) {
      _trackFreeAt.add(0);
      _trackY.add(i * itemHeight);
    }
  }

  /// 为弹幕分配轨道，返回 y 坐标，-1 表示无可用轨道（丢弃）
  double allocate(DanmuItem item, double currentTime, double speed) {
    final duration = viewWidth / speed; // 弹幕穿越屏幕的时间

    for (int i = 0; i < maxTracks; i++) {
      if (currentTime >= _trackFreeAt[i]) {
        _trackFreeAt[i] = currentTime + duration;
        item.y = _trackY[i];
        item.speed = speed;
        return _trackY[i];
      }
    }
    return -1; // 所有轨道满载，丢弃
  }

  void reset() {
    for (int i = 0; i < maxTracks; i++) {
      _trackFreeAt[i] = 0;
    }
  }
}
```

### 3.3 渲染器 (danmu_renderer.dart)

```dart
class DanmuRenderer extends CustomPainter {
  final List<DanmuItem> items;
  final double elapsed;       // 当前播放时间（秒）
  final double viewWidth;
  final double viewHeight;

  // 文本画笔缓存（避免每帧重建）
  static final Map<int, TextPainter> _painterCache = {};
  static final Map<int, ui.Paragraph> _paragraphCache = {};

  DanmuRenderer({
    required this.items,
    required this.elapsed,
    required this.viewWidth,
    required this.viewHeight,
  });

  @override
  void paint(Canvas canvas, Size size) {
    for (final item in items) {
      if (!item.alive) continue;
      final sx = item.screenX(elapsed);
      if (!item.isVisible(elapsed, viewWidth)) continue;

      final color = Color(item.comment.color);

      // 使用 Paragraph API（比 TextPainter 更轻量）
      final paragraph = _getParagraph(item, color);
      canvas.drawParagraph(paragraph, Offset(sx, item.y));
    }
  }

  ui.Paragraph _getParagraph(DanmuItem item, Color color) {
    // 用 cid 作为缓存 key（同一条弹幕只构建一次 Paragraph）
    final cached = _paragraphCache[item.comment.cid];
    if (cached != null) return cached;

    final builder = ui.ParagraphBuilder(
      ui.ParagraphStyle(fontSize: 16, textAlign: TextAlign.left),
    )
      ..pushStyle(ui.TextStyle(
        color: Colors.white,
        shadows: [
          Shadow(blurRadius: 2, color: Colors.black54),
          Shadow(blurRadius: 4, color: Colors.black38),
        ],
      ))
      ..addText(item.comment.content);

    final paragraph = builder.build()
      ..layout(ui.ParagraphConstraints(width: double.infinity));

    item.width = paragraph.longestLine;
    item.height = paragraph.height;
    _paragraphCache[item.comment.cid] = paragraph;
    return paragraph;
  }

  @override
  bool shouldRepaint(covariant DanmuRenderer old) => true;

  static void clearCache() {
    _painterCache.clear();
    _paragraphCache.clear();
  }
}
```

### 3.4 弹幕控制器 (danmu_controller.dart)

```dart
class DanmuController extends ChangeNotifier {
  DanmuTrackManager? _trackManager;
  final List<DanmuItem> _activeItems = [];
  final List<DanmuComment> _allComments = [];
  bool _enabled = true;
  double _opacity = 1.0;
  double _fontSize = 16;
  double _area = 1.0;       // 弹幕区域（0.5=上半屏, 1.0=全屏）
  double _speed = 140;       // 像素/秒
  int _maxVisible = 100;     // 同屏最大弹幕数

  // 分片管理
  List<DanmuSegment> _segments = [];
  int _currentSegmentIndex = 0;
  bool _isLoadingSegment = false;

  // 时间 → 弹幕索引的排序映射（二分查找用）
  List<DanmuComment> _sortedByTime = [];

  // 帧调度
  Timer? _frameTimer;
  double _lastPosition = 0;
  bool _playing = false;

  // ---- 公开 API ----

  bool get enabled => _enabled;
  double get opacity => _opacity;
  int get activeCount => _activeItems.length;
  int get totalCount => _allComments.length;

  void init({required double viewWidth, required double viewHeight}) {
    _trackManager = DanmuTrackManager(
      viewWidth: viewWidth,
      viewHeight: viewHeight * _area,
      itemHeight: _fontSize + 12,
    );
  }

  /// 加载初始弹幕数据
  void loadDanmuData(DanmuData data) {
    _allComments.clear();
    _allComments.addAll(data.comments);
    _segments = data.segmentList;
    _currentSegmentIndex = 0;
    _sortedByTime = List.of(_allComments)
      ..sort((a, b) => a.time.compareTo(b.time));
    notifyListeners();
  }

  /// 追加分片弹幕
  void appendComments(List<DanmuComment> comments) {
    _allComments.addAll(comments);
    _sortedByTime = List.of(_allComments)
      ..sort((a, b) => a.time.compareTo(b.time));
  }

  /// 切换弹幕开关
  void toggle() {
    _enabled = !_enabled;
    if (!_enabled) _activeItems.clear();
    notifyListeners();
  }

  /// 设置透明度
  void setOpacity(double v) {
    _opacity = v.clamp(0.0, 1.0);
    notifyListeners();
  }

  /// 播放器位置更新回调（每帧调用）
  void onPositionUpdate(double positionSeconds) {
    if (!_enabled || _trackManager == null) return;

    _lastPosition = positionSeconds;

    // 1. 检查是否需要加载下一分片
    _maybeLoadNextSegment(positionSeconds);

    // 2. 清除已过期的弹幕
    _activeItems.removeWhere((item) =>
        !item.isVisible(positionSeconds, _trackManager!.viewWidth));

    // 3. 用二分查找找到当前时间窗口内应发射的弹幕
    _fireNewDanmu(positionSeconds);

    notifyListeners();
  }

  void _fireNewDanmu(double position) {
    if (_activeItems.length >= _maxVisible) return;

    // 查找 [position - 0.1, position + 0.1] 范围内的弹幕
    final windowStart = position - 0.1;
    final windowEnd = position + 0.1;

    int lo = 0, hi = _sortedByTime.length;
    while (lo < hi) {
      final mid = (lo + hi) >> 1;
      if (_sortedByTime[mid].time < windowStart) lo = mid + 1;
      else hi = mid;
    }

    for (int i = lo; i < _sortedByTime.length; i++) {
      final comment = _sortedByTime[i];
      if (comment.time > windowEnd) break;

      // 避免重复发射
      if (_activeItems.any((a) => a.comment.cid == comment.cid)) continue;

      final item = DanmuItem(comment);
      final allocated = _trackManager!.allocate(item, position, _speed);
      if (allocated >= 0) {
        _activeItems.add(item);
      }
      if (_activeItems.length >= _maxVisible) break;
    }
  }

  void _maybeLoadNextSegment(double position) {
    if (_isLoadingSegment) return;
    if (_currentSegmentIndex >= _segments.length - 1) return;

    final nextSeg = _segments[_currentSegmentIndex + 1];
    if (position >= nextSeg.segmentStart - 30) {  // 提前30秒预加载
      _isLoadingSegment = true;
      _currentSegmentIndex++;
      // 通过回调通知 Provider 发起网络请求
      _onNeedLoadSegment?.call(nextSeg);
    }
  }

  void onSegmentLoaded(List<DanmuComment> comments) {
    appendComments(comments);
    _isLoadingSegment = false;
  }

  /// 播放/暂停状态同步
  void setPlaying(bool playing) => _playing = playing;

  // 分片加载回调（由 Provider 注入）
  void Function(DanmuSegment segment)? _onNeedLoadSegment;

  void setOnNeedLoadSegment(void Function(DanmuSegment) cb) {
    _onNeedLoadSegment = cb;
  }

  void dispose_engine() {
    _frameTimer?.cancel();
    _activeItems.clear();
    DanmuRenderer.clearCache();
  }
}
```

### 3.5 性能设计要点

| 策略 | 说明 |
|---|---|
| **单 CustomPainter** | 所有弹幕在一个 Canvas 上绘制，零 Widget 树开销 |
| **Paragraph 缓存** | 同一条弹幕的 Paragraph 只构建一次，用 cid 做 key |
| **轨道预分配** | 8-12 条水平轨道，O(1) 分配，满载直接丢弃 |
| **二分查找发射** | _sortedByTime 有序数组 + 二分，O(log n) 定位 |
| **视口剔除** | isVisible() 检查，屏幕外弹幕不参与绘制 |
| **同屏上限** | maxVisible=100，超限丢弃，保护 GPU |
| **预加载** | 提前 30 秒请求下一分片，避免播放中断 |
| **独立帧率** | 弹幕用 Ticker 或 16ms Timer 独立刷新，不依赖播放器帧回调 |

---

## 四、状态管理 (danmu_provider.dart)

遵循项目现有的 StateNotifierProvider 模式：

```dart
// ---- State ----

class DanmuState {
  final bool enabled;
  final bool loading;
  final String? error;

  // 匹配结果
  final DanmuMatchResult? matchResult;
  final List<DanmuSource> sources;
  final DanmuSource? selectedSource;

  // 弹幕数据
  final DanmuData? danmuData;
  final int loadedSegmentIndex;
  final int totalDanmuCount;

  // 搜索
  final List<DanmuSearchItem> searchResults;
  final bool searchLoading;

  // 绑定
  final DanmuBinding? binding;

  const DanmuState({
    this.enabled = false,
    this.loading = false,
    this.error,
    this.matchResult,
    this.sources = const [],
    this.selectedSource,
    this.danmuData,
    this.loadedSegmentIndex = 0,
    this.totalDanmuCount = 0,
    this.searchResults = const [],
    this.searchLoading = false,
    this.binding,
  });

  DanmuState copyWith({
    bool? enabled,
    bool? loading,
    String? error,
    DanmuMatchResult? matchResult,
    List<DanmuSource>? sources,
    DanmuSource? selectedSource,
    DanmuData? danmuData,
    int? loadedSegmentIndex,
    int? totalDanmuCount,
    List<DanmuSearchItem>? searchResults,
    bool? searchLoading,
    DanmuBinding? binding,
  }) => DanmuState(
    enabled: enabled ?? this.enabled,
    loading: loading ?? this.loading,
    error: error,
    matchResult: matchResult ?? this.matchResult,
    sources: sources ?? this.sources,
    selectedSource: selectedSource ?? this.selectedSource,
    danmuData: danmuData ?? this.danmuData,
    loadedSegmentIndex: loadedSegmentIndex ?? this.loadedSegmentIndex,
    totalDanmuCount: totalDanmuCount ?? this.totalDanmuCount,
    searchResults: searchResults ?? this.searchResults,
    searchLoading: searchLoading ?? this.searchLoading,
    binding: binding ?? this.binding,
  );
}

// ---- Notifier ----

class DanmuNotifier extends StateNotifier<DanmuState> {
  final ApiClient _api;
  final String _fileId;
  DanmuController? _engine;

  DanmuNotifier(this._api, this._fileId) : super(const DanmuState());

  DanmuController? get engine => _engine;

  /// 开启弹幕：触发自动匹配
  Future<void> enable() async {
    state = state.copyWith(enabled: true, loading: true);
    try {
      final result = await _api.danmuAutoMatch(_fileId);
      final engine = DanmuController();
      if (result.danmuData != null) {
        engine.loadDanmuData(result.danmuData!);
        engine.setOnNeedLoadSegment(_loadSegment);
      }
      _engine = engine;
      state = state.copyWith(
        loading: false,
        matchResult: result,
        sources: result.sources,
        selectedSource: result.bestMatch,
        danmuData: result.danmuData,
        totalDanmuCount: result.danmuData?.count ?? 0,
        binding: result.binding,
      );
    } catch (e) {
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 切换弹幕开关
  void toggle() {
    if (state.enabled) {
      _engine?.dispose_engine();
      _engine = null;
      state = state.copyWith(enabled: false);
    } else {
      enable();
    }
  }

  /// 选择不同的源
  Future<void> selectSource(DanmuSource source) async {
    state = state.copyWith(loading: true, selectedSource: source);
    try {
      final data = await _api.getDanmuByEpisode(source.episodeId);
      _engine?.loadDanmuData(data);
      state = state.copyWith(
        loading: false,
        danmuData: data,
        totalDanmuCount: data.count,
      );
    } catch (e) {
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 搜索弹幕
  Future<void> search(String keyword) async {
    state = state.copyWith(searchLoading: true);
    try {
      final results = await _api.danmuSearch(keyword);
      state = state.copyWith(searchResults: results, searchLoading: false);
    } catch (e) {
      state = state.copyWith(searchLoading: false, error: e.toString());
    }
  }

  /// 手动选择 bangumi episode
  Future<void> selectEpisode(int episodeId) async {
    state = state.copyWith(loading: true);
    try {
      final data = await _api.getDanmuByEpisode(episodeId);
      _engine?.loadDanmuData(data);
      state = state.copyWith(
        loading: false,
        danmuData: data,
        totalDanmuCount: data.count,
      );
    } catch (e) {
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 分片加载回调
  Future<void> _loadSegment(DanmuSegment segment) async {
    try {
      final result = await _api.danmuNextSegment(segment.url);
      _engine?.onSegmentLoaded(result.comments);
      state = state.copyWith(
        loadedSegmentIndex: state.loadedSegmentIndex + 1);
    } catch (_) {
      // _isLoadingSegment 由 engine 内部管理
    }
  }

  @override
  void dispose() {
    _engine?.dispose_engine();
    super.dispose();
  }
}

// ---- Providers ----

final danmuProvider = StateNotifierProvider.family
    .autoDispose<DanmuNotifier, DanmuState, String>((ref, fileId) {
  final api = ref.read(apiClientProvider);
  return DanmuNotifier(api, fileId);
});
```

---

## 五、API 扩展 (danmu_api.dart)

在 ApiClient 上添加弹幕相关方法（使用 extension）：

```dart
extension DanmuApi on ApiClient {
  /// 自动匹配弹幕
  Future<DanmuMatchResult> danmuAutoMatch(String fileId) async {
    final res = await _client.post(
      _u('/api/danmu/match/auto'),
      headers: _headers({'Content-Type': 'application/json'}),
      body: jsonEncode({'file_id': fileId}),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('弹幕匹配失败');
    }
    return DanmuMatchResult.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 搜索弹幕
  Future<List<DanmuSearchItem>> danmuSearch(String keyword) async {
    final res = await _client.get(
      _u('/api/danmu/search?keyword=${Uri.encodeComponent(keyword)}'),
      headers: _headers(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('搜索失败');
    }
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    return (data['items'] as List?)
        ?.map((e) => DanmuSearchItem.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [];
  }

  /// 获取 bangumi 详情（含 episodes）
  Future<DanmuBangumi> getDanmuBangumi(int animeId) async {
    final res = await _client.get(
      _u('/api/danmu/bangumi/$animeId'),
      headers: _headers(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('获取番剧信息失败');
    }
    return DanmuBangumi.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 按 episodeId 获取弹幕
  Future<DanmuData> getDanmuByEpisode(int episodeId) async {
    final res = await _client.get(
      _u('/api/danmu/$episodeId'),
      headers: _headers(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('获取弹幕失败');
    }
    return DanmuData.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 加载下一分片
  Future<DanmuNextSegmentResult> danmuNextSegment(String url) async {
    final res = await _client.get(
      _u('/api/danmu/next-segment?url=${Uri.encodeComponent(url)}'),
      headers: _headers(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('加载分片失败');
    }
    return DanmuNextSegmentResult.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 保存手动绑定
  Future<DanmuBinding> saveDanmuBinding(String fileId, int episodeId) async {
    final res = await _client.post(
      _u('/api/danmu/match/bind/$fileId'),
      headers: _headers({'Content-Type': 'application/json'}),
      body: jsonEncode({'episode_id': episodeId}),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('保存绑定失败');
    }
    return DanmuBinding.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 删除绑定
  Future<void> deleteDanmuBinding(String fileId) async {
    final res = await _client.delete(
      _u('/api/danmu/match/bind/$fileId'),
      headers: _headers(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('删除绑定失败');
    }
  }

  /// 调整偏移量
  Future<DanmuBinding> updateDanmuOffset(
      String fileId, double offset) async {
    final res = await _client.put(
      _u('/api/danmu/match/bind/$fileId/offset'),
      headers: _headers({'Content-Type': 'application/json'}),
      body: jsonEncode({'offset': offset}),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('调整偏移失败');
    }
    return DanmuBinding.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }
}
```

---

## 六、UI 层设计

### 6.1 弹幕渲染层 (danmu_overlay.dart)

嵌入 CommonPlayerLayout 的 Stack 中，位于 Controls 层之下：

```dart
class DanmuOverlay extends ConsumerStatefulWidget {
  final String fileId;

  const DanmuOverlay({required this.fileId});

  @override
  ConsumerState<DanmuOverlay> createState() => _DanmuOverlayState();
}

class _DanmuOverlayState extends ConsumerState<DanmuOverlay>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  double _elapsed = 0;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((duration) {
      setState(() => _elapsed = duration.inMilliseconds / 1000.0);
    });
    _ticker.start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final danmuState = ref.watch(danmuProvider(widget.fileId));
    final engine = danmuState.enabled
        ? ref.read(danmuProvider(widget.fileId).notifier).engine
        : null;
    if (engine == null || !danmuState.enabled) return const SizedBox.shrink();

    // 订阅播放器位置更新
    final position = ref.watch(playbackProvider).position;
    engine.onPositionUpdate(position);

    return IgnorePointer(
      child: Opacity(
        opacity: engine.opacity,
        child: LayoutBuilder(
          builder: (context, constraints) {
            engine.init(
              viewWidth: constraints.maxWidth,
              viewHeight: constraints.maxHeight,
            );
            return CustomPaint(
              size: Size(constraints.maxWidth, constraints.maxHeight),
              painter: DanmuRenderer(
                items: engine._activeItems,
                elapsed: _elapsed,
                viewWidth: constraints.maxWidth,
                viewHeight: constraints.maxHeight,
              ),
            );
          },
        ),
      ),
    );
  }
}
```

### 6.2 弹幕控制面板 (danmu_panel.dart)

参照现有 `_openPanel` 模式，适配竖屏 BottomSheet / 横屏右侧 Drawer：

```
┌─────────────────────────────┐
│  弹幕开关  [====●====]       │  ← 开关 + 透明度滑块
│─────────────────────────────│
│  匹配来源                    │
│  ┌─────────────────────────┐│
│  │ 🟡 生万物(2025) 第2集    ││  ← best_match 黄色高亮
│  │    【qiyi】 电视剧        ││
│  ├─────────────────────────┤│
│  │ ⚪ 生万物(2025) 第3集    ││  ← 其他 source 白色
│  │    【bilibili】 电视剧    ││
│  └─────────────────────────┘│
│                              │
│  已加载 1482 条弹幕          │  ← 状态信息
│                              │
│  🔍 手动搜索                 │  ← 跳转搜索页
└─────────────────────────────┘
```

```dart
class DanmuPanel extends ConsumerWidget {
  final String fileId;

  const DanmuPanel({required this.fileId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(danmuProvider(fileId));
    final notifier = ref.read(danmuProvider(fileId).notifier);

    return Container(
      color: const Color(0xFF1E1E1E),
      child: Column(
        children: [
          // ---- 开关 + 透明度 ----
          _buildToggleRow(state, notifier),

          const Divider(color: Colors.white12),

          // ---- 匹配来源列表 ----
          if (state.loading)
            const Center(child: CircularProgressIndicator())
          else if (state.sources.isNotEmpty)
            Expanded(child: _buildSourceList(state, notifier))
          else
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('未找到匹配弹幕',
                  style: TextStyle(color: Colors.white54)),
            ),

          // ---- 状态信息 ----
          if (state.danmuData != null)
            Padding(
              padding: const EdgeInsets.symmetric(
                  horizontal: 16, vertical: 8),
              child: Text(
                '已加载 ${state.totalDanmuCount} 条弹幕',
                style: const TextStyle(
                    color: Colors.white54, fontSize: 12),
              ),
            ),

          // ---- 手动搜索按钮 ----
          ListTile(
            leading: const Icon(Icons.search, color: Colors.white70),
            title: const Text('手动搜索',
                style: TextStyle(color: Colors.white70)),
            onTap: () => _openSearchPage(context),
          ),
        ],
      ),
    );
  }

  Widget _buildToggleRow(DanmuState state, DanmuNotifier notifier) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          const Text('弹幕',
              style: TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          Switch(
            value: state.enabled,
            activeColor: const Color(0xFFFFE796),
            onChanged: (_) => notifier.toggle(),
          ),
        ],
      ),
    );
  }

  Widget _buildSourceList(DanmuState state, DanmuNotifier notifier) {
    return ListView.builder(
      itemCount: state.sources.length,
      itemBuilder: (context, index) {
        final source = state.sources[index];
        final isSelected =
            source.episodeId == state.selectedSource?.episodeId;
        return GestureDetector(
          onTap: () => notifier.selectSource(source),
          child: Container(
            margin:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF666666).withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(12),
              border: isSelected
                  ? Border.all(
                      color: const Color(0xFFFFE796), width: 1.5)
                  : null,
            ),
            child: Row(
              children: [
                if (source.imageUrl.isNotEmpty)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: Image.network(source.imageUrl,
                        width: 48, height: 36, fit: BoxFit.cover),
                  ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(source.animeTitle,
                        style: TextStyle(
                          color: isSelected
                              ? const Color(0xFFFFE796)
                              : Colors.white,
                          fontSize: 14,
                          fontWeight:
                              isSelected ? FontWeight.bold : null,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${source.episodeTitle}  ${source.typeDescription}',
                        style: const TextStyle(
                            color: Colors.white54, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _openSearchPage(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => DanmuSearchPage(fileId: fileId),
    ));
  }
}
```

### 6.3 手动搜索页面 (danmu_search_page.dart)

搜索列表页：

```
┌──────────────────────────────────────┐
│  ←  弹幕搜索                         │
│  ┌──────────────────────────┐ [搜索] │
│  │ 输入影视名称...           │        │
│  └──────────────────────────┘        │
│                                      │
│  搜索结果:                           │
│  ┌──────────────────────────────────┐│
│  │ [图] 万物生灵 2(2025)            ││
│  │      电视剧 · 7集               ││
│  ├──────────────────────────────────┤│
│  │ [图] 生万物(2025)               ││
│  │      电视剧 · 35集              ││
│  └──────────────────────────────────┘│
│                                      │
│  (点击某个 item → 跳转集信息面板)     │
└──────────────────────────────────────┘
```

集信息面板：

```
┌──────────────────────────────────────┐
│  ←  生万物(2025)  电视剧             │
│  ┌──────────────────────────────────┐│
│  │ Season 1 (35集)                  ││
│  ├──────────────────────────────────┤│
│  │ [qq] 第1集                       ││
│  │ [qq] 第2集                       ││
│  │ [qiyi] 第1集                     ││
│  │ [qiyi] 第2集  ← 点击选中加载弹幕 ││
│  │ ...                              ││
│  └──────────────────────────────────┘│
└──────────────────────────────────────┘
```

选中某个 episode 后：
1. 调用 `notifier.selectEpisode(episodeId)` 加载弹幕
2. 自动保存绑定（`saveDanmuBinding`）
3. 返回播放器页面，弹幕面板自动更新

---

## 七、与播放器集成

### 7.1 修改 CommonPlayerLayout

在 `common_player_layout.dart` 的 Stack 中，Controls 层之前插入弹幕层：

```dart
Stack(
  children: [
    // 1. Video layer
    _buildVideoLayer(),
    // 2. Loading overlay
    _DelayedLoadingOverlay(...),
    // 3. Error overlay
    ErrorOverlay(...),
    // >>> 4. 弹幕渲染层 (NEW) <<<
    if (fileId != null) DanmuOverlay(fileId: fileId!),
    // 5. Controls layer
    if (controlsVisible) _buildControlsLayer(),
  ],
)
```

### 7.2 修改 MobileBottomBar

在 `mobile_bottom_bar.dart` 的按钮行中，添加弹幕按钮（紧跟在字幕按钮之后）：

```dart
// 弹幕按钮
_buildControlButton(
  icon: state.danmuEnabled ? Icons.subtitles : Icons.subtitles_off,
  label: '弹幕',
  onTap: () => _openDanmuPanel(context),
),
```

### 7.3 修改 MobileTopBar

在 `mobile_top_bar.dart` 右上角区域添加手动搜索入口：

```dart
_buildIconButton(
  icon: Icons.search,
  onTap: () => _openDanmuSearch(context),
),
```

### 7.4 PlaybackState 扩展

在 `PlaybackState` 中添加弹幕相关字段：

```dart
// 弹幕
final bool danmuEnabled;
final int danmuCount;
```

### 7.5 面板注册

在 `mobile_controls.dart` 的面板构建器中注册弹幕面板：

```dart
'buildDanmuPanel': (state, notifier) =>
    DanmuPanel(fileId: state.fileId!),
```

---

## 八、数据流总览

```
用户开启弹幕
    │
    ▼
DanmuNotifier.enable()
    │
    ├─ POST /api/danmu/match/auto  →  DanmuMatchResult
    │     ├── sources[]     → 面板列表展示
    │     ├── best_match    → 黄色高亮
    │     ├── danmu_data    → 加载第一片弹幕
    │     │     ├── comments[]     → DanmuController.loadDanmuData()
    │     │     └── segment_list[] → 保存，用于后续加载
    │     └── binding       → 保存绑定关系
    │
    ▼
播放器 position 更新 (每秒 ~60 次)
    │
    ├─ DanmuController.onPositionUpdate(position)
    │     ├── 清除过期弹幕
    │     ├── 二分查找当前时间窗口弹幕
    │     ├── 轨道分配 → DanmuItem
    │     └── 检查是否需要加载下一分片
    │           └── 触发 _onNeedLoadSegment
    │                 └── GET /api/danmu/{episode_id}/next-segment
    │                       └── appendComments()
    │
    ▼
DanmuOverlay (Ticker @ 60fps)
    │
    └─ CustomPaint(DanmuRenderer)
         └─ 遍历 activeItems，Canvas.drawParagraph()
```

---

## 九、性能保障措施

| 层级 | 措施 | 效果 |
|---|---|---|
| **数据** | 二分查找 + 有序数组 | O(log n) 弹幕定位 |
| **布局** | 轨道预分配，无运行时计算 | O(1) 分配 |
| **渲染** | 单 CustomPainter + Paragraph 缓存 | 零 Widget 开销 |
| **网络** | 分片预加载（提前 30s） | 无播放中断 |
| **内存** | 过期弹幕及时回收 + 同屏上限 100 | 内存可控 |
| **隔离** | 弹幕 Ticker 独立于播放器帧回调 | 不抢占 media_kit |
| **交互** | IgnorePointer 包裹弹幕层 | 不拦截手势事件 |

---

## 十、实现优先级建议

1. **P0 — 核心链路**：models → API → DanmuController(引擎) → DanmuOverlay(渲染) → DanmuPanel(开关+源列表) → 集成到 CommonPlayerLayout
2. **P1 — 分片加载**：segment 预加载、next-segment API 调用
3. **P2 — 手动搜索**：DanmuSearchPage → Bangumi 详情页 → 选集加载
4. **P3 — 体验优化**：透明度/区域调节、弹幕密度控制、绑定偏移量调整
