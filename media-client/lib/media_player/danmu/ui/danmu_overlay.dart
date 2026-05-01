import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../provider/danmu_provider.dart';
import '../engine/danmu_controller.dart';
import '../engine/danmu_renderer.dart';
import '../../core/state/playback_state.dart';

class DanmuOverlay extends ConsumerStatefulWidget {
  final String fileId;

  const DanmuOverlay({super.key, required this.fileId});

  @override
  ConsumerState<DanmuOverlay> createState() => _DanmuOverlayState();
}

class _DanmuOverlayState extends ConsumerState<DanmuOverlay>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  double _elapsed = 0;
  double _lastViewWidth = 0;
  double _lastViewHeight = 0;
  DanmuController? _lastEngine;
  bool _needsInit = false;

  @override
  void initState() {
    super.initState();
    // ignore: avoid_print
    print('[Danmu] Overlay initState, fileId=${widget.fileId}');
    _ticker = createTicker((duration) {
      if (!mounted) return;
      _elapsed = duration.inMilliseconds / 1000.0;

      // 在 ticker 回调中更新引擎（build 外部，安全调用 notifyListeners）
      final danmuState = ref.read(danmuProvider(widget.fileId));
      if (!danmuState.enabled) return; // 弹幕关闭时不触发 setState，节省 CPU

      final engine =
          ref.read(danmuProvider(widget.fileId).notifier).engine;
      if (engine != null) {
        final position = ref.read(playbackProvider).position;
        final positionSeconds = position.inMilliseconds / 1000.0;
        engine.updateFrame(positionSeconds, _elapsed);
      }

      setState(() {});
    });
    _ticker.start();
  }

  @override
  void dispose() {
    // ignore: avoid_print
    print('[Danmu] Overlay dispose, fileId=${widget.fileId}');
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final danmuState = ref.watch(danmuProvider(widget.fileId));
    final engine = danmuState.enabled
        ? ref.read(danmuProvider(widget.fileId).notifier).engine
        : null;

    if (engine == null || !danmuState.enabled) {
      _lastEngine = null;
      return const SizedBox.shrink();
    }

    // 引擎实例变化时（开关切换/换集），强制重新初始化轨道管理器
    if (!identical(engine, _lastEngine)) {
      _lastEngine = engine;
      _needsInit = true;
    }

    return IgnorePointer(
      child: Opacity(
        opacity: engine.opacity,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final w = constraints.maxWidth;
            final h = constraints.maxHeight;
            // 尺寸变化或引擎实例变化时重新初始化轨道管理器
            if (_needsInit || w != _lastViewWidth || h != _lastViewHeight) {
              _lastViewWidth = w;
              _lastViewHeight = h;
              _needsInit = false;
              engine.init(viewWidth: w, viewHeight: h);
              // ignore: avoid_print
              print('[Danmu] Overlay init tracks: ${w}x$h');
            }
            return CustomPaint(
              size: Size(w, h),
              painter: DanmuRenderer(
                items: engine.activeItems,
                elapsed: _elapsed,
                viewWidth: w,
                viewHeight: h,
              ),
            );
          },
        ),
      ),
    );
  }
}
