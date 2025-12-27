/// 播放器配置常量
///
/// 集中管理播放器的各种配置参数，
/// 便于调整和优化
class PlayerConfig {
  // 控件自动隐藏时间
  static const Duration autoHideControlsDelay = Duration(seconds: 3);

  // 进度更新节流时间（毫秒）
  static const int positionUpdateThrottleMs = 200;

  // 位置跳跃阈值（毫秒），超过此值立即更新
  static const int positionJumpThresholdMs = 1000;

  // 音量步长
  static const double volumeStep = 0.1;

  // 快进快退时间
  static const Duration seekStep = Duration(seconds: 10);

  // 播放倍速选项
  static const List<double> playbackRates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];

  // 缓冲超时时间
  static const Duration bufferingTimeout = Duration(seconds: 10);

  // 双击手势区域划分
  static const double doubleTapAreaRatio = 0.5;

  // 滑动手势灵敏度
  static const double gestureSensitivity = 0.5;

  // 音量滑块宽度
  static const double volumeSliderWidth = 80.0;

  // 控件按钮大小
  static const double controlButtonSize = 24.0;

  // 进度条高度
  static const double progressBarHeight = 4.0;

  // 缓冲指示器大小
  static const double bufferingIndicatorSize = 42.0;
}

/// 手势配置
class GestureConfig {
  // 双击时间阈值（毫秒）
  static const int doubleTapTimeThreshold = 300;

  // 长按时间阈值（毫秒）
  static const int longPressTimeThreshold = 500;

  // 滑动最小距离
  static const double minSwipeDistance = 20.0;

  // 滑动最大时间（毫秒）
  static const int maxSwipeTime = 500;

  // 水平滑动阈值
  static const double horizontalSwipeThreshold = 50.0;

  // 垂直滑动阈值
  static const double verticalSwipeThreshold = 50.0;
}

/// 性能优化配置
class PerformanceConfig {
  // 最大同时处理的播放器实例数
  static const int maxConcurrentPlayers = 3;

  // 预加载下一个视频的提前时间（秒）
  static const int preloadNextVideoSeconds = 30;

  // 内存缓存大小（MB）
  static const int memoryCacheSizeMB = 100;

  // 磁盘缓存大小（MB）
  static const int diskCacheSizeMB = 500;

  // 网络请求超时时间
  static const Duration networkTimeout = Duration(seconds: 30);

  // 重试次数
  static const int maxRetryCount = 3;

  // 重试间隔
  static const Duration retryInterval = Duration(seconds: 2);
}
