import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/danmu_models.dart';
import 'danmu_item.dart';
import 'danmu_track_manager.dart';
import 'danmu_renderer.dart';

class DanmuController extends ChangeNotifier {
  DanmuTrackManager? _trackManager;
  final List<DanmuItem> _activeItems = [];
  final List<DanmuComment> _allComments = [];
  bool _enabled = true;
  double _opacity = 1.0;
  final double _fontSize = 16;
  final double _area = 1.0; // 弹幕区域（0.5=上半屏, 1.0=全屏）
  final double _speed = 140; // 像素/秒
  final int _maxVisible = 100; // 同屏最大弹幕数

  // 分片管理
  List<DanmuSegment> _segments = [];
  int _currentSegmentIndex = 0;
  bool _isLoadingSegment = false;

  // 时间 → 弹幕索引的排序映射（二分查找用）
  List<DanmuComment> _sortedByTime = [];

  // 帧调度
  Timer? _frameTimer;

  // 当前播放位置（由 DanmuOverlay 在 Ticker 回调中更新）
  double _currentPosition = 0;
  int _frameCount = 0;
  int _lastLogActiveCount = -1;

  // ---- 公开 API ----

  bool get enabled => _enabled;
  double get opacity => _opacity;
  int get activeCount => _activeItems.length;
  int get totalCount => _allComments.length;
  List<DanmuItem> get activeItems => _activeItems;
  double get currentPosition => _currentPosition;

  void init({required double viewWidth, required double viewHeight}) {
    _trackManager = DanmuTrackManager(
      viewWidth: viewWidth,
      viewHeight: viewHeight * _area,
      itemHeight: _fontSize + 12,
    );
    // ignore: avoid_print
    print('[Danmu] Controller init: view=${viewWidth}x$viewHeight, '
        'maxTracks=${_trackManager!.maxTracks}');
  }

  /// 加载初始弹幕数据
  void loadDanmuData(DanmuData data) {
    _allComments.clear();
    _activeItems.clear();
    _allComments.addAll(data.comments);
    _segments = data.segmentList;
    _currentSegmentIndex = 0;
    _sortedByTime = List.of(_allComments)
      ..sort((a, b) => a.time.compareTo(b.time));
    // ignore: avoid_print
    print('[Danmu] Controller loadDanmuData: count=${data.comments.length}, '
        'segments=${data.segmentList.length}, '
        'sorted=${_sortedByTime.length}, '
        'firstTime=${_sortedByTime.isNotEmpty ? _sortedByTime.first.time : "N/A"}, '
        'lastTime=${_sortedByTime.isNotEmpty ? _sortedByTime.last.time : "N/A"}');
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

  /// 每帧更新：由 DanmuOverlay 的 Ticker 回调驱动
  ///
  /// [positionSeconds] 当前播放位置（秒）
  /// [elapsedSeconds]  当前 Ticker elapsed 时间（秒）
  void updateFrame(double positionSeconds, double elapsedSeconds) {
    if (!_enabled || _trackManager == null) return;

    _currentPosition = positionSeconds;
    _frameCount++;

    // 1. 检查是否需要加载下一分片
    _maybeLoadNextSegment(positionSeconds);

    // 2. 清除已过期的弹幕
    _activeItems.removeWhere(
        (item) => !item.isVisible(elapsedSeconds, _trackManager!.viewWidth));

    // 3. 用二分查找找到当前时间窗口内应发射的弹幕
    _fireNewDanmu(positionSeconds, elapsedSeconds);

    // 定期或状态变化时打印日志
    if (_frameCount % 300 == 0 || _activeItems.length != _lastLogActiveCount) {
      _lastLogActiveCount = _activeItems.length;
      // ignore: avoid_print
      print('[Danmu] updateFrame: pos=${positionSeconds.toStringAsFixed(1)}s, '
          'elapsed=${elapsedSeconds.toStringAsFixed(1)}s, '
          'active=${_activeItems.length}, sorted=${_sortedByTime.length}, '
          'segments=${_segments.length}');
    }

    notifyListeners();
  }

  /// 旧接口兼容：仅更新位置，不触发帧逻辑
  void onPositionUpdate(double positionSeconds) {
    _currentPosition = positionSeconds;
    _maybeLoadNextSegment(positionSeconds);
  }

  void _fireNewDanmu(double position, double elapsed) {
    if (_activeItems.length >= _maxVisible) return;

    // 查找 [position - 0.1, position + 0.1] 范围内的弹幕
    final windowStart = position - 0.1;
    final windowEnd = position + 0.1;

    int lo = 0, hi = _sortedByTime.length;
    while (lo < hi) {
      final mid = (lo + hi) >> 1;
      if (_sortedByTime[mid].time < windowStart) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }

    for (int i = lo; i < _sortedByTime.length; i++) {
      final comment = _sortedByTime[i];
      if (comment.time > windowEnd) break;

      // 避免重复发射
      if (_activeItems.any((a) => a.comment.cid == comment.cid)) continue;

      final item = DanmuItem(comment);
      // 初始位置：屏幕右边缘
      item.x = _trackManager!.viewWidth;
      // 记录发射时的 Ticker elapsed，用于渲染时计算位移
      item.firedAtElapsed = elapsed;
      final allocated = _trackManager!.allocate(item, position, _speed);
      if (allocated >= 0) {
        _activeItems.add(item);
        // ignore: avoid_print
        print('[Danmu] fire: cid=${comment.cid}, '
            'time=${comment.time.toStringAsFixed(1)}s, '
            'pos=${position.toStringAsFixed(1)}s, '
            'track=${(allocated / (_fontSize + 12)).floor()}, '
            'active=${_activeItems.length}');
      }
      if (_activeItems.length >= _maxVisible) break;
    }
  }

  void _maybeLoadNextSegment(double position) {
    if (_isLoadingSegment) return;
    if (_currentSegmentIndex >= _segments.length - 1) return;

    final nextSeg = _segments[_currentSegmentIndex + 1];
    if (position >= nextSeg.segmentStart - 30) {
      // 提前30秒预加载
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

  // 分片加载回调（由 Provider 注入）
  void Function(DanmuSegment segment)? _onNeedLoadSegment;

  void setOnNeedLoadSegment(void Function(DanmuSegment) cb) {
    _onNeedLoadSegment = cb;
  }

  void disposeEngine() {
    _frameTimer?.cancel();
    _activeItems.clear();
    DanmuRenderer.clearCache();
  }
}
