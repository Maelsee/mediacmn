import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit_video/media_kit_video.dart';
import '../../../logic/player_notifier.dart';

/// 视频渲染层
///
/// 负责显示视频画面，支持手势缩放。
class VideoLayer extends ConsumerWidget {
  final TransformationController transformationController;

  const VideoLayer({
    super.key,
    required this.transformationController,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final videoController =
        ref.watch(playerProvider.select((s) => s.videoController));

    if (videoController == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        return InteractiveViewer(
          transformationController: transformationController,
          minScale: 1.0,
          maxScale: 4.0,
          child: SizedBox(
            width: constraints.maxWidth,
            height: constraints.maxHeight,
            child: Video(
              controller: videoController,
              fit: BoxFit.contain,
              controls: NoVideoControls,
            ),
          ),
        );
      },
    );
  }
}
