import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:media_client/media_library/media_models.dart';
import 'package:media_client/media_player/core/state/playback_state.dart';
import 'package:media_client/media_player/desktop_window/desktop_player_side_panel.dart';

void main() {
  testWidgets('DesktopPlayerSidePanel 渲染选集并响应点击', (tester) async {
    var tapped = -1;

    final episodes = [
      EpisodeDetail(
        episodeNumber: 1,
        title: '开始',
        assets: [
          AssetItem(fileId: 11, path: '/a.mp4', type: 'mp4'),
        ],
      ),
      EpisodeDetail(
        episodeNumber: 2,
        title: '继续',
        assets: [
          AssetItem(fileId: 22, path: '/b.mp4', type: 'mp4'),
        ],
      ),
    ];

    final state = PlaybackState(
      loading: false,
      episodes: episodes,
      fileId: 11,
      currentEpisodeFileId: 11,
      episodesLoading: false,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Stack(
            children: [
              DesktopPlayerSidePanel(
                visible: true,
                state: state,
                onClose: () {},
                onEpisodeTap: (index) async {
                  tapped = index;
                },
              ),
            ],
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.textContaining('第1集'), findsOneWidget);
    expect(find.textContaining('第2集'), findsOneWidget);

    await tester.tap(find.textContaining('第2集'));
    await tester.pump();
    expect(tapped, 1);
  });
}
