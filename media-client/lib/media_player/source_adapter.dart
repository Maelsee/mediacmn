import '../core/api_client.dart';
import 'playable_source.dart';
import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;

/// 播放源适配器抽象接口
///
/// 定义了从输入参数解析为可播放源的接口规范。
/// 不同的适配器实现可以支持不同的数据源和解析策略。
abstract class SourceAdapter {
  /// 解析播放源
  ///
  /// 将输入的参数解析为统一的PlayableSource对象。
  ///
  /// [input] 包含播放信息的输入参数，可能包含：
  ///   - fileId: 文件ID
  ///   - asset: 资源对象
  ///   - candidates: 备选资源列表
  ///   - detail: 详细信息对象
  ///
  /// [api] API客户端，用于请求播放链接和获取播放进度
  ///
  /// 返回可用于播放的PlayableSource对象
  ///
  /// 抛出Exception当无法解析出有效的播放源时
  Future<PlayableSource> resolve(Map<String, dynamic> input, ApiClient api);
}

/// 默认播放源适配器实现
///
/// 提供标准的播放源解析逻辑，支持多种输入格式和数据源。
/// 主要特点：
/// - 优先使用fileId请求后端播放接口
/// - 支持Web平台的Basic Auth URL注入
/// - 支持过期URL的自动刷新
/// - 支持续播功能
class DefaultSourceAdapter implements SourceAdapter {
  @override
  Future<PlayableSource> resolve(
      Map<String, dynamic> input, ApiClient api) async {
    // 已去播放链接化：不直接使用 playurl 入参，统一通过后端获取

    // 解析输入参数
    final dynamic asset = input['asset'];  // 资源对象
    final List<dynamic> candidates =       // 备选资源列表
        (input['candidates'] as List<dynamic>?) ?? const [];
    final dynamic detail = input['detail']; // 详细信息

    // 尝试从多个来源获取fileId
    final int? fileId = input['fileId'] as int? ??
        (asset is Map
            ? (asset['fileId'] as int?) ?? (asset['file_id'] as int?)
            : (asset?.fileId as int?));

    /// 清理URL字符串的辅助函数
    /// 移除可能存在的反引号包围符
    String? cleanUrl(String? s) {
      if (s == null) return null;
      var t = s.trim();
      if (t.startsWith('`')) t = t.substring(1).trimLeft();
      if (t.endsWith('`')) t = t.substring(0, t.length - 1).trimRight();
      return t;
    }

    // 仅凭 fileId 请求后端播放接口生成预签名 URL
    int? fallbackFileId = fileId;

    // 如果主fileId为空，尝试从备选列表中查找
    if (fallbackFileId == null) {
      for (final c in candidates) {
        try {
          if (c is Map) {
            // Map格式的备选资源
            final fid = (c['fileId'] as int?) ?? (c['file_id'] as int?);
            if (fid != null) {
              fallbackFileId = fid;
              break;
            }
          } else {
            // 对象格式的备选资源
            final fid = c.fileId as int?;
            if (fid != null) {
              fallbackFileId = fid;
              break;
            }
          }
        } catch (_) {
          // 忽略解析错误，继续尝试下一个
        }
      }
    }
    // 如果仍未找到fileId，尝试从detail对象中解析
    if (fallbackFileId == null && detail != null) {
      try {
        // 兼容 Map 结构的 detail
        if (detail is Map<String, dynamic>) {
          // 解析版本-资源结构（适用于电影、单集内容）
          final versions = (detail['versions'] as List?) ?? const [];
          for (final v in versions) {
            final assets = (v is Map) ? (v['assets'] as List?) : const [];
            if (assets == null) continue;

            // 遍历资源列表，查找视频类型的fileId
            for (final a in assets) {
              if (a is Map) {
                final t = (a['type'] as String?)?.toLowerCase();
                final fid = (a['file_id'] as int?) ?? (a['fileId'] as int?);
                // 优先选择视频资源，或者类型为空的资源
                if (fid != null && (t == null || t == 'video')) {
                  fallbackFileId = fid;
                  break;
                }
              }
            }
            if (fallbackFileId != null) break;
          }

          // 如果在版本中未找到，尝试解析剧集结构（适用于电视剧）
          if (fallbackFileId == null) {
            final seasons = (detail['seasons'] as List?) ?? const [];
            for (final s in seasons) {
              final eps = (s is Map) ? (s['episodes'] as List?) : const [];
              if (eps == null) continue;

              // 遍历剧集
              for (final e in eps) {
                final assets = (e is Map) ? (e['assets'] as List?) : const [];
                if (assets == null) continue;

                // 遍历剧集资源，查找视频类型的fileId
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
          // 兼容对象结构的 detail（如 MediaDetail 实例）
          final v = (detail as dynamic).versions as List?;
          if (v != null) {
            for (final it in v) {
              try {
                final assets = (it as dynamic).assets as List?;
                if (assets != null) {
                  for (final a in assets) {
                    final t = (a as dynamic).type as String?;
                    final fid = (a as dynamic).fileId as int?;
                    // 同样优先选择视频资源
                    if (fid != null &&
                        (t == null || t.toLowerCase() == 'video')) {
                      fallbackFileId = fid;
                      break;
                    }
                  }
                }
                if (fallbackFileId != null) break;
              } catch (_) {
                // 忽略解析错误，继续尝试
              }
            }
          }
        }
      } catch (_) {
        // 解析detail失败，静默处理
      }
    }
    // 如果找到了有效的fileId，请求播放链接
    if (fallbackFileId != null) {
      int? startPositionMs;

      // 获取播放进度以支持续播
      try {
        final v = await api.getPlaybackProgress(fallbackFileId);
        startPositionMs = (v != null && v > 0) ? v : null;
      } catch (_) {
        // 获取进度失败，从头开始播放
      }

      // 请求播放URL
      Map<String, dynamic> data = await api.getPlayUrl(fallbackFileId);
      final got = cleanUrl(data['playurl'] as String?);

      // 解析HTTP头
      Map<String, String>? hdrs;
      try {
        final raw = data['headers'];
        if (raw is Map) {
          hdrs = raw.map((k, v) => MapEntry('$k', '$v'));
        }
      } catch (_) {}

      // 解析过期时间
      final int? exp = data['expires_at'] as int?;
      final DateTime? expiresAt =
          exp != null ? DateTime.fromMillisecondsSinceEpoch(exp * 1000) : null;

      if (got != null && got.isNotEmpty) {
        // 过期刷新策略：若存在 expires_at 且即将过期（5秒内），自动刷新
        try {
          final exp = data['expires_at'] as int?;
          if (exp != null) {
            final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
            // 如果URL将在5秒内过期，自动刷新
            if (exp <= now + 5) {
              data = await api.refreshPlayUrl(fallbackFileId);
            }
          }
        } catch (_) {
          // 刷新失败，使用原URL
        }

        String url = got;

        // Web平台特殊处理：将Basic Auth信息注入URL
        // 因为浏览器无法设置自定义请求头，所以需要将认证信息放在URL中
        if (kIsWeb && hdrs != null) {
          final auth = hdrs['Authorization'];
          final m =
              auth != null ? RegExp(r'^Basic\s+(.+)$').firstMatch(auth) : null;

          if (m != null) {
            try {
              // 解码Basic Auth信息
              final raw = utf8.decode(base64Decode(m.group(1)!));
              final i = raw.indexOf(':');

              if (i > 0) {
                // 重新构建URL，将用户名密码注入userInfo部分
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
            } catch (_) {
              // URL注入失败，使用原URL
            }
          }
        }

        // 返回构建好的PlayableSource对象
        return PlayableSource(
            uri: url,
            headers: hdrs,           // 在Web平台下，headers主要用于非Basic Auth的信息
            format: data['format'] as String?,
            expiresAt: expiresAt,
            fileId: fallbackFileId,
            startPositionMs: startPositionMs);
      }
    }

    // 无法解析出有效的播放源
    throw Exception('no_play_source');
  }
}
