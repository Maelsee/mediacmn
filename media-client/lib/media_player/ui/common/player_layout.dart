import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../browser/browser_player_layout.dart';
import '../mobile/mobile_player_layout.dart';

class PlayerLayout extends ConsumerWidget {
  final String? title;
  final List<Map<String, dynamic>> episodes;
  final int currentEpisodeIndex;
  final Function(int index)? onEpisodeSelected;
  final VoidCallback? onNext;
  final VoidCallback? onPrev;

  const PlayerLayout({
    super.key,
    this.title,
    this.episodes = const [],
    this.currentEpisodeIndex = -1,
    this.onEpisodeSelected,
    this.onNext,
    this.onPrev,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (kIsWeb) {
      return BrowserPlayerLayout(
        title: title,
        episodes: episodes,
        currentEpisodeIndex: currentEpisodeIndex,
        onEpisodeSelected: onEpisodeSelected,
        onNext: onNext,
        onPrev: onPrev,
      );
    }

    return MobilePlayerLayout(
      title: title,
      episodes: episodes,
      currentEpisodeIndex: currentEpisodeIndex,
      onEpisodeSelected: onEpisodeSelected,
      onNext: onNext,
      onPrev: onPrev,
    );
  }
}
