import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/danmu_models.dart';
import '../service/danmaku_service.dart';
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

  // 引擎版本号：每次创建新引擎时递增，用于 DanmuOverlay 检测引擎变更并重建 DanmakuScreen
  final int engineVersion;

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
    this.engineVersion = 0,
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
    int? engineVersion,
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
        engineVersion: engineVersion ?? this.engineVersion,
      );
}

// ---- Notifier ----

class DanmuNotifier extends StateNotifier<DanmuState> {
  final ApiClient _api;
  final String _fileId;
  DanmuController? _engine;

  /// 最近一次 Ticker 帧的视频播放位置（秒），用于在加载弹幕数据时
  /// 立即触发当前播放位置对应的分片加载，避免等待下一帧。
  double _lastKnownPosition = 0;

  /// 异步请求序号，用于丢弃过期回调。
  /// 每次引擎生命周期变化（开启/关闭/切换源）都会递增，
  /// 确保旧的异步回调不会写入已被 dispose 或重建的引擎。
  int _requestId = 0;

  /// 引擎版本号，每次创建新引擎时递增。
  /// 用于 DanmuOverlay 检测引擎变更并重建 DanmakuScreen（重新注入 canvas 控制器）。
  int _engineVersion = 0;

  DanmuNotifier(this._api, this._fileId) : super(const DanmuState());

  DanmuController? get engine => _engine;

  /// 更新最近已知的视频播放位置（由 Ticker 每帧调用）
  void updatePosition(double positionSeconds) {
    _lastKnownPosition = positionSeconds;
  }

  /// 开启弹幕：触发自动匹配
  Future<void> enable() async {
    final requestId = ++_requestId;
    state = state.copyWith(enabled: true, loading: true, clearError: true);
    try {
      final result = await _api.danmuAutoMatch(_fileId);
      // 引擎已被 dispose（toggle OFF/ON 或 dispose）或有更新的请求，丢弃结果
      if (_requestId != requestId) return;
      // 在 requestId 检查通过后再创建引擎，避免创建后被丢弃
      final engine = DanmuController();
      _engine = engine;
      _engineVersion++;
      _applyDanmuData(result.danmuData, currentPosition: _lastKnownPosition);
      state = state.copyWith(
        loading: false,
        matchResult: result,
        sources: result.sources,
        selectedSource: result.bestMatch,
        danmuData: result.danmuData,
        totalDanmuCount: result.danmuData?.count ?? 0,
        binding: result.binding,
        engineVersion: _engineVersion,
      );
    } catch (e) {
      if (_requestId != requestId) return;
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
        final engineCreated = _applyDanmuData(state.danmuData, currentPosition: _lastKnownPosition);
        state = state.copyWith(
          enabled: true,
          clearError: true,
          engineVersion: engineCreated ? _engineVersion : null,
        );
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
    state = state.copyWith(loading: true, clearError: true);
    try {
      final data = await _api.getDanmuByEpisode(source.episodeId, _fileId);
      if (_requestId != requestId) return;
      // 只在弹幕开启时加载到引擎；关闭时只更新 state 缓存
      bool engineCreated = false;
      if (state.enabled) {
        engineCreated = _applyDanmuData(data, currentPosition: _lastKnownPosition);
      }
      // selectedSource 与 danmuData 原子更新，保证一致性
      state = state.copyWith(
        loading: false,
        selectedSource: source,
        danmuData: data,
        totalDanmuCount: data.count,
        engineVersion: engineCreated ? _engineVersion : null,
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
      bool engineCreated = false;
      if (state.enabled) {
        engineCreated = _applyDanmuData(data, currentPosition: _lastKnownPosition);
      }
      // selectedSource 与 danmuData 原子更新，保证一致性
      state = state.copyWith(
        loading: false,
        selectedSource: manualSource,
        danmuData: data,
        totalDanmuCount: data.count,
        engineVersion: engineCreated ? _engineVersion : null,
      );
    } catch (e) {
      if (_requestId != requestId) return;
      state = state.copyWith(loading: false, error: e.toString());
    }
  }

  /// 更新弹幕时间偏移（纯前端，不持久化到服务器）
  void updateOffset(double offset) {
    _engine?.setTimeOffset(offset);
  }

  /// 统一加载弹幕数据到引擎（自动匹配/手动搜索/切换源 共用）
  ///
  /// 处理流程：
  /// 1. 确保引擎存在（手动搜索场景下 engine 可能为 null）
  /// 2. 将 comments 加载到引擎（排序 + 清空活跃弹幕）
  /// 3. 注册分片加载回调（后续 segment_list 中的片段通过 next-segment API 获取）
  /// 4. 立即触发当前播放位置对应的分片加载
  /// 加载弹幕数据到引擎。如果引擎不存在则创建新引擎。
  /// 返回 true 表示创建了新引擎（调用方需在后续 state 更新中包含 engineVersion）。
  bool _applyDanmuData(DanmuData? data, {double currentPosition = 0}) {
    if (data == null) return false;
    bool engineCreated = false;
    if (_engine == null) {
      _engine = DanmuController();
      _engineVersion++;
      engineCreated = true;
      // 新引擎：从绑定读取初始偏移
      _engine!.setTimeOffset(state.binding?.offset ?? 0);
    }
    // 已有引擎：保留用户手动设置的时间偏移
    _engine!.setOnNeedLoadSegment(_loadSegment);
    _engine!.loadDanmuData(data, currentPosition: currentPosition);
    return engineCreated;
  }

  /// 分片加载回调
  Future<void> _loadSegment(DanmuSegment segment) async {
    // 捕获当前 requestId 和引擎引用，防止异步完成后写入已失效的引擎
    final requestId = _requestId;
    final engine = _engine;
    if (engine == null) {
      print('[Danmu] _loadSegment: engine 为 null，丢弃');
      return;
    }
    try {
      final episodeId = state.danmuData?.episodeId;
      if (episodeId == null) {
        print('[Danmu] _loadSegment: episodeId 为 null，丢弃');
        return;
      }
      print('[Danmu] _loadSegment: 请求分片 episodeId=$episodeId, '
          'range=[${segment.segmentStart}, ${segment.segmentEnd}]');
      final result = await _api.danmuNextSegment(segment, episodeId);
      // 引擎已被 dispose 或有新的操作，丢弃结果
      if (_requestId != requestId || !identical(engine, _engine)) {
        print('[Danmu] _loadSegment: 引擎已变更(reqId=$_requestId!=$requestId 或 '
            'engine changed)，丢弃 ${result.comments.length} 条');
        return;
      }
      print('[Danmu] _loadSegment: 加载成功 +${result.comments.length}条, '
          'episodeId=$episodeId');
      engine.onSegmentLoaded(result.comments);
      state = state.copyWith(loadedSegmentIndex: state.loadedSegmentIndex + 1);
    } catch (e) {
      print('[Danmu] _loadSegment: 异常 $e');
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
