import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api_client.dart';
import 'local_playback_store.dart';
import 'playback_progress_repository.dart';
import 'recent_repository.dart';
import 'remote_playback_data_source.dart';

/// 播放历史本地存储 Provider。
final localPlaybackStoreProvider = Provider<LocalPlaybackStore>((ref) {
  return LocalPlaybackStore();
});

/// 播放历史远端数据源 Provider。
final remotePlaybackDataSourceProvider = Provider<RemotePlaybackDataSource>((
  ref,
) {
  final api = ref.watch(apiClientProvider);
  return RemotePlaybackDataSource(api: api);
});

/// 播放进度仓库 Provider。
final playbackProgressRepositoryProvider = Provider<PlaybackProgressRepository>(
  (ref) {
    final local = ref.watch(localPlaybackStoreProvider);
    final remote = ref.watch(remotePlaybackDataSourceProvider);
    return PlaybackProgressRepository(local: local, remote: remote);
  },
);

/// 最近观看仓库 Provider。
final recentRepositoryProvider = Provider<RecentRepository>((ref) {
  final local = ref.watch(localPlaybackStoreProvider);
  final api = ref.watch(apiClientProvider);
  return RecentRepository(local: local, api: api);
});
