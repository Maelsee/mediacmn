/// 播放器配置。
///
/// 用于统一控制默认音量、倍速、进度上报周期等行为。
class PlayerConfig {
  /// 快进/快退步长。
  final Duration seekStep;

  /// 播放进度上报到后端的周期。
  final Duration progressReportInterval;

  /// 初始音量（0~100）。
  final double initialVolume;

  /// 初始倍速。
  final double initialSpeed;

  const PlayerConfig({
    this.seekStep = const Duration(seconds: 10),
    this.progressReportInterval = const Duration(seconds: 10),
    this.initialVolume = 80,
    this.initialSpeed = 1.0,
  });
}
