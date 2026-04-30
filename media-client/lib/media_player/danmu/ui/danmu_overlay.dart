import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../provider/danmu_provider.dart';
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

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((duration) {
      if (!mounted) return;
      setState(() => _elapsed = duration.inMilliseconds / 1000.0);
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
    final engine = danmuState.enabled
        ? ref.read(danmuProvider(widget.fileId).notifier).engine
        : null;
    if (engine == null || !danmuState.enabled) return const SizedBox.shrink();

    // 订阅播放器位置更新
    final position = ref.watch(playbackProvider).position;
    final positionSeconds = position.inMilliseconds / 1000.0;
    engine.onPositionUpdate(positionSeconds);

    return IgnorePointer(
      child: Opacity(
        opacity: engine.opacity,
        child: LayoutBuilder(
          builder: (context, constraints) {
            engine.init(
              viewWidth: constraints.maxWidth,
              viewHeight: constraints.maxHeight,
            );
            return CustomPaint(
              size: Size(constraints.maxWidth, constraints.maxHeight),
              painter: DanmuRenderer(
                items: engine.activeItems,
                elapsed: _elapsed,
                viewWidth: constraints.maxWidth,
                viewHeight: constraints.maxHeight,
              ),
            );
          },
        ),
      ),
    );
  }
}
