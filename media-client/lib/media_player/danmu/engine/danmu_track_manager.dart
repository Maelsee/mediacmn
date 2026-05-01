import 'danmu_item.dart';

/// 轨道管理器：将弹幕分配到不重叠的水平轨道
class DanmuTrackManager {
  final double viewWidth;
  final double viewHeight;
  final double itemHeight; // 单行弹幕高度
  final int maxTracks;

  /// 同轨道前后弹幕最小间距（像素），只需保证文字不重叠
  static const double minGapPx = 200.0;

  // 每条轨道记录：该轨道允许下一条弹幕发射的最早时间
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

  /// 为弹幕分配轨道，返回 y 坐标，-1 表示无可用轨道
  double allocate(DanmuItem item, double currentTime, double speed) {
    // 仅需等待前一条弹幕移出 minGapPx 距离，而非整个屏幕宽度
    final minInterval = minGapPx / speed;

    for (int i = 0; i < maxTracks; i++) {
      if (currentTime >= _trackFreeAt[i]) {
        _trackFreeAt[i] = currentTime + minInterval;
        item.y = _trackY[i];
        item.speed = speed;
        return _trackY[i];
      }
    }
    return -1; // 所有轨道满载（由调用方入队等待）
  }

  void reset() {
    for (int i = 0; i < maxTracks; i++) {
      _trackFreeAt[i] = 0;
    }
  }
}
