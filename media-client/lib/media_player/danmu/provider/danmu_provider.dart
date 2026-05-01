import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/danmu_models.dart';
import '../engine/danmu_controller.dart';
import '../api/danmu_api.dart';

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

  // 手动搜索选中的源
  final DanmuSource? manualSource;

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
    this.manualSource,
  });

  DanmuState copyWith({
    bool? enabled,
    bool? loading,
    String? error,
    bool clearError = false,
    DanmuMatchResult? matchResult,
    List<DanmuSource>? sources,
    DanmuSource? selectedSource,
    DanmuData? danmuData,
    int? loadedSegmentIndex,
    int? totalDanmuCount,
    List<DanmuSearchItem>? searchResults,
    bool? searchLoading,
    DanmuBinding? binding,
    DanmuSource? manualSource,
    bool clearManualSource = false,
  }) =>
      DanmuState(
        enabled: enabled ?? this.enabled,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
        matchResult: matchResult ?? this.matchResult,
        sources: sources ?? this.sources,
        selectedSource: selectedSource ?? this.selectedSource,
        danmuData: danmuData ?? this.danmuData,
        loadedSegmentIndex: loadedSegmentIndex ?? this.loadedSegmentIndex,
        totalDanmuCount: totalDanmuCount ?? this.totalDanmuCount,
        searchResults: searchResults ?? this.searchResults,
        searchLoading: searchLoading ?? this.searchLoading,
        binding: binding ?? this.binding,
        manualSource: clearManualSource ? null : (manualSource ?? this.manualSource),
      );
}

// ---- Notifier ----

class DanmuNotifier extends StateNotifier<DanmuState> {
  final ApiClient _api;
  final String _fileId;
  DanmuController? _engine;

  /// 异步请求序号，用于丢弃过期回调。
  /// 每次引擎生命周期变化（开启/关闭/切换源）都会递增，
  /// 确保旧的异步回调不会写入已被 dispose 或重建的引擎。
  int _requestId = 0;

  DanmuNotifier(this._api, this._fileId) : super(const DanmuState());

  DanmuController? get engine => _engine;

  /// 开启弹幕：触发自动匹配
  Future<void> enable() async {
    final requestId = ++_requestId;
    state = state.copyWith(enabled: true, loading: true, clearError: true);
    try {
      final result = await _api.danmuAutoMatch(_fileId);
      // 引擎已被 dispose（toggle OFF/ON 或 dispose）或有更新的请求，丢弃结果
      if (_requestId != requestId) return;
      // ignore: avoid_print
      print('[Danmu] match result: isMatched=${result.isMatched}, '
          'sources=${result.sources.length}, '
          'bestMatch=${result.bestMatch?.animeTitle}, '
          'danmuData=${result.danmuData != null ? '${result.danmuData!.count} comments' : 'null'}, '
          'binding=${result.binding != null}');
      // 在 requestId 检查通过后再创建引擎，避免创建后被丢弃
      final engine = DanmuController();
      _engine = engine;
      _applyDanmuData(result.danmuData);
      state = state.copyWith(
        loading: false,
        matchResult: result,
        sources: result.sources,
        selectedSource: result.bestMatch,
        danmuData: result.danmuData,
        totalDanmuCount: result.danmuData?.count ?? 0,
        binding: result.binding,
      );
    } catch (e, st) {
      if (_requestId != requestId) return;
      // ignore: avoid_print
      print('[Danmu] enable error: $e\n$st');
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 切换弹幕开关
  void toggle() {
    if (state.enabled) {
      // 关闭弹幕：递增 requestId 使所有进行中的异步回调失效
      // 保留引擎实例，避免重建引擎后 seek 检测误触发清空弹幕
      _requestId++;
      state = state.copyWith(enabled: false);
    } else {
      // 开启弹幕：递增 requestId 使旧的 enable() 回调失效
      _requestId++;
      if (state.selectedSource != null && state.danmuData != null) {
        // 已有匹配源和弹幕数据，直接复用，不重新请求 API
        state = state.copyWith(enabled: true, clearError: true);
        _applyDanmuData(state.danmuData);
      } else {
        enable();
      }
    }
  }

  /// 选择不同的源（自动匹配列表中的源）
  ///
  /// 弹幕关闭时也会被调用（用户在面板中切换源），此时只更新状态不操作引擎。
  /// 注意：selectedSource 与 danmuData 必须在同一帧原子更新，
  /// 防止快速切换时两者脱节导致 toggle 复用错误的缓存数据。
  Future<void> selectSource(DanmuSource source) async {
    final requestId = ++_requestId;
    // ignore: avoid_print
    print('[Danmu] selectSource: episodeId=${source.episodeId}, '
        'title=${source.animeTitle}, episode=${source.episodeTitle}');
    state = state.copyWith(loading: true, clearError: true);
    try {
      final data = await _api.getDanmuByEpisode(source.episodeId, _fileId);
      if (_requestId != requestId) return;
      // 只在弹幕开启时加载到引擎；关闭时只更新 state 缓存
      if (state.enabled) {
        _applyDanmuData(data);
      }
      // selectedSource 与 danmuData 原子更新，保证一致性
      state = state.copyWith(
        loading: false,
        selectedSource: source,
        danmuData: data,
        totalDanmuCount: data.count,
      );
    } catch (e) {
      if (_requestId != requestId) return;
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 搜索弹幕
  Future<void> search(String keyword) async {
    state = state.copyWith(searchLoading: true, clearError: true);
    try {
      final results = await _api.danmuSearch(keyword);
      state = state.copyWith(searchResults: results, searchLoading: false);
    } catch (e) {
      state = state.copyWith(searchLoading: false, error: e.toString());
    }
  }

  /// 手动选择 bangumi episode（带 bangumi 信息，用于面板展示）
  ///
  /// 弹幕关闭时也会被调用，此时只更新状态不操作引擎。
  /// 注意：manualSource / selectedSource 与 danmuData 必须在同一帧原子更新。
  Future<void> selectEpisodeFromBangumi({
    required int episodeId,
    required int animeId,
    required String animeTitle,
    required String episodeTitle,
    required String type,
    required String typeDescription,
    required String imageUrl,
  }) async {
    final requestId = ++_requestId;
    // ignore: avoid_print
    print('[Danmu] selectEpisodeFromBangumi: episodeId=$episodeId, '
        'anime=$animeTitle, episode=$episodeTitle');
    final manualSource = DanmuSource(
      episodeId: episodeId,
      animeId: animeId,
      animeTitle: animeTitle,
      episodeTitle: episodeTitle,
      type: type,
      typeDescription: typeDescription,
      shift: 0,
      imageUrl: imageUrl,
    );
    // manualSource 先写入（用于搜索页展示"手动"标签），但 selectedSource 等 API 返回后更新
    state = state.copyWith(
        loading: true,
        manualSource: manualSource,
        clearError: true);
    try {
      final data = await _api.getDanmuByEpisode(episodeId, _fileId);
      if (_requestId != requestId) return;
      // 只在弹幕开启时加载到引擎；关闭时只更新 state 缓存
      if (state.enabled) {
        _applyDanmuData(data);
      }
      // selectedSource 与 danmuData 原子更新，保证一致性
      state = state.copyWith(
        loading: false,
        selectedSource: manualSource,
        danmuData: data,
        totalDanmuCount: data.count,
      );
    } catch (e) {
      if (_requestId != requestId) return;
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 统一加载弹幕数据到引擎（自动匹配/手动搜索/切换源 共用）
  ///
  /// 处理流程：
  /// 1. 确保引擎存在（手动搜索场景下 engine 可能为 null）
  /// 2. 将 comments 加载到引擎（排序 + 清空活跃弹幕）
  /// 3. 注册分片加载回调（后续 segment_list 中的片段通过 next-segment API 获取）
  void _applyDanmuData(DanmuData? data) {
    if (data == null) return;
    if (_engine == null) {
      // ignore: avoid_print
      print('[Danmu] _applyDanmuData: engine was null, creating new one');
      _engine = DanmuController();
    }
    _engine!.loadDanmuData(data);
    _engine!.setOnNeedLoadSegment(_loadSegment);
    // ignore: avoid_print
    print('[Danmu] _applyDanmuData: loaded ${data.count} comments, '
        '${data.segmentList.length} segments');
  }

  /// 分片加载回调
  Future<void> _loadSegment(DanmuSegment segment) async {
    // 捕获当前 requestId 和引擎引用，防止异步完成后写入已失效的引擎
    final requestId = _requestId;
    final engine = _engine;
    if (engine == null) return;
    try {
      // ignore: avoid_print
      print('[Danmu] loadSegment: type=${segment.type}, '
          'start=${segment.segmentStart}, end=${segment.segmentEnd}');
      final episodeId = state.danmuData?.episodeId;
      if (episodeId == null) return;
      final result = await _api.danmuNextSegment(segment, episodeId);
      // 引擎已被 dispose 或有新的操作，丢弃结果
      if (_requestId != requestId || !identical(engine, _engine)) return;
      engine.onSegmentLoaded(result.comments);
      state = state.copyWith(loadedSegmentIndex: state.loadedSegmentIndex + 1);
    } catch (e) {
      // ignore: avoid_print
      print('[Danmu] loadSegment error: $e');
    } finally {
      // 无论成功失败都重置加载状态，防止卡在 _isLoadingSegment=true
      // 只重置当前引擎（如果还是同一个的话）
      if (identical(engine, _engine)) {
        engine.resetSegmentLoading();
      }
    }
  }

  @override
  void dispose() {
    _requestId++; // 使所有进行中的异步回调失效
    _engine?.disposeEngine();
    super.dispose();
  }
}

// ---- Providers ----

final danmuProvider = StateNotifierProvider.family
    .autoDispose<DanmuNotifier, DanmuState, String>((ref, fileId) {
  final api = ref.read(apiClientProvider);
  return DanmuNotifier(api, fileId);
});
