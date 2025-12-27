import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

/// 视频控制器服务
///
/// 管理 media_kit_video 的 VideoController。
/// 处理硬件加速配置和视频渲染控制。
class VideoControllerService {
  VideoController? _controller;
  bool _hardwareAccelerationEnabled = true;

  /// 获取 VideoController
  VideoController? get controller => _controller;

  /// 获取硬件加速状态
  bool get isHardwareAccelerationEnabled => _hardwareAccelerationEnabled;

  /// 初始化控制器
  void initialize(Player player, {bool enableHardwareAcceleration = true}) {
    _hardwareAccelerationEnabled = enableHardwareAcceleration;
    _createController(player);
  }

  /// 重新创建控制器（用于切换硬件加速配置）
  void reinitialize(Player player) {
    _createController(player);
  }

  void _createController(Player player) {
    _controller = VideoController(
      player,
      configuration: VideoControllerConfiguration(
        enableHardwareAcceleration: _hardwareAccelerationEnabled,
        // Android 模拟器兼容性配置
        androidAttachSurfaceAfterVideoParameters: false,
      ),
    );
  }

  /// 设置硬件加速
  void setHardwareAcceleration(Player player, bool enable) {
    if (_hardwareAccelerationEnabled != enable) {
      _hardwareAccelerationEnabled = enable;
      reinitialize(player);
    }
  }
}
