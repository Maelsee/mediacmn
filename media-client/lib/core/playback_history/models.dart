// 播放历史模块的数据模型定义。
//
// 说明：
// - 该模块为“离线优先 + 异步同步”的播放历史能力提供基础数据结构。
// - Hive 存储使用 Map 结构持久化，避免引入 TypeAdapter 的额外维护成本。

class PlaybackProgressRecord {
  /// 文件 ID（续播与上报主键）。
  final int fileId;

  /// 媒体核心 ID（用于路由与详情定位）。
  final int? coreId;

  /// 媒体类型（movie/tv/tv_episode...）。
  final String? mediaType;

  /// 当前播放进度（毫秒）。
  final int positionMs;

  /// 总时长（毫秒）。
  final int? durationMs;

  /// 本地最后写入时间（epoch ms）。
  final int updatedAtMs;

  /// 最近一次播放时间（epoch ms），用于“最近观看”排序。
  final int lastPlayedAtMs;

  /// 最后一次成功上报到服务端的时间（epoch ms）。
  final int? lastReportedAtMs;

  /// 是否存在未同步的本地更新。
  final bool dirty;

  /// 离线展示用标题（可选）。
  final String? title;

  /// 离线展示用封面 URL（可选）。
  final String? coverUrl;

  const PlaybackProgressRecord({
    required this.fileId,
    this.coreId,
    this.mediaType,
    required this.positionMs,
    this.durationMs,
    required this.updatedAtMs,
    required this.lastPlayedAtMs,
    this.lastReportedAtMs,
    required this.dirty,
    this.title,
    this.coverUrl,
  });

  PlaybackProgressRecord copyWith({
    int? fileId,
    int? coreId,
    String? mediaType,
    int? positionMs,
    int? durationMs,
    int? updatedAtMs,
    int? lastPlayedAtMs,
    int? lastReportedAtMs,
    bool? dirty,
    String? title,
    String? coverUrl,
  }) {
    return PlaybackProgressRecord(
      fileId: fileId ?? this.fileId,
      coreId: coreId ?? this.coreId,
      mediaType: mediaType ?? this.mediaType,
      positionMs: positionMs ?? this.positionMs,
      durationMs: durationMs ?? this.durationMs,
      updatedAtMs: updatedAtMs ?? this.updatedAtMs,
      lastPlayedAtMs: lastPlayedAtMs ?? this.lastPlayedAtMs,
      lastReportedAtMs: lastReportedAtMs ?? this.lastReportedAtMs,
      dirty: dirty ?? this.dirty,
      title: title ?? this.title,
      coverUrl: coverUrl ?? this.coverUrl,
    );
  }

  /// 将对象序列化为可持久化的 Map。
  Map<String, dynamic> toJson() {
    return {
      'file_id': fileId,
      'core_id': coreId,
      'media_type': mediaType,
      'position_ms': positionMs,
      'duration_ms': durationMs,
      'updated_at_ms': updatedAtMs,
      'last_played_at_ms': lastPlayedAtMs,
      'last_reported_at_ms': lastReportedAtMs,
      'dirty': dirty,
      'title': title,
      'cover_url': coverUrl,
    };
  }

  /// 从 Map 反序列化为对象。
  factory PlaybackProgressRecord.fromJson(Map<String, dynamic> json) {
    return PlaybackProgressRecord(
      fileId: (json['file_id'] as num).toInt(),
      coreId: (json['core_id'] as num?)?.toInt(),
      mediaType: json['media_type'] as String?,
      positionMs: (json['position_ms'] as num?)?.toInt() ?? 0,
      durationMs: (json['duration_ms'] as num?)?.toInt(),
      updatedAtMs: (json['updated_at_ms'] as num?)?.toInt() ?? 0,
      lastPlayedAtMs: (json['last_played_at_ms'] as num?)?.toInt() ?? 0,
      lastReportedAtMs: (json['last_reported_at_ms'] as num?)?.toInt(),
      dirty: (json['dirty'] as bool?) ?? false,
      title: json['title'] as String?,
      coverUrl: json['cover_url'] as String?,
    );
  }
}

class ProgressReportTask {
  /// 任务 ID（建议使用时间戳或 UUID）。
  final String id;

  /// 文件 ID。
  final int fileId;

  /// 媒体核心 ID（可选）。
  final int? coreId;

  /// 进度（毫秒）。
  final int positionMs;

  /// 时长（毫秒）。
  final int? durationMs;

  /// 事件类型（open/close/compensate）。
  ///
  /// 说明：该字段用于客户端内部区分上报触发点。
  /// 若后端支持 status，可通过 status 字段传入；否则仅携带 position/duration 即可。
  final String event;

  /// 透传给后端的状态字段（可选）。
  final String? status;

  /// 任务创建时间（epoch ms）。
  final int createdAtMs;

  /// 重试次数。
  final int retryCount;

  /// 下次允许重试时间（epoch ms）。
  final int nextRetryAtMs;

  /// 平台信息（可选）。
  final String? platform;

  /// 设备标识（可选）。
  final String? deviceId;

  /// 媒体类型（可选）。
  final String? mediaType;

  const ProgressReportTask({
    required this.id,
    required this.fileId,
    this.coreId,
    required this.positionMs,
    this.durationMs,
    required this.event,
    this.status,
    required this.createdAtMs,
    required this.retryCount,
    required this.nextRetryAtMs,
    this.platform,
    this.deviceId,
    this.mediaType,
  });

  ProgressReportTask copyWith({
    String? id,
    int? fileId,
    int? coreId,
    int? positionMs,
    int? durationMs,
    String? event,
    String? status,
    int? createdAtMs,
    int? retryCount,
    int? nextRetryAtMs,
    String? platform,
    String? deviceId,
    String? mediaType,
  }) {
    return ProgressReportTask(
      id: id ?? this.id,
      fileId: fileId ?? this.fileId,
      coreId: coreId ?? this.coreId,
      positionMs: positionMs ?? this.positionMs,
      durationMs: durationMs ?? this.durationMs,
      event: event ?? this.event,
      status: status ?? this.status,
      createdAtMs: createdAtMs ?? this.createdAtMs,
      retryCount: retryCount ?? this.retryCount,
      nextRetryAtMs: nextRetryAtMs ?? this.nextRetryAtMs,
      platform: platform ?? this.platform,
      deviceId: deviceId ?? this.deviceId,
      mediaType: mediaType ?? this.mediaType,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'file_id': fileId,
      'core_id': coreId,
      'position_ms': positionMs,
      'duration_ms': durationMs,
      'event': event,
      'status': status,
      'created_at_ms': createdAtMs,
      'retry_count': retryCount,
      'next_retry_at_ms': nextRetryAtMs,
      'platform': platform,
      'device_id': deviceId,
      'media_type': mediaType,
    };
  }

  factory ProgressReportTask.fromJson(Map<String, dynamic> json) {
    return ProgressReportTask(
      id: (json['id'] ?? '').toString(),
      fileId: (json['file_id'] as num).toInt(),
      coreId: (json['core_id'] as num?)?.toInt(),
      positionMs: (json['position_ms'] as num?)?.toInt() ?? 0,
      durationMs: (json['duration_ms'] as num?)?.toInt(),
      event: (json['event'] ?? 'unknown').toString(),
      status: json['status'] as String?,
      createdAtMs: (json['created_at_ms'] as num?)?.toInt() ?? 0,
      retryCount: (json['retry_count'] as num?)?.toInt() ?? 0,
      nextRetryAtMs: (json['next_retry_at_ms'] as num?)?.toInt() ?? 0,
      platform: json['platform'] as String?,
      deviceId: json['device_id'] as String?,
      mediaType: json['media_type'] as String?,
    );
  }
}
