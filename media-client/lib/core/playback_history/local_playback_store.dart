import 'package:hive_flutter/hive_flutter.dart';

import 'models.dart';

/// 播放历史的本地存储封装。
///
/// 说明：
/// - 统一管理 Hive Box 的打开与读写。
/// - 以 Map 作为持久化格式，避免引入 Hive TypeAdapter。
class LocalPlaybackStore {
  /// 播放进度盒子名称。
  static const String progressBoxName = 'playback_progress_box';

  /// 最近观看索引盒子名称。
  static const String recentIndexBoxName = 'playback_recent_index_box';

  /// 待同步 Outbox 盒子名称。
  static const String outboxBoxName = 'playback_progress_outbox_box';

  Box? _progressBox;
  Box? _recentIndexBox;
  Box? _outboxBox;

  /// 获取或打开播放进度盒子。
  Future<Box> _getProgressBox() async {
    _progressBox ??= await Hive.openBox(progressBoxName);
    return _progressBox!;
  }

  /// 获取或打开最近观看索引盒子。
  Future<Box> _getRecentIndexBox() async {
    _recentIndexBox ??= await Hive.openBox(recentIndexBoxName);
    return _recentIndexBox!;
  }

  /// 获取或打开 outbox 盒子。
  Future<Box> _getOutboxBox() async {
    _outboxBox ??= await Hive.openBox(outboxBoxName);
    return _outboxBox!;
  }

  /// 读取指定文件的播放进度记录。
  Future<PlaybackProgressRecord?> getProgress(int fileId) async {
    final box = await _getProgressBox();
    final raw = box.get(fileId);
    if (raw is Map) {
      return PlaybackProgressRecord.fromJson(raw.cast<String, dynamic>());
    }
    return null;
  }

  /// 写入播放进度记录，并同步更新最近观看索引。
  Future<void> putProgress(PlaybackProgressRecord record) async {
    final progressBox = await _getProgressBox();
    await progressBox.put(record.fileId, record.toJson());

    final indexBox = await _getRecentIndexBox();
    await indexBox.put(record.fileId, record.lastPlayedAtMs);
  }

  /// 删除指定文件的播放进度记录与索引。
  Future<void> deleteProgress(int fileId) async {
    final progressBox = await _getProgressBox();
    await progressBox.delete(fileId);

    final indexBox = await _getRecentIndexBox();
    await indexBox.delete(fileId);
  }

  /// 获取最近观看的文件 ID 列表（按 lastPlayedAtMs 倒序）。
  Future<List<int>> getRecentFileIds({required int limit}) async {
    final indexBox = await _getRecentIndexBox();
    final entries = <MapEntry<int, int>>[];
    for (final key in indexBox.keys) {
      final k = key is int ? key : int.tryParse('$key');
      if (k == null) continue;
      final v = indexBox.get(key);
      final ms = (v is num) ? v.toInt() : int.tryParse('$v');
      if (ms == null) continue;
      entries.add(MapEntry(k, ms));
    }
    entries.sort((a, b) => b.value.compareTo(a.value));
    return entries.take(limit).map((e) => e.key).toList();
  }

  /// 获取最近观看的进度记录列表。
  Future<List<PlaybackProgressRecord>> getRecentProgressRecords({
    required int limit,
  }) async {
    final fileIds = await getRecentFileIds(limit: limit);
    if (fileIds.isEmpty) return const [];

    final progressBox = await _getProgressBox();
    final records = <PlaybackProgressRecord>[];
    for (final fileId in fileIds) {
      final raw = progressBox.get(fileId);
      if (raw is Map) {
        records.add(
          PlaybackProgressRecord.fromJson(raw.cast<String, dynamic>()),
        );
      }
    }
    records.sort((a, b) => b.lastPlayedAtMs.compareTo(a.lastPlayedAtMs));
    return records;
  }

  Stream<List<PlaybackProgressRecord>> watchRecentProgressRecords({
    required int limit,
  }) async* {
    yield await getRecentProgressRecords(limit: limit);
    final indexBox = await _getRecentIndexBox();
    await for (final _ in indexBox.watch()) {
      yield await getRecentProgressRecords(limit: limit);
    }
  }

  /// 将上报任务加入 outbox。
  Future<void> enqueueReportTask(ProgressReportTask task) async {
    final box = await _getOutboxBox();
    await box.put(task.id, task.toJson());
  }

  /// 获取当前时间之前可执行的 outbox 任务。
  Future<List<ProgressReportTask>> listDueReportTasks({
    required int nowMs,
    int limit = 20,
  }) async {
    final box = await _getOutboxBox();
    final tasks = <ProgressReportTask>[];
    for (final key in box.keys) {
      final raw = box.get(key);
      if (raw is! Map) continue;
      final task = ProgressReportTask.fromJson(raw.cast<String, dynamic>());
      if (task.nextRetryAtMs <= nowMs) {
        tasks.add(task);
      }
    }
    tasks.sort((a, b) => a.createdAtMs.compareTo(b.createdAtMs));
    if (tasks.length <= limit) return tasks;
    return tasks.take(limit).toList();
  }

  /// 更新 outbox 任务。
  Future<void> updateReportTask(ProgressReportTask task) async {
    final box = await _getOutboxBox();
    await box.put(task.id, task.toJson());
  }

  /// 删除 outbox 任务。
  Future<void> deleteReportTask(String id) async {
    final box = await _getOutboxBox();
    await box.delete(id);
  }

  static Future<void> clearAll() async {
    await _clearBox(progressBoxName);
    await _clearBox(recentIndexBoxName);
    await _clearBox(outboxBoxName);
  }

  static Future<void> _clearBox(String name) async {
    if (Hive.isBoxOpen(name)) {
      final box = Hive.box(name);
      await box.clear();
      await box.close();
    }

    final exists = await Hive.boxExists(name);
    if (!exists) return;

    try {
      await Hive.deleteBoxFromDisk(name);
    } catch (_) {}
  }
}
