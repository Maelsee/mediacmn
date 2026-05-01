import 'dart:async';

import '../../../core/playback_history/playback_progress_repository.dart';

/// 播放进度快照（用于从 PlaybackNotifier 传递当前状态给 ProgressTracker）。
class ProgressSnapshot {
  final int? fileId;
  final int? coreId;
  final String? mediaType;
  final String? title;
  final String? coverUrl;
  final int positionMs;
  final int? durationMs;
  final bool playing;

  const ProgressSnapshot({
    required this.fileId,
    required this.coreId,
    required this.mediaType,
    required this.title,
    required this.coverUrl,
    required this.positionMs,
    required this.durationMs,
    required this.playing,
  });
}

/// 播放进度追踪器。
///
/// 负责本地进度定时保存和播放关闭时的远端上报。
class ProgressTracker {
  final PlaybackProgressRepository repository;

  Timer? _timer;
  int _lastSavedPositionMs = -1;

  ProgressTracker({required this.repository});

  /// 启动本地进度保存定时器（每 2 秒）。
  void start(ProgressSnapshot Function() snapshotProvider) {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) async {
      final snap = snapshotProvider();
      if (!snap.playing) return;
      await saveLocalProgress(snap);
    });
  }

  /// 保存本地进度（带去重）。
  Future<void> saveLocalProgress(ProgressSnapshot snap) async {
    if (snap.fileId == null) return;
    if (snap.positionMs == _lastSavedPositionMs) return;
    _lastSavedPositionMs = snap.positionMs;

    await repository.saveLocalProgress(
      fileId: snap.fileId!,
      coreId: snap.coreId,
      mediaType: snap.mediaType,
      positionMs: snap.positionMs,
      durationMs: snap.durationMs,
      title: snap.title,
      coverUrl: snap.coverUrl,
    );
  }

  /// 上报播放关闭事件。
  Future<void> reportClose(ProgressSnapshot snap) async {
    if (snap.fileId == null) return;
    await repository.enqueueCloseReport(
      fileId: snap.fileId!,
      coreId: snap.coreId,
      mediaType: snap.mediaType,
      positionMs: snap.positionMs,
      durationMs: snap.durationMs,
      title: snap.title,
      coverUrl: snap.coverUrl,
    );
  }

  /// 上报播放打开事件。
  Future<void> reportOpen(ProgressSnapshot snap) async {
    if (snap.fileId == null) return;
    await repository.enqueueOpenReport(
      fileId: snap.fileId!,
      coreId: snap.coreId,
      mediaType: snap.mediaType,
      positionMs: snap.positionMs,
      durationMs: snap.durationMs,
      title: snap.title,
      coverUrl: snap.coverUrl,
    );
  }

  /// 释放资源。
  void dispose() {
    _timer?.cancel();
  }
}
