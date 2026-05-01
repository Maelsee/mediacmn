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

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((duration) {
      if (!mounted) return;
      _elapsed = duration.inMilliseconds / 1000.0;

      // 弹幕关闭时不更新引擎，节省 CPU
      final danmuState = ref.read(danmuProvider(widget.fileId));
      if (!danmuState.enabled) return;

      final engine =
          ref.read(danmuProvider(widget.fileId).notifier).engine;
      if (engine != null) {
        final position = ref.read(playbackProvider).position;
        final playbackSpeed = ref.read(playbackProvider).speed;
        final positionSeconds = position.inMilliseconds / 1000.0;
        // 同步视频播放倍速到弹幕引擎
        engine.setPlaybackSpeed(playbackSpeed);
        engine.updateFrame(positionSeconds, _elapsed);
      }

      setState(() {});
    });
    _ticker.start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final danmuState = ref.watch(danmuProvider(widget.fileId));
    final engine = ref.read(danmuProvider(widget.fileId).notifier).engine;

    // 引擎不存在时返回空（首次进入或无匹配弹幕源）
    if (engine == null) {
      _lastEngine = null;
      return const SizedBox.shrink();
    }

    // 引擎实例变化时（首次匹配/换集），需要初始化轨道管理器
    if (!identical(engine, _lastEngine)) {
      _lastEngine = engine;
      // 新引擎需要通过 LayoutBuilder 初始化
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _lastViewWidth > 0 && _lastViewHeight > 0) {
          engine.init(viewWidth: _lastViewWidth, viewHeight: _lastViewHeight);
        }
      });
    }

    // 始终保持挂载，通过 opacity 控制可见性。
    // 关闭弹幕时 opacity=0 + IgnorePointer，避免重建 widget 树导致引擎丢失。
    return IgnorePointer(
      ignoring: !danmuState.enabled,
      child: Opacity(
        opacity: danmuState.enabled ? engine.opacity : 0.0,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final w = constraints.maxWidth;
            final h = constraints.maxHeight;
            // 尺寸变化时重新初始化轨道管理器
            if (w != _lastViewWidth || h != _lastViewHeight) {
              _lastViewWidth = w;
              _lastViewHeight = h;
              engine.init(viewWidth: w, viewHeight: h);
            }
            // 每帧只触发 CustomPaint 重绘，不重建 LayoutBuilder
            return ListenableBuilder(
              listenable: engine,
              builder: (context, _) {
                return CustomPaint(
                  size: Size(w, h),
                  painter: danmuState.enabled
                      ? DanmuRenderer(
                          items: engine.activeItems,
                          elapsed: _elapsed,
                          viewWidth: w,
                          viewHeight: h,
                          fontSize: engine.fontSize,
                        )
                      : null, // 关闭时不绘制
                );
              },
            );
          },
        ),
      ),
    );
  }
}
