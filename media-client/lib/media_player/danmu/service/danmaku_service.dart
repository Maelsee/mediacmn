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
  double _fontSize = 17;
  double _area = 0.3;
  double _speed = 70; // px/s
  double _playbackSpeed = 1.0;
  double _density = 0.3;
  double _timeOffset = 0;

  // === 弹幕数据 ===
  final List<DanmuComment> _allComments = [];
  List<DanmuComment> _sortedByTime = [];
  final Set<int> _activeCids = {}; // O(1) 去重

  // === 分片管理 ===
  List<DanmuSegment> _segments = [];
  bool _isLoadingSegment = false;
  int _pendingSegmentIndex = -1; // 正在加载的分片索引
  final Set<int> _loadedSegments = {0};

  // === 发射控制 ===
  static const double _lookAheadSeconds = 3.0;
  static const double _minFireGap = 0.3;
  double _nextFireElapsed = 0;
  double _currentPosition = 0;
  double _lastPosition = 0;

  // === 密度控制 ===
  double _lastFireTime = 0;

  // === 调试 ===
  int _frameCount = 0;

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
  double get timeOffset => _timeOffset;
  int get totalCount => _allComments.length;
  double get currentPosition => _currentPosition;

  // ---- canvas 控制器注入 ----

  /// 由 DanmuOverlay 在 DanmakuScreen.createdController 回调中调用
  void attachCanvasController(cd.DanmakuController<DanmuComment> controller) {
    _canvasController = controller;
    print('[Danmu] canvas 控制器已注入');
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
    _isLoadingSegment = false;
    _pendingSegmentIndex = -1;
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

    final firstTime = _sortedByTime.isNotEmpty ? _sortedByTime.first.time : 0;
    final lastTime = _sortedByTime.isNotEmpty ? _sortedByTime.last.time : 0;
    print('[Danmu] 数据加载完成: comments=${data.comments.length}, '
        'segments=${_segments.length}, sorted=${_sortedByTime.length}, '
        'timeRange=[${firstTime.toStringAsFixed(1)}, ${lastTime.toStringAsFixed(1)}], '
        'pos=${currentPosition.toStringAsFixed(1)}, canvas=$_canvasController');

    if (currentPosition > 0) {
      _maybeLoadNextSegment(currentPosition);
    }

    notifyListeners();
  }

  void appendComments(List<DanmuComment> comments) {
    if (comments.isEmpty) return;
    final oldLen = _sortedByTime.length;
    _allComments.addAll(comments);
    final newSorted = List<DanmuComment>.of(comments)
      ..sort((a, b) => a.time.compareTo(b.time));
    _sortedByTime = _mergeSorted(_sortedByTime, newSorted);
    final newFirst = _sortedByTime.isNotEmpty ? _sortedByTime.first.time : 0;
    final newLast = _sortedByTime.isNotEmpty ? _sortedByTime.last.time : 0;
    print('[Danmu] appendComments: +${comments.length}, sorted $oldLen -> ${_sortedByTime.length}, '
        'timeRange=[${newFirst.toStringAsFixed(1)}, ${newLast.toStringAsFixed(1)}]');
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
    _area = v.clamp(0.0, 1.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setSpeed(double v) {
    _speed = v.clamp(20.0, 200.0);
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setPlaybackSpeed(double v) {
    _playbackSpeed = v.clamp(0.25, 4.0);
    _syncOptionToCanvas();
  }

  void setDensity(double v) {
    _density = v.clamp(0.1, 1.0);
    // density 仅控制 massiveMode（轨道占满时是否叠加），不再混入 area 调整
    _syncOptionToCanvas();
    notifyListeners();
  }

  void setTimeOffset(double v) {
    final old = _timeOffset;
    _timeOffset = v;
    if (old != v) {
      final direction = v > 0 ? '弹幕慢于视频' : (v < 0 ? '弹幕快于视频' : '无偏移');
      print('[Danmu] 时间偏移变更: ${old.toStringAsFixed(1)}s -> ${v.toStringAsFixed(1)}s ($direction)');
    }
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

    // density → massiveMode（轨道占满时是否叠加显示）
    final massiveMode = _density >= 0.5;

    // 注意：opacity 不在此处同步，由 DanmuOverlay 通过 Opacity widget 控制
    // 原因：canvas_danmaku 的 _updateOption 不会 setState，导致 Opacity widget 不重建
    cc.updateOption(cc.option.copyWith(
      fontSize: _fontSize,
      area: _area,
      duration: duration,
      opacity: 1.0, // 固定为 1.0，实际透明度由外层 Opacity widget 控制
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

    // 每 120 帧（约 2 秒）输出一次状态
    if (++_frameCount % 120 == 0) {
      print('[Danmu] 帧更新: pos=${positionSeconds.toStringAsFixed(1)}, '
          'elapsed=${elapsedSeconds.toStringAsFixed(1)}, '
          'sorted=${_sortedByTime.length}, canvas=${_canvasController != null}, '
          'activeCids=${_activeCids.length}, nextFire=${_nextFireElapsed.toStringAsFixed(2)}');
    }

    // 1. Seek 检测
    final positionDelta = (positionSeconds - _lastPosition).abs();
    if (positionDelta > 1.0 && _lastPosition != 0) {
      print('[Danmu] Seek 检测: ${_lastPosition.toStringAsFixed(1)} -> ${positionSeconds.toStringAsFixed(1)}');
      _canvasController?.clear();
      _activeCids.clear();
      _nextFireElapsed = 0;
      _lastFireTime = 0;
      // 重置分片加载状态，允许为新位置加载分片
      _isLoadingSegment = false;
      _pendingSegmentIndex = -1;
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

  // ---- 发射逻辑 ----

  void _fireNewDanmu(double position, double elapsed) {
    if (elapsed < _nextFireElapsed) return;

    // 密度门控
    final minGap = _minFireGap + (1.0 - _density) * 0.5;
    if (elapsed - _lastFireTime < minGap) return;

    final adjustedPosition = position + _timeOffset;
    final windowEnd = adjustedPosition + _lookAheadSeconds;

    // 偏移调试日志（仅在有偏移时输出，避免刷屏）
    if (_timeOffset != 0) {
      final direction = _timeOffset > 0 ? '弹幕慢于视频' : '弹幕快于视频';
      print('[Danmu] 偏移发射: 视频位置=${position.toStringAsFixed(2)}s, '
          '偏移=${_timeOffset.toStringAsFixed(1)}s, '
          '查询位置=${adjustedPosition.toStringAsFixed(2)}s ($direction)');
    }

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
    int candidates = 0;

    for (int i = lo; i < _sortedByTime.length; i++) {
      final comment = _sortedByTime[i];
      if (comment.time > windowEnd) break;
      candidates++;
      if (_activeCids.contains(comment.cid)) continue;
      if (fired >= maxFirePerFrame) break;

      final item = _commentToContentItem(comment);
      _canvasController?.addDanmaku(item);
      _activeCids.add(comment.cid);
      _nextFireElapsed = elapsed + minGap;
      _lastFireTime = elapsed;
      fired++;
    }

    if (fired > 0) {
      print('[Danmu] 发射成功: fired=$fired, candidates=$candidates');
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

  // ---- 分片管理 ----

  /// 查找并加载当前位置需要的分片。
  /// 跳过已过期的分片（end < pos - 30），从当前位置附近开始加载。
  void _maybeLoadNextSegment(double position) {
    if (_isLoadingSegment) return;
    if (_segments.isEmpty) return;

    for (int i = 0; i < _segments.length; i++) {
      if (_loadedSegments.contains(i)) continue;
      final seg = _segments[i];
      // 跳过已过期的分片（结束位置在当前位置 30 秒之前）
      if (seg.segmentEnd < position - 30) continue;
      // 当前位置在分片范围内，或提前 30 秒预加载
      if (position >= seg.segmentStart - 30) {
        print('[Danmu] 请求分片[$i]: '
            'range=[${seg.segmentStart.toStringAsFixed(0)}, ${seg.segmentEnd.toStringAsFixed(0)}], '
            'pos=${position.toStringAsFixed(1)}');
        _pendingSegmentIndex = i;
        _isLoadingSegment = true;
        _onNeedLoadSegment?.call(seg);
        return;
      }
    }
  }

  void onSegmentLoaded(List<DanmuComment> comments) {
    appendComments(comments);
    if (_pendingSegmentIndex >= 0) {
      _loadedSegments.add(_pendingSegmentIndex);
      _pendingSegmentIndex = -1;
    }
    _isLoadingSegment = false;
    _nextFireElapsed = 0;
    final firstT = comments.isNotEmpty ? comments.first.time : 0;
    final lastT = comments.isNotEmpty ? comments.last.time : 0;
    print('[Danmu] 分片加载完成: +${comments.length}条, '
        '总计=${_sortedByTime.length}, loadedSegments=$_loadedSegments, '
        'commentTimeRange=[${firstT.toStringAsFixed(1)}, ${lastT.toStringAsFixed(1)}]');
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
    _isLoadingSegment = false;
    _pendingSegmentIndex = -1;
    _loadedSegments.clear();
    _nextFireElapsed = 0;
    _onNeedLoadSegment = null;
  }
}
