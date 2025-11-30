import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'playable_source.dart';
// import 'package:flutter/foundation.dart' show kIsWeb;

class PlayerCore {
  final Player player;
  late final VideoController controller;
  PlayerCore(this.player) {
    controller = VideoController(player);
  }
  Future<void> open(PlayableSource src) async {
    await player.open(Media(src.uri, httpHeaders: src.headers));
    try {
      final start = src.startPositionMs ?? 0;
      if (start > 0) {
        await player.seek(Duration(milliseconds: start));
      }
    } catch (_) {}
    await player.play();
  }

  void dispose() {
    player.dispose();
  }
}
