class ScanTask {
  final String id;
  final String sourceId;
  final String status;
  final int progress;
  final String? error;
  ScanTask({
    required this.id,
    required this.sourceId,
    required this.status,
    required this.progress,
    this.error,
  });
  factory ScanTask.fromJson(Map<String, dynamic> json) => ScanTask(
        id: json['id'] as String,
        sourceId: json['source_id'] as String,
        status: json['status'] as String,
        progress: (json['progress'] ?? 0) as int,
        error: json['error'] as String?,
      );
}

class ScanGroup {
  final String groupId;
  final String status;
  final int progress;
  final List<ScanTask> tasks;
  ScanGroup({
    required this.groupId,
    required this.status,
    required this.progress,
    required this.tasks,
  });
  factory ScanGroup.fromJson(Map<String, dynamic> json) => ScanGroup(
        groupId: json['group_id'] as String,
        status: json['status'] as String,
        progress: (json['progress'] ?? 0) as int,
        tasks: (json['tasks'] as List)
            .cast<Map<String, dynamic>>()
            .map(ScanTask.fromJson)
            .toList(),
      );
}
