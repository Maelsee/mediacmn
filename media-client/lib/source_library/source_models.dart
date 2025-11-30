class SourceCreateResponse {
  final String id;
  final String? taskId;
  SourceCreateResponse({required this.id, this.taskId});
  factory SourceCreateResponse.fromJson(Map<String, dynamic> json) =>
      SourceCreateResponse(
          id: '${json['id']}', taskId: json['task_id'] as String?);
}

class SourceItem {
  final String id;
  final String type;
  final String name;
  final String status;
  final String? lastScan;
  SourceItem(
      {required this.id,
      required this.type,
      required this.name,
      required this.status,
      this.lastScan});
  factory SourceItem.fromJson(Map<String, dynamic> json) => SourceItem(
        id: '${json['id']}',
        type: (json['type'] as String?) ??
            (json['storage_type'] as String?) ??
            'unknown',
        name: json['name'] as String? ?? '',
        status: json['status'] as String? ?? 'unknown',
        lastScan: json['last_scan'] as String?,
      );
}
