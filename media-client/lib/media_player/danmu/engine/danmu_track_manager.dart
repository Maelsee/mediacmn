import 'danmu_item.dart';

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
    // ignore: avoid_print
    print('[Danmu] TrackManager: view=${viewWidth}x$viewHeight, '
        'maxTracks=$maxTracks, itemHeight=$itemHeight');
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
    // ignore: avoid_print
    print('[Danmu] allocate FAIL: all $maxTracks tracks busy, discarding');
    return -1; // 所有轨道满载，丢弃
  }

  void reset() {
    for (int i = 0; i < maxTracks; i++) {
      _trackFreeAt[i] = 0;
    }
  }
}
