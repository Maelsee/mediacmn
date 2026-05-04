import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:canvas_danmaku/canvas_danmaku.dart' as cd;

import '../provider/danmu_provider.dart';
import '../models/danmu_models.dart';
import '../../core/state/playback_state.dart';

/// 弹幕覆盖层：使用 canvas_danmaku 的 DanmakuScreen 组件
///
/// 架构：
/// - DanmakuScreen 负责渲染（内置 Ticker + Canvas 绘制）
/// - 外部 Ticker 驱动 DanmuController.updateFrame（二分查找发射 + 分片加载）
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

  // 引擎变更监听器（用于 Ticker 重启）
  VoidCallback? _engineListener;
  dynamic _lastEngine;

  // 缓存 DanmakuScreen 实例，避免 Widget 重建导致控制器失效
  cd.DanmakuScreen<DanmuComment>? _cachedScreen;

  // 智能 Ticker 生命周期
  int _idleFrameCount = 0;
  static const int _idleThreshold = 10;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((duration) {
      if (!mounted) return;
      _elapsed = duration.inMilliseconds / 1000.0;

      // 同步播放位置
      final position = ref.read(playbackProvider).position;
      final positionSeconds = position.inMilliseconds / 1000.0;
      ref
          .read(danmuProvider(widget.fileId).notifier)
          .updatePosition(positionSeconds);

      final danmuState = ref.read(danmuProvider(widget.fileId));
      if (!danmuState.enabled) return;

      final engine = ref.read(danmuProvider(widget.fileId).notifier).engine;
      if (engine != null) {
        final playbackSpeed = ref.read(playbackProvider).speed;
        engine.setPlaybackSpeed(playbackSpeed);
        engine.updateFrame(positionSeconds, _elapsed);
      }

      // 智能 Ticker 停止
      if (++_idleFrameCount >= _idleThreshold) {
        _idleFrameCount = 0;
        if (engine != null && !engine.hasActiveItems) {
          _ticker.stop();
        }
      }
    });
    _ticker.start();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final engine = ref.read(danmuProvider(widget.fileId).notifier).engine;
    if (!identical(engine, _lastEngine)) {
      _unbindEngineListener();
      _lastEngine = engine;
      _bindEngineListener(engine);
    }
  }

  /// 绑定引擎监听器：当引擎通知变更时重启 Ticker
  void _bindEngineListener(dynamic engine) {
    if (engine == null) return;
    _engineListener = () {
      if (!_ticker.isActive) {
        _idleFrameCount = 0;
        _ticker.start();
      }
    };
    engine.addListener(_engineListener!);
  }

  void _unbindEngineListener() {
    if (_engineListener != null && _lastEngine != null) {
      _lastEngine!.removeListener(_engineListener!);
      _engineListener = null;
    }
  }

  @override
  void dispose() {
    _unbindEngineListener();
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final danmuState = ref.watch(danmuProvider(widget.fileId));
    final engine = ref.read(danmuProvider(widget.fileId).notifier).engine;

    if (engine == null) {
      _unbindEngineListener();
      _lastEngine = null;
      _cachedScreen = null;
      return const SizedBox.shrink();
    }

    // 引擎实例变化时初始化 + 绑定监听 + 清除缓存
    if (!identical(engine, _lastEngine)) {
      _unbindEngineListener();
      _lastEngine = engine;
      _bindEngineListener(engine);
      _cachedScreen = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _lastViewWidth > 0 && _lastViewHeight > 0) {
          engine.init(viewWidth: _lastViewWidth, viewHeight: _lastViewHeight);
        }
      });
    }

    return IgnorePointer(
      ignoring: !danmuState.enabled,
      child: Opacity(
        opacity: danmuState.enabled ? 1.0 : 0.0,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final w = constraints.maxWidth;
            final h = constraints.maxHeight;
            if (w != _lastViewWidth || h != _lastViewHeight) {
              _lastViewWidth = w;
              _lastViewHeight = h;
              engine.init(viewWidth: w, viewHeight: h);
              // 视口尺寸变化时重建 DanmakuScreen
              _cachedScreen = null;
            }

            if (!danmuState.enabled) {
              _cachedScreen = null;
              return SizedBox(width: w, height: h);
            }

            // 缓存 DanmakuScreen 实例
            _cachedScreen ??= cd.DanmakuScreen<DanmuComment>(
              key: ValueKey('danmaku_${widget.fileId}'),
              createdController: (controller) {
                engine.attachCanvasController(controller);
              },
              option: cd.DanmakuOption(
                fontSize: engine.fontSize,
                area: engine.area,
                opacity: engine.opacity,
                duration: w > 0
                    ? (w / (engine.speed * engine.playbackSpeed))
                        .clamp(3.0, 30.0)
                    : 10.0,
                staticDuration: 5.0,
                strokeWidth: 1.5,
                massiveMode: engine.density >= 0.7,
                safeArea: false,
              ),
            );

            return _cachedScreen!;
          },
        ),
      ),
    );
  }
}
