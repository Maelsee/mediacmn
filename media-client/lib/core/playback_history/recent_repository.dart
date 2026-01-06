import '../api_client.dart';
import '../../media_library/media_models.dart';
import 'local_playback_store.dart';
import 'models.dart';

/// 最近观看仓库。
///
/// 目标：
/// - 首页区块与最近列表页统一数据源。
/// - 进度字段以本地为主（尤其是 dirty 状态），远端作为补全与跨设备纠错。
class RecentRepository {
  /// 本地存储。
  final LocalPlaybackStore local;

  /// 网络 API 客户端。
  final ApiClient api;

  const RecentRepository({
    required this.local,
    required this.api,
  });

  /// 获取最近观看（用于首页区块）。
  ///
  /// 规则：
  /// - 本地优先，若本地为空再请求远端。
  /// - 若请求远端成功，会回填本地进度与索引。
  Future<List<RecentCardItem>> getRecent({int limit = 20}) async {
    final localRecords = await local.getRecentProgressRecords(limit: limit);
    if (localRecords.isNotEmpty) {
      return localRecords.map(_recordToRecentItem).toList();
    }

    if (!api.isLoggedIn) return const [];
    final remoteItems = await api.getRecent(limit: limit);
    await _mergeRemoteRecentIntoLocal(remoteItems);
    return await _loadRecentFromLocal(limit: limit, fallback: remoteItems);
  }

  /// 拉取最近观看分页（用于最近列表页）。
  ///
  /// 说明：列表页当前使用远端分页作为主序列，本地进度用于覆盖 position/duration。
  Future<List<RecentCardItem>> fetchRecentPage({
    required int page,
    required int pageSize,
    String sort = 'updated_desc',
  }) async {
    if (!api.isLoggedIn) return const [];
    final raw =
        await api.getRecentRaw(page: page, pageSize: pageSize, sort: sort);
    final items = raw.map(RecentCardItem.fromApi).toList();

    final merged = <RecentCardItem>[];
    for (final item in items) {
      final fid = item.fileId;
      if (fid == null) {
        merged.add(item);
        continue;
      }
      final record = await local.getProgress(fid);
      if (record == null) {
        merged.add(item);
        continue;
      }
      merged.add(_mergeItemWithLocal(item, record));
    }

    await _mergeRemoteRecentIntoLocal(merged);
    return merged;
  }

  Future<List<RecentCardItem>> _loadRecentFromLocal({
    required int limit,
    required List<RecentCardItem> fallback,
  }) async {
    final localRecords = await local.getRecentProgressRecords(limit: limit);
    if (localRecords.isEmpty) return fallback;
    return localRecords.map(_recordToRecentItem).toList();
  }

  RecentCardItem _recordToRecentItem(PlaybackProgressRecord record) {
    final id = record.coreId ?? record.fileId;
    return RecentCardItem(
      id: id,
      name: record.title ?? '未命名',
      coverUrl: record.coverUrl,
      mediaType: record.mediaType ?? 'movie',
      positionMs: record.positionMs,
      durationMs: record.durationMs,
      fileId: record.fileId,
    );
  }

  RecentCardItem _mergeItemWithLocal(
      RecentCardItem remoteItem, PlaybackProgressRecord localRecord) {
    final remotePos = remoteItem.positionMs ?? 0;
    final localPos = localRecord.positionMs;
    final shouldPreferLocal = localRecord.dirty || localPos >= remotePos;
    return RecentCardItem(
      id: remoteItem.id,
      name: remoteItem.name,
      coverUrl: remoteItem.coverUrl,
      mediaType: remoteItem.mediaType,
      positionMs: shouldPreferLocal ? localPos : remotePos,
      durationMs: shouldPreferLocal
          ? (localRecord.durationMs ?? remoteItem.durationMs)
          : remoteItem.durationMs,
      fileId: remoteItem.fileId,
    );
  }

  Future<void> _mergeRemoteRecentIntoLocal(
      List<RecentCardItem> remoteItems) async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    for (final item in remoteItems) {
      final fid = item.fileId;
      if (fid == null) continue;

      final existing = await local.getProgress(fid);
      final remotePos = item.positionMs ?? 0;
      final remoteDur = item.durationMs;

      final merged = PlaybackProgressRecord(
        fileId: fid,
        coreId: item.id,
        mediaType: item.mediaType,
        positionMs:
            _choosePositionMs(existing: existing, remotePositionMs: remotePos),
        durationMs: existing?.durationMs ?? remoteDur,
        updatedAtMs: existing?.updatedAtMs ?? nowMs,
        lastPlayedAtMs: existing?.lastPlayedAtMs ?? nowMs,
        lastReportedAtMs: existing?.lastReportedAtMs,
        dirty: existing?.dirty ?? false,
        title: existing?.title ?? item.name,
        coverUrl: existing?.coverUrl ?? item.coverUrl,
      );

      await local.putProgress(merged);
    }
  }

  int _choosePositionMs({
    required PlaybackProgressRecord? existing,
    required int remotePositionMs,
  }) {
    if (existing == null) return remotePositionMs;
    if (existing.dirty) return existing.positionMs;
    return existing.positionMs >= remotePositionMs
        ? existing.positionMs
        : remotePositionMs;
  }
}
