import '../models/danmu_models.dart';

class DanmuItem {
  final DanmuComment comment;
  // 布局结果（由 TrackManager 计算后填入）
  double x = 0;            // 发射时的初始 x（屏幕右边缘）
  double y = 0;
  double width = 0;
  double height = 0;
  double speed = 0;        // 像素/秒
  double opacity = 1.0;
  bool alive = true;

  /// 发射时的 Ticker elapsed（秒），用于渲染位置计算
  double firedAtElapsed = 0;

  DanmuItem(this.comment);

  /// 当前帧的屏幕 x 坐标
  /// elapsed: 当前 Ticker elapsed 时间
  /// 位置 = 初始x - speed * (当前elapsed - 发射elapsed)
  double screenX(double elapsed) => x - speed * (elapsed - firedAtElapsed);

  /// 是否还在可视区域内
  bool isVisible(double elapsed, double viewWidth) {
    final sx = screenX(elapsed);
    return sx + width > 0 && sx < viewWidth;
  }
}
