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
        manualSource: clearManualSource ? null : (manualSource ?? this.manualSource),
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

  /// 选择不同的源（自动匹配列表中的源）
  Future<void> selectSource(DanmuSource source) async {
    // ignore: avoid_print
    print('[Danmu] selectSource: episodeId=${source.episodeId}, '
        'title=${source.animeTitle}, episode=${source.episodeTitle}');
    state = state.copyWith(loading: true, selectedSource: source);
    try {
      final data = await _api.getDanmuByEpisode(source.episodeId, _fileId);
      _applyDanmuData(data);
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

  /// 手动选择 bangumi episode（带 bangumi 信息，用于面板展示）
  Future<void> selectEpisodeFromBangumi({
    required int episodeId,
    required int animeId,
    required String animeTitle,
    required String episodeTitle,
    required String type,
    required String typeDescription,
    required String imageUrl,
  }) async {
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
    state = state.copyWith(
        loading: true,
        manualSource: manualSource,
        selectedSource: manualSource);
    try {
      final data = await _api.getDanmuByEpisode(episodeId, _fileId);
      _applyDanmuData(data);
      state = state.copyWith(
        loading: false,
        danmuData: data,
        totalDanmuCount: data.count,
      );
    } catch (e) {
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
    try {
      // ignore: avoid_print
      print('[Danmu] loadSegment: type=${segment.type}, '
          'start=${segment.segmentStart}, end=${segment.segmentEnd}');
      final episodeId = state.danmuData?.episodeId;
      if (episodeId == null) return;
      final result = await _api.danmuNextSegment(segment, episodeId);
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
