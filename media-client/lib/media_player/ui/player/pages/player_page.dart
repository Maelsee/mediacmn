import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:floating/floating.dart';
import 'package:flutter_volume_controller/flutter_volume_controller.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../../../core/state/playback_state.dart';
import '../layouts/common_player_layout.dart';

class PlayerPage extends ConsumerStatefulWidget {
  final String coreId;
  final Object? extra;

  const PlayerPage({super.key, required this.coreId, this.extra});

  @override
  ConsumerState<PlayerPage> createState() => _PlayerPageState();
}

class _PlayerPageState extends ConsumerState<PlayerPage> {
  /// 是否处于 Widget 测试环境。
  ///
  /// 说明：避免在测试环境初始化 PiP 轮询等行为导致定时器残留。
  bool get _isWidgetTest {
    final binding = WidgetsBinding.instance;
    return binding.runtimeType.toString().contains('TestWidgetsFlutterBinding');
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_isWidgetTest) {
        // 进入播放页即启用沉浸式全屏，隐藏状态栏与底部导航栏。
        SystemChrome.setEnabledSystemUIMode(
          SystemUiMode.immersiveSticky,
          overlays: [],
        );

        // 隐藏系统音量条，避免手势调音量时遮挡。
        FlutterVolumeController.updateShowSystemUI(false);
      }
      ref
          .read(playbackProvider.notifier)
          .initialize(coreId: widget.coreId, extra: widget.extra);
    });
  }

  @override
  void dispose() {
    if (!_isWidgetTest) {
      // 退出播放页恢复系统 UI 展示。
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
      // 恢复系统音量条显示。
      FlutterVolumeController.updateShowSystemUI(true);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(playbackProvider);
    final service = ref.watch(playerServiceProvider);
    if (_isWidgetTest) {
      return Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          top: false,
          bottom: false,
          left: false,
          right: false,
          child: CommonPlayerLayout(
            state: s,
            controller: service.videoController,
          ),
        ),
      );
    }

    final floating = ref.watch(floatingProvider);

    // PiP 字幕样式配置：使用较小字号并固定在底部，避免遮挡中心画面。
    final subtitleConfig = SubtitleViewConfiguration(
      style: TextStyle(
        height: 1.25,
        // PiP 窗口较小，字号适当缩小（相对于主界面的 40）
        fontSize: s.settings.subtitleFontSize * 0.85,
        color: const Color(0xffffffff),
        backgroundColor: Colors.transparent,
        shadows: const [
          Shadow(
            color: Color(0xaa000000),
            offset: Offset(2.0, 2.0),
            blurRadius: 2.0,
          ),
        ],
      ),
      // PiP 窗口底部留出一定安全距离，避免贴底
      padding: const EdgeInsets.only(bottom: 12.0),
    );

    return PiPSwitcher(
      floating: floating,
      childWhenDisabled: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          top: false,
          bottom: false,
          left: false,
          right: false,
          child: CommonPlayerLayout(
            state: s,
            controller: service.videoController,
          ),
        ),
      ),
      childWhenEnabled: Scaffold(
        backgroundColor: Colors.black,
        body: service.videoController != null
            ? Video(
                // 强制 key 重建以响应配置变更
                key: ValueKey(
                  'pip_video_${s.settings.subtitleFontSize}',
                ),
                controller: service.videoController!,
                controls: NoVideoControls,
                fit: s.fit,
                subtitleViewConfiguration: subtitleConfig,
              )
            : const SizedBox(),
      ),
    );
  }
}
