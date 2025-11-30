import '../core/api_client.dart';
import 'playable_source.dart';
import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;

abstract class SourceAdapter {
  Future<PlayableSource> resolve(Map<String, dynamic> input, ApiClient api);
}

class DefaultSourceAdapter implements SourceAdapter {
  @override
  Future<PlayableSource> resolve(
      Map<String, dynamic> input, ApiClient api) async {
    // 已去播放链接化：不直接使用 playurl 入参
    final dynamic asset = input['asset'];
    final List<dynamic> candidates =
        (input['candidates'] as List<dynamic>?) ?? const [];
    final dynamic detail = input['detail'];
    final int? fileId = input['fileId'] as int? ??
        (asset is Map
            ? (asset['fileId'] as int?) ?? (asset['file_id'] as int?)
            : (asset?.fileId as int?));

    // 移除未使用的辅助函数（去播放链接化后不需要资产路径推断播放）

    String? cleanUrl(String? s) {
      if (s == null) return null;
      var t = s.trim();
      if (t.startsWith('`')) t = t.substring(1).trimLeft();
      if (t.endsWith('`')) t = t.substring(0, t.length - 1).trimRight();
      return t;
    }

    // 仅凭 fileId 请求后端播放接口生成预签名 URL
    int? fallbackFileId = fileId;
    if (fallbackFileId == null) {
      for (final c in candidates) {
        try {
          if (c is Map) {
            final fid = (c['fileId'] as int?) ?? (c['file_id'] as int?);
            if (fid != null) {
              fallbackFileId = fid;
              break;
            }
          } else {
            final fid = c.fileId as int?;
            if (fid != null) {
              fallbackFileId = fid;
              break;
            }
          }
        } catch (_) {}
      }
    }
    if (fallbackFileId == null && detail != null) {
      try {
        // 兼容 Map 结构的 detail
        if (detail is Map<String, dynamic>) {
          final versions = (detail['versions'] as List?) ?? const [];
          for (final v in versions) {
            final assets = (v is Map) ? (v['assets'] as List?) : const [];
            if (assets == null) continue;
            for (final a in assets) {
              if (a is Map) {
                final t = (a['type'] as String?)?.toLowerCase();
                final fid = (a['file_id'] as int?) ?? (a['fileId'] as int?);
                if (fid != null && (t == null || t == 'video')) {
                  fallbackFileId = fid;
                  break;
                }
              }
            }
            if (fallbackFileId != null) break;
          }
          if (fallbackFileId == null) {
            final seasons = (detail['seasons'] as List?) ?? const [];
            for (final s in seasons) {
              final eps = (s is Map) ? (s['episodes'] as List?) : const [];
              if (eps == null) continue;
              for (final e in eps) {
                final assets = (e is Map) ? (e['assets'] as List?) : const [];
                if (assets == null) continue;
                for (final a in assets) {
                  if (a is Map) {
                    final t = (a['type'] as String?)?.toLowerCase();
                    final fid = (a['file_id'] as int?) ?? (a['fileId'] as int?);
                    if (fid != null && (t == null || t == 'video')) {
                      fallbackFileId = fid;
                      break;
                    }
                  }
                }
                if (fallbackFileId != null) break;
              }
              if (fallbackFileId != null) break;
            }
          }
        } else {
          // 兼容对象结构的 detail（如 MediaDetail）
          final v = (detail as dynamic).versions as List?;
          if (v != null) {
            for (final it in v) {
              try {
                final assets = (it as dynamic).assets as List?;
                if (assets != null) {
                  for (final a in assets) {
                    final t = (a as dynamic).type as String?;
                    final fid = (a as dynamic).fileId as int?;
                    if (fid != null &&
                        (t == null || t.toLowerCase() == 'video')) {
                      fallbackFileId = fid;
                      break;
                    }
                  }
                }
                if (fallbackFileId != null) break;
              } catch (_) {}
            }
          }
        }
      } catch (_) {}
    }
    if (fallbackFileId != null) {
      int? startPositionMs;
      try {
        final v = await api.getPlaybackProgress(fallbackFileId);
        startPositionMs = (v != null && v > 0) ? v : null;
      } catch (_) {}
      final data = await api.getPlayUrl(fallbackFileId);
      final got = cleanUrl(data['playurl'] as String?);
      Map<String, String>? hdrs;
      try {
        final raw = data['headers'];
        if (raw is Map) {
          hdrs = raw.map((k, v) => MapEntry('$k', '$v'));
        }
      } catch (_) {}
      final int? exp = data['expires_at'] as int?;
      final DateTime? expiresAt =
          exp != null ? DateTime.fromMillisecondsSinceEpoch(exp * 1000) : null;
      if (got != null && got.isNotEmpty) {
        String url = got;
        if (kIsWeb && hdrs != null) {
          final auth = hdrs['Authorization'];
          final m =
              auth != null ? RegExp(r'^Basic\s+(.+)$').firstMatch(auth) : null;
          if (m != null) {
            try {
              final raw = utf8.decode(base64Decode(m.group(1)!));
              final i = raw.indexOf(':');
              if (i > 0) {
                final u = Uri.parse(url);
                final rebuilt = Uri(
                  scheme: u.scheme,
                  userInfo:
                      '${Uri.encodeComponent(raw.substring(0, i))}:${Uri.encodeComponent(raw.substring(i + 1))}',
                  host: u.host,
                  port: u.hasPort ? u.port : null,
                  path: u.path,
                  query: u.query,
                  fragment: u.fragment,
                ).toString();
                url = rebuilt;
              }
            } catch (_) {}
          }
        }
        return PlayableSource(
            uri: url,
            headers: hdrs,
            format: data['format'] as String?,
            expiresAt: expiresAt,
            fileId: fallbackFileId,
            startPositionMs: startPositionMs);
      }
    }
    throw Exception('no_play_source');
  }
}
