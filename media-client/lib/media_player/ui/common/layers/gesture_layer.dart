import 'dart:async';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:screen_brightness/screen_brightness.dart';
import '../../../logic/player_notifier.dart';
import '../../../utils/formatters.dart';

/// 手势控制层
///
/// 处理播放器上的所有手势操作：
/// - 单击：切换 UI 显示/隐藏
/// - 双击：播放/暂停或快进/快退
/// - 水平滑动：调整播放进度
/// - 垂直滑动：调整音量/亮度
class GestureLayer extends ConsumerStatefulWidget {
  final VoidCallback onTap;
  final VoidCallback onActivity;

  const GestureLayer({
    super.key,
    required this.onTap,
    required this.onActivity,
  });

  @override
  ConsumerState<GestureLayer> createState() => _GestureLayerState();
}

class _GestureLayerState extends ConsumerState<GestureLayer> {
  // 进度调节相关
  bool _isSeekSliding = false;
  Duration? _seekStartPosition;
  Duration? _seekTargetPosition;
  double _seekAccumulatedDelta = 0;
  static const double _seekSensitivity = 2.0;

  // 音量/亮度调节相关
  bool _isVerticalSliding = false;
  bool _isVolumeControl = false; // true: 音量, false: 亮度
  double _verticalStartValue = 0.0;
  double _verticalCurrentValue = 0.0;
  double _verticalAccumulatedDelta = 0;

  int? _activePointerId;
  Offset? _pointerDownPosition;
  bool _pointerMoved = false;

  @override
  void dispose() {
    _tapResetTimer?.cancel();
    super.dispose();
  }

  Timer? _tapResetTimer;
  DateTime? _lastTapUpTime;
  Offset? _lastTapUpPosition;
  static const Duration _doubleTapMaxInterval = Duration(milliseconds: 280);

  void _onPointerDown(PointerDownEvent event) {
    if (_activePointerId != null) return;
    _activePointerId = event.pointer;
    _pointerDownPosition = event.localPosition;
    _pointerMoved = false;
  }

  void _onPointerMove(PointerMoveEvent event) {
    if (event.pointer != _activePointerId) return;
    final start = _pointerDownPosition;
    if (start == null) return;
    if (_pointerMoved) return;
    if ((event.localPosition - start).distance > kTouchSlop) {
      _pointerMoved = true;
      _tapResetTimer?.cancel();
      _tapResetTimer = null;
      _lastTapUpTime = null;
      _lastTapUpPosition = null;
    }
  }

  void _onPointerCancel(PointerCancelEvent event) {
    if (event.pointer != _activePointerId) return;
    _activePointerId = null;
    _pointerDownPosition = null;
    _pointerMoved = false;
  }

  void _onPointerUp(PointerUpEvent event, BoxConstraints constraints) {
    if (event.pointer != _activePointerId) return;
    _activePointerId = null;
    _pointerDownPosition = null;

    if (_pointerMoved) {
      _pointerMoved = false;
      return;
    }
    _pointerMoved = false;

    final now = DateTime.now();
    final lastTime = _lastTapUpTime;
    final lastPos = _lastTapUpPosition;
    final currentPos = event.localPosition;

    final isDoubleTap = lastTime != null &&
        now.difference(lastTime) <= _doubleTapMaxInterval &&
        lastPos != null &&
        (currentPos - lastPos).distance <= kTouchSlop * 2;

    if (isDoubleTap) {
      _tapResetTimer?.cancel();
      _tapResetTimer = null;
      _lastTapUpTime = null;
      _lastTapUpPosition = null;
      _handleDoubleTap(currentPos, constraints);
      return;
    }

    widget.onTap();
    _lastTapUpTime = now;
    _lastTapUpPosition = currentPos;
    _tapResetTimer?.cancel();
    _tapResetTimer = Timer(_doubleTapMaxInterval, () {
      if (!mounted) return;
      _lastTapUpTime = null;
      _lastTapUpPosition = null;
      _tapResetTimer = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return Stack(
          children: [
            // 手势检测区域
            Listener(
              behavior: HitTestBehavior.opaque,
              onPointerDown: _onPointerDown,
              onPointerMove: _onPointerMove,
              onPointerUp: (event) => _onPointerUp(event, constraints),
              onPointerCancel: _onPointerCancel,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onHorizontalDragStart: _handleHorizontalDragStart,
                onHorizontalDragUpdate: (details) =>
                    _handleHorizontalDragUpdate(details),
                onHorizontalDragEnd: _handleHorizontalDragEnd,
                onVerticalDragStart: (details) =>
                    _handleVerticalDragStart(details, constraints),
                onVerticalDragUpdate: _handleVerticalDragUpdate,
                onVerticalDragEnd: _handleVerticalDragEnd,
                child: const SizedBox.expand(),
              ),
            ),

            // 进度调节提示
            if (_isSeekSliding && _seekTargetPosition != null)
              Center(
                child: _buildSeekOverlay(),
              ),

            // 音量/亮度调节提示
            if (_isVerticalSliding)
              Center(
                child: _buildVerticalOverlay(),
              ),
          ],
        );
      },
    );
  }

  // ==================== 手势处理逻辑 ====================
  void _handleDoubleTap(Offset position, BoxConstraints constraints) {
    widget.onActivity();
    final width = constraints.maxWidth;
    final dx = position.dx;
    final notifier = ref.read(playerProvider.notifier);
    final state = ref.read(playerProvider);

    if (dx < width * 0.3) {
      // 左侧双击：快退 10s
      final newPos = state.position - const Duration(seconds: 10);
      notifier.seek(newPos < Duration.zero ? Duration.zero : newPos);
    } else if (dx > width * 0.7) {
      // 右侧双击：快进 10s
      final newPos = state.position + const Duration(seconds: 10);
      final duration = state.duration;
      notifier.seek(newPos > duration ? duration : newPos);
    } else {
      // 中间双击：播放/暂停
      notifier.toggle();
    }
  }

  void _handleHorizontalDragStart(DragStartDetails details) {
    widget.onActivity();
    final state = ref.read(playerProvider);
    setState(() {
      _isSeekSliding = true;
      _seekStartPosition = state.position;
      _seekAccumulatedDelta = 0;
    });
  }

  void _handleHorizontalDragUpdate(DragUpdateDetails details) {
    widget.onActivity();
    if (!_isSeekSliding || _seekStartPosition == null) return;

    _seekAccumulatedDelta += details.primaryDelta!;
    final state = ref.read(playerProvider);
    final totalSeconds = state.duration.inSeconds;
    if (totalSeconds == 0) return;

    final secondsToAdd = (_seekAccumulatedDelta * _seekSensitivity).toInt();
    final newSeconds =
        (_seekStartPosition!.inSeconds + secondsToAdd).clamp(0, totalSeconds);

    setState(() {
      _seekTargetPosition = Duration(seconds: newSeconds);
    });
  }

  void _handleHorizontalDragEnd(DragEndDetails details) {
    widget.onActivity();
    if (_seekTargetPosition != null) {
      ref.read(playerProvider.notifier).seek(_seekTargetPosition!);
    }
    setState(() {
      _isSeekSliding = false;
      _seekTargetPosition = null;
      _seekStartPosition = null;
    });
  }

  Future<void> _handleVerticalDragStart(
      DragStartDetails details, BoxConstraints constraints) async {
    widget.onActivity();
    setState(() {
      _isVerticalSliding = true;
      _verticalAccumulatedDelta = 0;
    });

    // 右半屏调节音量，左半屏调节亮度
    if (details.globalPosition.dx > constraints.maxWidth * 0.5) {
      _isVolumeControl = true;
      _verticalStartValue = ref.read(playerProvider).volume / 100.0;
    } else {
      _isVolumeControl = false;
      try {
        _verticalStartValue = await ScreenBrightness().application;
      } catch (_) {
        _verticalStartValue = 0.5;
      }
    }
    _verticalCurrentValue = _verticalStartValue;
  }

  void _handleVerticalDragUpdate(DragUpdateDetails details) {
    widget.onActivity();
    if (!_isVerticalSliding) return;

    // 向上滑为负，需转为正向增加
    _verticalAccumulatedDelta -= details.primaryDelta!;

    // 灵敏度调节
    final change = _verticalAccumulatedDelta * 0.005;
    final newValue = (_verticalStartValue + change).clamp(0.0, 1.0);

    setState(() {
      _verticalCurrentValue = newValue;
    });

    if (_isVolumeControl) {
      ref.read(playerProvider.notifier).setVolume(newValue * 100);
    } else {
      try {
        ScreenBrightness().setApplicationScreenBrightness(newValue);
      } catch (_) {}
    }
  }

  void _handleVerticalDragEnd(DragEndDetails details) {
    widget.onActivity();
    setState(() {
      _isVerticalSliding = false;
    });
  }

  // ==================== UI 构建 helper ====================

  Widget _buildSeekOverlay() {
    final state = ref.read(playerProvider);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '${formatDuration(_seekTargetPosition!)} / ${formatDuration(state.duration)}',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          const Text('滑动快进/快退', style: TextStyle(color: Colors.white70)),
        ],
      ),
    );
  }

  Widget _buildVerticalOverlay() {
    final icon = _isVolumeControl
        ? (_verticalCurrentValue == 0
            ? Icons.volume_off
            : (_verticalCurrentValue < 0.5
                ? Icons.volume_down
                : Icons.volume_up))
        : (_verticalCurrentValue < 0.3
            ? Icons.brightness_low
            : (_verticalCurrentValue < 0.7
                ? Icons.brightness_medium
                : Icons.brightness_high));

    return Container(
      width: 120,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.white, size: 48),
          const SizedBox(height: 16),
          LinearProgressIndicator(
            value: _verticalCurrentValue,
            backgroundColor: Colors.white24,
            valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
          ),
          const SizedBox(height: 8),
          Text(
            '${(_verticalCurrentValue * 100).toInt()}%',
            style: const TextStyle(color: Colors.white, fontSize: 16),
          ),
        ],
      ),
    );
  }
}
