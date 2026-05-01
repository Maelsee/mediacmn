import 'dart:collection';
import 'dart:math';
import 'package:flutter/foundation.dart';
import '../models/danmu_models.dart';
import 'danmu_item.dart';
import 'danmu_track_manager.dart';
import 'danmu_renderer.dart';

class DanmuController extends ChangeNotifier {
  DanmuTrackManager? _trackManager;
  final List<DanmuItem> _activeItems = [];
  final Set<int> _activeCids = {}; // O(1) 去重，替代 _activeItems.any() 线性扫描
  final List<DanmuComment> _allComments = [];
  double _opacity = 0.5;
  double _fontSize = 15;
  double _area = 0.3; // 弹幕区域（0.2~1.0）
  double _speed = 130; // 基础弹幕速度（像素/秒）
  double _playbackSpeed = 1.0; // 视频播放倍速，弹幕速度会乘以此值
  final int _maxVisible = 100; // 同屏最大弹幕数

  // 弹幕密度（0.1~1.0，值越大越密集）
  double _density = 1.0;
  double _minGapPx = 200.0; // 密度对应的轨道最小间距
  double _staggerFactor = 0.1; // 密度对应的交错偏移系数

  // 分片管理
  List<DanmuSegment> _segments = [];
  int _currentSegmentIndex = 0;
  bool _isLoadingSegment = false;

  // 时间 → 弹幕索引的排序映射（二分查找用）
  List<DanmuComment> _sortedByTime = [];

  // 均匀发射控制
  static const double _lookAheadSeconds = 3.0; // 提前预取 3 秒
  static const double _minFireGap = 0.3; // 最小发射间隔（秒）
  double _nextFireElapsed = 0; // 下一次允许发射的 elapsed 时间

  // 待发射队列：轨道满时暂存，轨道空出后补发
  final Queue<DanmuItem> _pendingQueue = Queue();
  static const int _maxPendingQueue = 50;

  // 当前播放位置（由 DanmuOverlay 在 Ticker 回调中更新）
  double _currentPosition = 0;
  double _lastPosition = 0; // 上一帧位置，用于 seek 检测
  bool _dirty = true; // 脏标记：有变化才 notifyListeners

  // 缓存原始视口尺寸（用于 settings 变更后重建轨道）
  double _viewWidth = 0;
  double _viewHeight = 0;

  // ---- 公开 API ----

  double get opacity => _opacity;
  double get fontSize => _fontSize;
  double get area => _area;
  double get speed => _speed;
  double get playbackSpeed => _playbackSpeed;
  double get density => _density;
  int get activeCount => _activeItems.length;
  int get totalCount => _allComments.length;
  List<DanmuItem> get activeItems => _activeItems;
  double get currentPosition => _currentPosition;

  /// 实际弹幕滚动速度 = 基础速度 × 播放倍速
  double get _effectiveSpeed => _speed * _playbackSpeed;

  void init({required double viewWidth, required double viewHeight}) {
    _viewWidth = viewWidth;
    _viewHeight = viewHeight;
    _trackManager = DanmuTrackManager(
      viewWidth: viewWidth,
      viewHeight: viewHeight * _area,
      itemHeight: _fontSize + 12,
      minGapPx: _minGapPx,
    );
  }

  /// 加载初始弹幕数据
  void loadDanmuData(DanmuData data) {
    _allComments.clear();
    _activeItems.clear();
    _activeCids.clear();
    _pendingQueue.clear();
    _allComments.addAll(data.comments);
    _segments = data.segmentList;
    _currentSegmentIndex = 0;
    _isLoadingSegment = false;
    _lastPosition = 0; // 重置，防止 seek 检测误触发
    _nextFireElapsed = 0; // 重置发射计时器
    _sortedByTime = List.of(_allComments)
      ..sort((a, b) => a.time.compareTo(b.time));
    notifyListeners();
  }

  /// 追加分片弹幕（merge-insertion，避免全量重排序）
  void appendComments(List<DanmuComment> comments) {
    if (comments.isEmpty) return;
    _allComments.addAll(comments);
    // 新分片内部已排序，用归并代替全量 sort：O(n+k) vs O((n+k) log(n+k))
    final newSorted = List<DanmuComment>.of(comments)
      ..sort((a, b) => a.time.compareTo(b.time));
    _sortedByTime = _mergeSorted(_sortedByTime, newSorted);
  }

  /// 归并两个已排序列表
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

  /// 设置透明度
  void setOpacity(double v) {
    _opacity = v.clamp(0.0, 1.0);
    notifyListeners();
  }

  /// 设置字体大小（需要重新初始化轨道）
  void setFontSize(double v) {
    _fontSize = v.clamp(12.0, 32.0);
    _reinitTrackManager();
    notifyListeners();
  }

  /// 设置弹幕显示区域（0.2~1.0）
  void setArea(double v) {
    _area = v.clamp(0.2, 1.0);
    _reinitTrackManager();
    notifyListeners();
  }

  /// 设置弹幕基础速度（像素/秒）
  void setSpeed(double v) {
    _speed = v.clamp(60.0, 300.0);
    notifyListeners();
  }

  /// 设置视频播放倍速，弹幕速度会自动跟随
  void setPlaybackSpeed(double v) {
    _playbackSpeed = v.clamp(0.25, 4.0);
  }

  /// 设置弹幕密度（0.1~1.0）
  /// 1.0 = 最密集（minGapPx=300, stagger=0.1）
  /// 0.1 = 最稀疏（minGapPx=700, stagger=0.9）
  void setDensity(double v) {
    _density = v.clamp(0.1, 1.0);
    _minGapPx = 700.0 - (_density - 0.1) * 500.0 / 0.9;
    _staggerFactor = 0.9 - (_density - 0.1) * 0.8 / 0.9;
    _reinitTrackManager();
    notifyListeners();
  }

  /// 0.1（10%）→ minGapPx = 700 - 0 = 700, stagger = 0.9 ✓
  /// 1.0（100%）→ minGapPx = 700 - 500 = 200, stagger = 0.9 - 0.8 = 0.1 ✓
  /// 0.55（55%）→ minGapPx = 500, stagger = 0.5 ✓

  /// 使用缓存的 viewWidth/viewHeight 重建轨道管理器
  void _reinitTrackManager() {
    if (_viewWidth == 0 || _viewHeight == 0) return;
    _trackManager = DanmuTrackManager(
      viewWidth: _viewWidth,
      viewHeight: _viewHeight * _area,
      itemHeight: _fontSize + 12,
      minGapPx: _minGapPx,
    );
  }

  /// 每帧更新：由 DanmuOverlay 的 Ticker 回调驱动
  ///
  /// [positionSeconds] 当前播放位置（秒）
  /// [elapsedSeconds]  当前 Ticker elapsed 时间（秒）
  void updateFrame(double positionSeconds, double elapsedSeconds) {
    if (_trackManager == null) return;

    _currentPosition = positionSeconds;
    _dirty = false;

    // 1. Seek 检测：位置跳变超过 1 秒时清除旧弹幕
    final positionDelta = (positionSeconds - _lastPosition).abs();
    if (positionDelta > 1.0 && _lastPosition != 0) {
      _activeItems.clear();
      _activeCids.clear();
      _pendingQueue.clear();
      _trackManager!.reset();
      _nextFireElapsed = 0;
      _dirty = true;
    }
    _lastPosition = positionSeconds;

    // 2. 检查是否需要加载下一分片
    _maybeLoadNextSegment(positionSeconds);

    // 3. 清除已过期的弹幕（单次遍历压缩）
    final prevCount = _activeItems.length;
    _removeExpiredItems(elapsedSeconds);
    if (_activeItems.length != prevCount) _dirty = true;

    // 4. 先处理待发射队列（轨道空出后补发之前被阻塞的弹幕）
    final prevCount2 = _activeItems.length;
    _processPendingQueue(elapsedSeconds);
    if (_activeItems.length != prevCount2) _dirty = true;

    // 5. 用二分查找找到当前时间窗口内应发射的弹幕
    final prevCount3 = _activeItems.length;
    _fireNewDanmu(positionSeconds, elapsedSeconds);
    if (_activeItems.length != prevCount3) _dirty = true;

    if (_dirty) notifyListeners();
  }

  /// 移除已过期的弹幕，同步维护 _activeCids（单次遍历压缩，O(n)）
  void _removeExpiredItems(double elapsed) {
    final viewWidth = _trackManager!.viewWidth;
    int writeIdx = 0;
    for (int i = 0; i < _activeItems.length; i++) {
      final item = _activeItems[i];
      if (item.isVisible(elapsed, viewWidth)) {
        _activeItems[writeIdx++] = item;
      } else {
        _activeCids.remove(item.comment.cid);
      }
    }
    if (writeIdx < _activeItems.length) {
      _activeItems.length = writeIdx;
    }
  }

  /// 旧接口兼容：仅更新位置，不触发帧逻辑
  void onPositionUpdate(double positionSeconds) {
    _currentPosition = positionSeconds;
    _maybeLoadNextSegment(positionSeconds);
  }

  final _random = Random();

  /// 处理待发射队列：轨道空出后补发之前被阻塞的弹幕
  void _processPendingQueue(double elapsed) {
    if (_pendingQueue.isEmpty) return;
    if (_activeItems.length >= _maxVisible) return;

    final position = _currentPosition;
    final effectiveSpeed = _effectiveSpeed;

    // 从队列头部取出，尝试分配轨道
    int fired = 0;
    while (_pendingQueue.isNotEmpty &&
        _activeItems.length < _maxVisible &&
        fired < 3) {
      // 每帧最多补发 3 条，避免瞬间涌入
      final item = _pendingQueue.removeFirst();
      // 重新设置发射时间（队列等待期间 elapsed 已变化）
      item.firedAtElapsed = elapsed;
      item.firedAtPosition = position;
      final allocated = _trackManager!.allocate(item, position, effectiveSpeed);
      if (allocated >= 0) {
        _activeItems.add(item);
        _activeCids.add(item.comment.cid);
        fired++;
      } else {
        // 轨道仍然满，放回队列头部，等下一帧再试
        _pendingQueue.addFirst(item);
        break;
      }
    }
  }

  void _fireNewDanmu(double position, double elapsed) {
    if (_activeItems.length >= _maxVisible) return;
    if (elapsed < _nextFireElapsed) return; // 速率控制：未到发射时间

    // 提前预取 3 秒内的弹幕，而非仅 ±0.1s
    final windowEnd = position + _lookAheadSeconds;

    int lo = 0, hi = _sortedByTime.length;
    while (lo < hi) {
      final mid = (lo + hi) >> 1;
      if (_sortedByTime[mid].time < position) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }

    final effectiveSpeed = _effectiveSpeed;
    int consecutiveFails = 0;

    for (int i = lo; i < _sortedByTime.length; i++) {
      final comment = _sortedByTime[i];
      if (comment.time > windowEnd) break;

      if (_activeCids.contains(comment.cid)) continue;

      final item = DanmuItem(comment);
      final staggerOffset =
          _random.nextDouble() * _trackManager!.viewWidth * _staggerFactor;
      item.x = _trackManager!.viewWidth + staggerOffset;
      item.firedAtElapsed = elapsed;
      item.firedAtPosition = position;
      final allocated = _trackManager!.allocate(item, position, effectiveSpeed);
      if (allocated >= 0) {
        _activeItems.add(item);
        _activeCids.add(comment.cid);
        _nextFireElapsed = elapsed + _minFireGap;
        consecutiveFails = 0;
      } else {
        if (_pendingQueue.length < _maxPendingQueue) {
          _pendingQueue.add(item);
        }
        if (++consecutiveFails >= 3) break; // 连续 3 条分配失败，轨道已满
      }
      if (_activeItems.length >= _maxVisible) break;
      if (elapsed < _nextFireElapsed) break;
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

  /// 重置分片加载状态（防止网络失败后卡在 loading）
  void resetSegmentLoading() {
    _isLoadingSegment = false;
  }

  // 分片加载回调（由 Provider 注入）
  void Function(DanmuSegment segment)? _onNeedLoadSegment;

  void setOnNeedLoadSegment(void Function(DanmuSegment) cb) {
    _onNeedLoadSegment = cb;
  }

  void disposeEngine() {
    _activeItems.clear();
    _activeCids.clear();
    _pendingQueue.clear();
    _allComments.clear();
    _sortedByTime.clear();
    _segments.clear();
    _currentSegmentIndex = 0;
    _isLoadingSegment = false;
    _nextFireElapsed = 0;
    _onNeedLoadSegment = null;
    _trackManager = null;
    DanmuRenderer.clearCache();
  }
}
