import '../models/danmu_models.dart';

class DanmuItem {
  final DanmuComment comment;
  // 布局结果（由 TrackManager 计算后填入）
  double x = 0;
  double y = 0;
  double width = 0;
  double height = 0;
  double speed = 0;        // 像素/秒
  double opacity = 1.0;
  bool alive = true;

  DanmuItem(this.comment);

  /// 当前帧的屏幕 x 坐标
  double screenX(double elapsed) => x - speed * elapsed;

  /// 是否还在可视区域内
  bool isVisible(double elapsed, double viewWidth) {
    final sx = screenX(elapsed);
    return sx + width > 0 && sx < viewWidth;
  }
}
