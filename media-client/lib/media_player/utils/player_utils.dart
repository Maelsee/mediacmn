import 'package:flutter/foundation.dart';

import '../../media_library/media_models.dart';

/// 将时间格式化为 mm:ss 或 hh:mm:ss。
String formatDuration(Duration d) {
  final totalSeconds = d.inSeconds;
  final hours = totalSeconds ~/ 3600;
  final minutes = (totalSeconds % 3600) ~/ 60;
  final seconds = totalSeconds % 60;
  if (hours > 0) {
    return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
  return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
}

/// 从后端返回中提取可播放的 URL。
///
/// 兼容不同字段命名：url / play_url / playUrl / playurl。
String? extractPlayableUrl(Map<String, dynamic> data) {
  final direct =
      data['url'] ?? data['play_url'] ?? data['playUrl'] ?? data['playurl'];
  if (direct is String) return _normalizePlayUrl(direct);
  final inner = data['data'];
  if (inner is Map) {
    final v = inner['url'] ??
        inner['play_url'] ??
        inner['playUrl'] ??
        inner['playurl'];
    if (v is String) return _normalizePlayUrl(v);
  }
  return null;
}

/// 从后端返回中提取 HTTP 请求头（用于 WebDAV 等需要鉴权的源）。
///
/// 兼容 headers / header 字段。
Map<String, String> extractPlayableHeaders(Map<String, dynamic> data) {
  final direct = data['headers'] ?? data['header'];
  final parsed = _parseHeadersMap(direct);
  if (parsed.isNotEmpty) return parsed;

  final inner = data['data'];
  if (inner is Map) {
    final v = inner['headers'] ?? inner['header'];
    return _parseHeadersMap(v);
  }
  return const {};
}

String? _normalizePlayUrl(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return null;
  final noTicks = trimmed.replaceAll('`', '').trim();
  return noTicks.isEmpty ? null : noTicks;
}

Map<String, String> _parseHeadersMap(Object? raw) {
  if (raw is Map) {
    return raw.map((k, v) => MapEntry(k.toString(), v.toString()));
  }
  return const {};
}

String assetDisplayName(AssetItem item) {
  final type = item.type.isEmpty ? '资源' : item.type;
  final size = item.sizeText;
  if (size != null && size.isNotEmpty) {
    return '$type · $size';
  }
  return type;
}

/// 获取当前平台名称（用于进度上报等）。
String currentPlatformName() {
  if (kIsWeb) return 'web';
  return defaultTargetPlatform.name;
}
