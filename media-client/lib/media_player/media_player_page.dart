import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'ui/player/pages/player_page.dart';

/// 媒体播放器路由页。
///
/// 负责承接路由参数，并将其交给播放器页面进行初始化。
class MediaPlayerPage extends ConsumerWidget {
  /// 媒体核心 ID（路由 path 参数）。
  final String coreId;

  /// 路由额外参数（一般包含 fileId、detail、candidates 等）。
  final Object? extra;

  const MediaPlayerPage({
    super.key,
    required this.coreId,
    this.extra,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PlayerPage(coreId: coreId, extra: extra);
  }
}
