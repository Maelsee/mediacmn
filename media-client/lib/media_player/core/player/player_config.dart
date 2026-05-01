/// 播放器配置。
///
/// 用于统一控制默认音量、倍速、进度上报周期等行为。
class PlayerConfig {
  /// 统一的倍速选项列表（移动端与桌面端共用）。
  static const kSpeedOptions = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];
  /// 快进/快退步长。
  final Duration seekStep;

  /// 播放进度上报到后端的周期。
  final Duration progressReportInterval;

  /// 初始音量（0~100）。
  final double initialVolume;

  /// 初始倍速。
  final double initialSpeed;

  /// 启用硬件加速解码。
  final bool enableHardwareAcceleration;

  /// 最大缓冲区大小（MB）。
  final int maxBufferSize;

  /// 高帧率视频优化阈值。
  final double highFrameRateThreshold;

  /// 4K视频优化开关。
  final bool enable4KOptimization;

  const PlayerConfig({
    this.seekStep = const Duration(seconds: 10),
    this.progressReportInterval = const Duration(seconds: 10),
    this.initialVolume = 80,
    this.initialSpeed = 1.0,
    this.enableHardwareAcceleration = true,
    this.maxBufferSize = 128,
    this.highFrameRateThreshold = 48.0,
    this.enable4KOptimization = true,
  });
}
