import 'dart:async';

import 'package:flutter/foundation.dart';

import 'local_playback_store.dart';
import 'models.dart';
import 'remote_playback_data_source.dart';

/// 播放进度仓库。
///
/// 目标：
/// - 播放过程高频写本地（离线优先）。
/// - 仅在关键时点（打开/关闭）将上报任务写入 outbox，并择机同步到服务端。
class PlaybackProgressRepository {
  /// 本地存储。
  final LocalPlaybackStore local;

  /// 远端数据源。
  final RemotePlaybackDataSource remote;

  const PlaybackProgressRepository({
    required this.local,
    required this.remote,
  });

  /// 统一的续播进度获取入口。
  ///
  /// 规则：
  /// 1) 路由显式传入 routeStartMs 优先。
  /// 2) 读取本地缓存。
  /// 3) 本地无数据时再请求远端，并回填本地。
  Future<int?> getResumePositionMs({
    required int fileId,
    int? routeStartMs,
  }) async {
    if (routeStartMs != null) return routeStartMs;

    final localRecord = await local.getProgress(fileId);
    if (localRecord != null) {
      return localRecord.positionMs;
    }

    final remoteMs = await remote.fetchProgressMs(fileId);
    if (remoteMs == null) return null;

    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final record = PlaybackProgressRecord(
      fileId: fileId,
      positionMs: remoteMs,
      durationMs: null,
      updatedAtMs: nowMs,
      lastPlayedAtMs: nowMs,
      dirty: false,
    );
    await local.putProgress(record);
    return remoteMs;
  }

  /// 保存一次本地播放进度（高频调用）。
  Future<void> saveLocalProgress({
    required int fileId,
    int? coreId,
    String? mediaType,
    required int positionMs,
    int? durationMs,
    String? title,
    String? coverUrl,
  }) async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final existing = await local.getProgress(fileId);

    final merged = PlaybackProgressRecord(
      fileId: fileId,
      coreId: coreId ?? existing?.coreId,
      mediaType: mediaType ?? existing?.mediaType,
      positionMs: positionMs,
      durationMs: durationMs ?? existing?.durationMs,
      updatedAtMs: nowMs,
      lastPlayedAtMs: nowMs,
      lastReportedAtMs: existing?.lastReportedAtMs,
      dirty: true,
      title: title ?? existing?.title,
      coverUrl: coverUrl ?? existing?.coverUrl,
    );

    await local.putProgress(merged);
  }

  /// 记录“打开播放器”关键点，并入队一次上报任务。
  Future<void> enqueueOpenReport({
    required int fileId,
    int? coreId,
    String? mediaType,
    required int positionMs,
    int? durationMs,
    String? title,
    String? coverUrl,
  }) async {
    await saveLocalProgress(
      fileId: fileId,
      coreId: coreId,
      mediaType: mediaType,
      positionMs: positionMs,
      durationMs: durationMs,
      title: title,
      coverUrl: coverUrl,
    );

    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final task = ProgressReportTask(
      id: _newTaskId(nowMs),
      fileId: fileId,
      coreId: coreId,
      positionMs: positionMs,
      durationMs: durationMs,
      event: 'open',
      status: null,
      createdAtMs: nowMs,
      retryCount: 0,
      nextRetryAtMs: nowMs,
      platform: _currentPlatformName(),
      deviceId: null,
      mediaType: mediaType,
    );
    await local.enqueueReportTask(task);
    unawaited(syncOutbox());
  }

  /// 记录“离开播放器”关键点，并入队一次上报任务。
  Future<void> enqueueCloseReport({
    required int fileId,
    int? coreId,
    String? mediaType,
    required int positionMs,
    int? durationMs,
    String? title,
    String? coverUrl,
  }) async {
    await saveLocalProgress(
      fileId: fileId,
      coreId: coreId,
      mediaType: mediaType,
      positionMs: positionMs,
      durationMs: durationMs,
      title: title,
      coverUrl: coverUrl,
    );

    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final task = ProgressReportTask(
      id: _newTaskId(nowMs),
      fileId: fileId,
      coreId: coreId,
      positionMs: positionMs,
      durationMs: durationMs,
      event: 'close',
      status: null,
      createdAtMs: nowMs,
      retryCount: 0,
      nextRetryAtMs: nowMs,
      platform: _currentPlatformName(),
      deviceId: null,
      mediaType: mediaType,
    );
    await local.enqueueReportTask(task);
    unawaited(syncOutbox());
  }

  /// 同步 outbox 中到期的上报任务。
  ///
  /// 说明：
  /// - 该方法可在应用启动、页面退出、网络恢复时调用。
  /// - 当前实现为“尽力而为”同步，不抛出错误影响主流程。
  Future<void> syncOutbox({int batchSize = 20}) async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final tasks =
        await local.listDueReportTasks(nowMs: nowMs, limit: batchSize);
    if (tasks.isEmpty) return;

    for (final task in tasks) {
      try {
        await remote.reportProgress(task);
        await local.deleteReportTask(task.id);

        final record = await local.getProgress(task.fileId);
        if (record != null) {
          final shouldClearDirty = record.updatedAtMs <= task.createdAtMs;
          await local.putProgress(record.copyWith(
            lastReportedAtMs: nowMs,
            dirty: shouldClearDirty ? false : record.dirty,
          ));
        }
      } catch (_) {
        final next = _nextRetryAtMs(nowMs: nowMs, retryCount: task.retryCount);
        final updated = task.copyWith(
          retryCount: task.retryCount + 1,
          nextRetryAtMs: next,
        );
        await local.updateReportTask(updated);
      }
    }
  }

  /// 删除一条播放进度（本地立即删除，远端尽力删除）。
  Future<void> deleteProgress({required int fileId}) async {
    final snapshot = await local.getProgress(fileId);
    await local.deleteProgress(fileId);
    try {
      await remote.api.deletePlaybackProgress(fileId);
    } catch (_) {
      if (snapshot != null) {
        await local.putProgress(snapshot);
      }
      rethrow;
    }
  }

  String _newTaskId(int nowMs) =>
      '$nowMs-${DateTime.now().microsecondsSinceEpoch}';

  int _nextRetryAtMs({required int nowMs, required int retryCount}) {
    final base = 1000;
    final exp = 1 << (retryCount.clamp(0, 10));
    final delayMs = (base * exp).clamp(1000, 60 * 60 * 1000);
    return nowMs + delayMs;
  }

  String _currentPlatformName() {
    if (kIsWeb) return 'web';
    return defaultTargetPlatform.name;
  }
}
