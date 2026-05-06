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
/// - Ticker 在弹幕开启期间持续运行，由 enabled 状态控制启停
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

  // 缓存 DanmakuScreen 实例，避免 Widget 重建导致控制器失效
  cd.DanmakuScreen<DanmuComment>? _cachedScreen;

  // 记录上一次的引擎版本，用于检测引擎变更并清除缓存
  int _lastEngineVersion = -1;
  bool _tickerLogOnce = false;
  bool _autoEnableChecked = false;

  @override
  void initState() {
    super.initState();
    print('[DanmuOverlay] initState fileId=${widget.fileId}');
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

      // 首帧日志（无论 enabled 与否）
      if (!_tickerLogOnce) {
        _tickerLogOnce = true;
        print('[DanmuOverlay] Ticker 首帧: enabled=${danmuState.enabled}, '
            'pos=${positionSeconds.toStringAsFixed(1)}, '
            'sources=${danmuState.sources.length}, '
            'danmuData=${danmuState.danmuData != null}');
      }

      if (!danmuState.enabled) return;

      final engine = ref.read(danmuProvider(widget.fileId).notifier).engine;
      if (engine != null) {
        final playbackSpeed = ref.read(playbackProvider).speed;
        engine.setPlaybackSpeed(playbackSpeed);
        engine.updateFrame(positionSeconds, _elapsed);
      }
    });
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final danmuState = ref.watch(danmuProvider(widget.fileId));
    final notifier = ref.read(danmuProvider(widget.fileId).notifier);
    final engine = notifier.engine;

    // 自动恢复弹幕状态：如果偏好为开启且当前 provider 未启用，则自动 enable。
    if (!_autoEnableChecked) {
      _autoEnableChecked = true;
      final playbackNotifier = ref.read(playbackProvider.notifier);
      if (playbackNotifier.danmuEnabled && !danmuState.enabled) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) notifier.enable();
        });
      }
    }

    // 同步弹幕开关偏好到 PlaybackNotifier（跨集保持）。
    ref.listen(danmuProvider(widget.fileId), (prev, next) {
      if (prev?.enabled != next.enabled) {
        ref.read(playbackProvider.notifier).danmuEnabled = next.enabled;
      }
    });

    // Ticker 生命周期：弹幕开启时运行，关闭时停止
    if (danmuState.enabled) {
      if (!_ticker.isActive) {
        print('[DanmuOverlay] 启动 Ticker');
        _ticker.start();
      }
    } else {
      if (_ticker.isActive) {
        print('[DanmuOverlay] 停止 Ticker');
        _ticker.stop();
      }
    }

    if (engine == null) {
      _cachedScreen = null;
      _lastEngineVersion = -1;
      return const SizedBox.shrink();
    }

    // 引擎版本变化时清除缓存，触发 DanmakuScreen 重建以重新注入 canvas 控制器
    if (danmuState.engineVersion != _lastEngineVersion) {
      _lastEngineVersion = danmuState.engineVersion;
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
              key: ValueKey('danmaku_${widget.fileId}_$_lastEngineVersion'),
              createdController: (controller) {
                engine.attachCanvasController(controller);
              },
              option: cd.DanmakuOption(
                fontSize: engine.fontSize,
                area: engine.area,
                opacity: 1.0, // 固定 1.0，透明度由外层 Opacity widget 控制
                duration: w > 0
                    ? (w / (engine.speed * engine.playbackSpeed))
                        .clamp(3.0, 30.0)
                    : 10.0,
                staticDuration: 5.0,
                strokeWidth: 1.5,
                massiveMode: engine.density >= 0.5,
                safeArea: false,
              ),
            );

            // 透明度通过 Opacity widget 控制（canvas_danmaku 的 _updateOption 不触发 setState）
            // ListenableBuilder 监听 engine 变化以更新透明度
            return ListenableBuilder(
              listenable: engine,
              builder: (context, child) {
                return Opacity(
                  opacity: engine.opacity,
                  child: child,
                );
              },
              child: _cachedScreen!,
            );
          },
        ),
      ),
    );
  }
}
