import 'package:flutter/material.dart';
import 'package:canvas_danmaku/canvas_danmaku.dart' as cd;
import '../models/danmu_models.dart';

/// 弹幕服务层：连接数据层（API/Provider）和视图层（DanmakuScreen）
///
/// 职责：
/// 1. 持有 canvas_danmaku 的 DanmakuController 实例
/// 2. 数据转换：DanmuComment → DanmakuContentItem
/// 3. 发射调度：二分查找 + 定时发射（读视频位置，调用 addDanmaku）
/// 4. Seek 检测：位置跳变 >1s 时调用 clear
/// 5. 分片管理：segment lazy loading
/// 6. 设置映射：用户设置 → DanmakuOption
class DanmuController extends ChangeNotifier {
  // === canvas_danmaku 控制器（由 DanmuOverlay 在 createdController 回调中注入） ===
  cd.DanmakuController<DanmuComment>? _canvasController;

  // === 用户设置 ===
  double _opacity = 0.5;
  double _fontSize = 15;
  double _area = 0.3;
  double _speed = 130; // px/s
  double _playbackSpeed = 1.0;
  double _density = 1.0;
  double _timeOffset = 0;

  // === 弹幕数据 ===
  final List<DanmuComment> _allComments = [];
  List<DanmuComment> _sortedByTime = [];
  final Set<int> _activeCids = {}; // O(1) 去重

  // === 分片管理 ===
  List<DanmuSegment> _segments = [];
  int _currentSegmentIndex = 0;
  bool _isLoadingSegment = false;
  final Set<int> _loadedSegments = {0};

  // === 发射控制 ===
  static const double _lookAheadSeconds = 3.0;
  static const double _minFireGap = 0.3;
  double _nextFireElapsed = 0;
  double _currentPosition = 0;
  double _lastPosition = 0;

  // === 密度控制 ===
  double _lastFireTime = 0;

  // === 分片加载回调 ===
  void Function(DanmuSegment segment)? _onNeedLoadSegment;

  // === 视口尺寸 ===
  double _viewWidth = 0;

  // ---- 公开 API（保持与旧 DanmuController 签名一致）----

  double get opacity => _opacity;
  double get fontSize => _fontSize;
  double get area => _area;
  double get speed => _speed;
  double get playbackSpeed => _playbackSpeed;
  double get density => _density;
  int get totalCount => _allComments.length;
  double get currentPosition => _currentPosition;

  /// 是否有活跃弹幕（用于 Ticker 生命周期管理）
  bool get hasActiveItems => _canvasController?.running ?? false;

  // ---- canvas 控制器注入 ----

  /// 由 DanmuOverlay 在 DanmakuScreen.createdController 回调中调用
  void attachCanvasController(cd.DanmakuController<DanmuComment> controller) {
    _canvasController = controller;
    _syncOptionToCanvas();
  }

  // ---- 初始化 ----

  void init({required double viewWidth, required double viewHeight}) {
    _viewWidth = viewWidth;
    _syncOptionToCanvas();
  }

  // ---- 数据加载 ----

  void loadDanmuData(DanmuData data, {double currentPosition = 0}) {
    _allComments.clear();
    _activeCids.clear();
    _canvasController?.clear();

    _allComments.addAll(data.comments);
    _segments = data.segmentList;
    _currentSegmentIndex = 0;
    _isLoadingSegment = false;
    _loadedSegments
      ..clear()
      ..add(0);

    if (_lastPosition == 0) {
      _lastPosition = currentPosition;
    }
    _nextFireElapsed = 0;
    _lastFireTime = 0;
    _sortedByTime = List.of(_allComments)
      ..sort((a, b) => a.time.compareTo(b.time));

    if (currentPosition > 0) {
      _maybeLoadNextSegment(currentPosition);
    }

    notifyListeners();
  }

  void appendComments(List<DanmuComment> comments) {
    if (comments.isEmpty) return;
    _allComments.addAll(comments);
    final newSorted = List<DanmuComment>.of(comments)
      ..sort((a, b) => a.time.compareTo(b.time));
    _sortedByTime = _mergeSorted(_sortedByTime, newSorted);
  }

  static List<DanmuComment> _mergeSorted(
    List<DanmuComment> a,
    List<DanmuComment> b,
  ) {
    final result = <DanmuComment>[];
    int i = 0, j = 0;
    while (i < a.length && j < b.length) {
      if (a[i].time <= b[j].time) {
        result.add(a[i++]);
      } else {
        result.add(b[j++]);
      }
    }
    while (i < a.length) {
      result.add(a[i++]);
    }
    while (j < b.length) {
      result.add(b[j++]);
    }
    return result;
  }

  // ---- 设置方法 ----

  void setOpacity(double v) {
    _opacity = v.clamp(0.0, 1.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setFontSize(double v) {
    _fontSize = v.clamp(12.0, 32.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setArea(double v) {
    _area = v.clamp(0.2, 1.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setSpeed(double v) {
    _speed = v.clamp(60.0, 300.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setPlaybackSpeed(double v) {
    _playbackSpeed = v.clamp(0.25, 4.0);
    _syncOptionToCanvas();
  }

  void setDensity(double v) {
    _density = v.clamp(0.1, 1.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setTimeOffset(double v) {
    _timeOffset = v;
  }

  // ---- 核心：设置映射到 DanmakuOption ----

  void _syncOptionToCanvas() {
    final cc = _canvasController;
    if (cc == null) return;

    // speed (px/s) → duration (秒)
    final effectiveSpeed = _speed * _playbackSpeed;
    final duration = _viewWidth > 0
        ? (_viewWidth / effectiveSpeed).clamp(3.0, 30.0)
        : 10.0;

    // density → massiveMode + area 微调
    final massiveMode = _density >= 0.7;
    final effectiveArea = _density < 0.3
        ? (_area * 0.8).clamp(0.2, 1.0)
        : _area;

    cc.updateOption(cc.option.copyWith(
      fontSize: _fontSize,
      area: effectiveArea,
      duration: duration,
      opacity: _opacity,
      massiveMode: massiveMode,
      strokeWidth: 1.5,
      safeArea: false,
      staticDuration: 5.0,
    ));
  }

  // ---- 帧更新（由 DanmuOverlay 的 Ticker 驱动）----

  void updateFrame(double positionSeconds, double elapsedSeconds) {
    _currentPosition = positionSeconds;
    bool dirty = false;

    // 1. Seek 检测
    final positionDelta = (positionSeconds - _lastPosition).abs();
    if (positionDelta > 1.0 && _lastPosition != 0) {
      _canvasController?.clear();
      _activeCids.clear();
      _nextFireElapsed = 0;
      _currentSegmentIndex = 0;
      _lastFireTime = 0;
      dirty = true;
    }
    _lastPosition = positionSeconds;

    // 2. 分片加载
    _maybeLoadNextSegment(positionSeconds);

    // 3. 清理过期 cid
    _pruneExpiredCids();

    // 4. 发射新弹幕
    final prevCidCount = _activeCids.length;
    _fireNewDanmu(positionSeconds, elapsedSeconds);
    if (_activeCids.length != prevCidCount) dirty = true;

    if (dirty) notifyListeners();
  }

  void onPositionUpdate(double positionSeconds) {
    _currentPosition = positionSeconds;
    _maybeLoadNextSegment(positionSeconds);
  }

  // ---- 发射逻辑 ----

  void _fireNewDanmu(double position, double elapsed) {
    if (elapsed < _nextFireElapsed) return;

    // 密度门控
    final minGap = _minFireGap + (1.0 - _density) * 0.5;
    if (elapsed - _lastFireTime < minGap) return;

    final adjustedPosition = position + _timeOffset;
    final windowEnd = adjustedPosition + _lookAheadSeconds;

    // 二分查找定位起始位置
    int lo = 0, hi = _sortedByTime.length;
    while (lo < hi) {
      final mid = (lo + hi) >> 1;
      if (_sortedByTime[mid].time < adjustedPosition) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }

    // 密度控制：限制每帧发射数量
    final maxFirePerFrame = _density >= 0.7 ? 5 : (_density >= 0.4 ? 3 : 1);
    int fired = 0;

    for (int i = lo; i < _sortedByTime.length; i++) {
      final comment = _sortedByTime[i];
      if (comment.time > windowEnd) break;
      if (_activeCids.contains(comment.cid)) continue;
      if (fired >= maxFirePerFrame) break;

      final item = _commentToContentItem(comment);
      _canvasController?.addDanmaku(item);
      _activeCids.add(comment.cid);
      _nextFireElapsed = elapsed + minGap;
      _lastFireTime = elapsed;
      fired++;
    }
  }

  /// DanmuComment → DanmakuContentItem 转换
  cd.DanmakuContentItem<DanmuComment> _commentToContentItem(
      DanmuComment comment) {
    return cd.DanmakuContentItem<DanmuComment>(
      comment.content,
      color: Color(comment.color).withAlpha(255),
      type: _danmakuTypeFromMode(comment.mode),
      extra: comment,
    );
  }

  static cd.DanmakuItemType _danmakuTypeFromMode(int mode) {
    switch (mode) {
      case 4:
        return cd.DanmakuItemType.bottom;
      case 5:
        return cd.DanmakuItemType.top;
      default:
        return cd.DanmakuItemType.scroll;
    }
  }

  /// 防止 _activeCids 无限增长
  void _pruneExpiredCids() {
    if (_activeCids.length > 500) {
      _activeCids.clear();
    }
  }

  // ---- 分片管理（保留原逻辑）----

  void _maybeLoadNextSegment(double position) {
    if (_isLoadingSegment) return;
    if (_segments.isEmpty) return;

    // 快速跳过已加载的分片
    while (_currentSegmentIndex < _segments.length - 1 &&
        _loadedSegments.contains(_currentSegmentIndex)) {
      _currentSegmentIndex++;
    }

    // 跳过位置已超过的分片（向前跳转场景）
    while (_currentSegmentIndex < _segments.length - 1) {
      final nextSeg = _segments[_currentSegmentIndex + 1];
      if (position >= nextSeg.segmentStart - 30) {
        _currentSegmentIndex++;
      } else {
        break;
      }
    }

    // 当前分片是否需要加载
    if (_currentSegmentIndex >= _segments.length) return;
    if (_loadedSegments.contains(_currentSegmentIndex)) return;

    final seg = _segments[_currentSegmentIndex];
    if (position >= seg.segmentStart - 30) {
      _isLoadingSegment = true;
      _onNeedLoadSegment?.call(seg);
    }
  }

  void onSegmentLoaded(List<DanmuComment> comments) {
    appendComments(comments);
    _loadedSegments.add(_currentSegmentIndex);
    _isLoadingSegment = false;
    _nextFireElapsed = 0;
    notifyListeners();
  }

  void resetSegmentLoading() {
    _isLoadingSegment = false;
  }

  void setOnNeedLoadSegment(void Function(DanmuSegment) cb) {
    _onNeedLoadSegment = cb;
  }

  // ---- 资源释放 ----

  void disposeEngine() {
    _canvasController?.clear();
    _canvasController = null;
    _activeCids.clear();
    _allComments.clear();
    _sortedByTime.clear();
    _segments.clear();
    _currentSegmentIndex = 0;
    _isLoadingSegment = false;
    _loadedSegments.clear();
    _nextFireElapsed = 0;
    _onNeedLoadSegment = null;
  }
}
