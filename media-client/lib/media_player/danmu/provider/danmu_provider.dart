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
  }) =>
      DanmuState(
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
      // ignore: avoid_print
      print('[Danmu] match result: isMatched=${result.isMatched}, '
          'sources=${result.sources.length}, '
          'bestMatch=${result.bestMatch?.animeTitle}, '
          'danmuData=${result.danmuData != null ? '${result.danmuData!.count} comments' : 'null'}, '
          'binding=${result.binding != null}');
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
    } catch (e, st) {
      // ignore: avoid_print
      print('[Danmu] enable error: $e\n$st');
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 切换弹幕开关
  void toggle() {
    if (state.enabled) {
      _engine?.disposeEngine();
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
      final data = await _api.getDanmuByEpisode(source.episodeId, _fileId);
      _engine?.loadDanmuData(data);
      state = state.copyWith(
        loading: false,
        danmuData: data,
        totalDanmuCount: data.count,
      );
      // Auto save binding when user selects a different source
      await _api.saveDanmuBinding(_fileId, source.episodeId);
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
      final data = await _api.getDanmuByEpisode(episodeId, _fileId);
      _engine?.loadDanmuData(data);
      state = state.copyWith(
        loading: false,
        danmuData: data,
        totalDanmuCount: data.count,
      );
      // Save binding
      await _api.saveDanmuBinding(_fileId, episodeId);
    } catch (e) {
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 分片加载回调
  Future<void> _loadSegment(DanmuSegment segment) async {
    try {
      final episodeId = state.danmuData?.episodeId;
      final result = await _api.danmuNextSegment(segment, episodeId: episodeId);
      _engine?.onSegmentLoaded(result.comments);
      state = state.copyWith(loadedSegmentIndex: state.loadedSegmentIndex + 1);
    } catch (_) {
      // _isLoadingSegment 由 engine 内部管理
    }
  }

  @override
  void dispose() {
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
