import 'package:flutter/material.dart';

/// 播放器加载/缓冲覆盖层。
///
/// 设计目标：转圈动画始终保持匀速转动，避免将动画进度绑定到跳变的缓冲进度上导致“卡顿感”。
class LoadingOverlay extends StatefulWidget {
  /// 缓冲/加载进度（0~1），可为空。
  final double? progress;

  const LoadingOverlay({super.key, this.progress});

  @override
  State<LoadingOverlay> createState() => _LoadingOverlayState();
}

class _LoadingOverlayState extends State<LoadingOverlay>
    with SingleTickerProviderStateMixin {
  /// 百分比显示的平滑进度（0~1）。
  double _displayProgress = 0;

  /// 平滑动画控制器。
  late final AnimationController _progressController;

  /// 平滑动画。
  Animation<double>? _progressAnimation;

  @override
  void initState() {
    super.initState();
    _progressController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 250),
    );
    _syncProgress(animated: false);
  }

  @override
  void didUpdateWidget(covariant LoadingOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncProgress(animated: true);
  }

  @override
  void dispose() {
    _progressAnimation?.removeListener(_onProgressTick);
    _progressController.dispose();
    super.dispose();
  }

  /// 将外部 progress 同步为平滑显示值。
  void _syncProgress({required bool animated}) {
    final raw = widget.progress;
    if (raw == null || raw <= 0) {
      _progressController.stop();
      return;
    }

    final target = raw.clamp(0.0, 1.0);
    if (!animated) {
      setState(() => _displayProgress = target);
      return;
    }

    if (target == _displayProgress) return;

    if (target < _displayProgress) {
      setState(() => _displayProgress = target);
      return;
    }

    _progressAnimation?.removeListener(_onProgressTick);
    _progressController.stop();

    _progressAnimation = Tween<double>(
      begin: _displayProgress,
      end: target,
    ).animate(
      CurvedAnimation(
        parent: _progressController,
        curve: Curves.easeOutCubic,
      ),
    )..addListener(_onProgressTick);

    _progressController
      ..reset()
      ..forward();
  }

  /// 平滑动画逐帧回调。
  void _onProgressTick() {
    final value = _progressAnimation?.value;
    if (value == null) return;
    setState(() => _displayProgress = value);
  }

  @override
  Widget build(BuildContext context) {
    final hasProgress = widget.progress != null && widget.progress! > 0;
    final percent = hasProgress ? (_displayProgress * 100).toInt() : null;

    return ColoredBox(
      color: Colors.black54,
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.black87,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                ),
              ),
              const SizedBox(width: 12),
              Text(
                percent != null ? '加载中 $percent%' : '加载中…',
                style: const TextStyle(color: Colors.white),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
