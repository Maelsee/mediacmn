import 'dart:convert';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:flutter/foundation.dart';
import 'package:hive_flutter/hive_flutter.dart';

import '../../media_library/media_models.dart';

class DesktopPlayerWindowService {
  static const _playerWindowType = 'player';

  static bool get isSupported {
    if (kIsWeb) return false;
    switch (defaultTargetPlatform) {
      case TargetPlatform.windows:
      case TargetPlatform.macOS:
      case TargetPlatform.linux:
        return true;
      default:
        return false;
    }
  }

  static Future<void> open({
    required String coreId,
    required Map<String, dynamic> extra,
  }) async {
    if (!isSupported) return;

    final payload = <String, dynamic>{
      'coreId': coreId,
      'extra': _normalizeExtra(extra),
      // 说明：桌面端多窗口会启动新的 Flutter 引擎（同进程不同引擎）。
      // Hive 的 box 文件存在进程级文件锁（例如 auth.lock），多个引擎同时打开同一路径会失败。
      // 这里将主窗口已登录态（token 等）打包传给新窗口，避免新窗口再去抢占同一个 auth box。
      'auth': _readAuthSnapshot(),
    };

    final existing = await _findExistingPlayerWindow();
    if (existing != null) {
      await existing.show();
      try {
        await existing.invokeMethod('open', payload);
      } catch (_) {}
      return;
    }

    final args = jsonEncode({
      'type': _playerWindowType,
      'payload': payload,
    });

    final controller = await WindowController.create(
      WindowConfiguration(arguments: args, hiddenAtLaunch: true),
    );
    await controller.show();
  }

  static Future<WindowController?> _findExistingPlayerWindow() async {
    try {
      final windows = await WindowController.getAll();
      for (final w in windows) {
        final raw = w.arguments;
        if (raw.isEmpty) continue;
        final decoded = jsonDecode(raw);
        if (decoded is! Map) continue;
        final type = decoded['type']?.toString();
        if (type == _playerWindowType) return w;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  static Map<String, dynamic> _normalizeExtra(Map<String, dynamic> extra) {
    final normalized = <String, dynamic>{};
    for (final entry in extra.entries) {
      normalized[entry.key] = _encodeValue(entry.value);
    }
    return normalized;
  }

  static Map<String, dynamic> _readAuthSnapshot() {
    try {
      if (!Hive.isBoxOpen('auth')) return const {};
      final box = Hive.box('auth');
      final token = box.get('token') as String?;
      final refreshToken = box.get('refresh_token') as String?;
      final tokenType = box.get('token_type') as String?;
      final expMs = box.get('token_expires_at') as int?;
      final expiresIn = expMs == null
          ? null
          : DateTime.fromMillisecondsSinceEpoch(expMs)
              .difference(DateTime.now())
              .inSeconds
              .clamp(0, 1 << 30);

      return {
        if (token != null) 'token': token,
        if (refreshToken != null) 'refresh_token': refreshToken,
        if (tokenType != null) 'token_type': tokenType,
        if (expiresIn != null) 'expires_in': expiresIn,
      };
    } catch (_) {
      return const {};
    }
  }

  static dynamic _encodeValue(dynamic value) {
    if (value == null) return null;
    if (value is num || value is bool || value is String) return value;
    if (value is Map) {
      return value.map((k, v) => MapEntry(k.toString(), _encodeValue(v)));
    }
    if (value is List) {
      return value.map(_encodeValue).toList();
    }
    if (value is MediaDetail) {
      return {
        'id': value.id,
        'title': value.title,
        'media_type': value.mediaType,
        'poster_path': value.posterPath,
        'backdrop_path': value.backdropPath,
      };
    }
    if (value is EpisodeDetail) {
      return {
        'id': value.id,
        'episode_number': value.episodeNumber,
        'title': value.title,
        'runtime': value.runtime,
        'runtime_text': value.runtimeText,
        'assets': value.assets.map(_encodeValue).toList(),
        'technical': _encodeValue(value.technical),
        'still_path': value.stillPath,
      };
    }
    if (value is AssetItem) {
      return {
        'file_id': value.fileId,
        'path': value.path,
        'type': value.type,
        'size': value.size,
        'size_text': value.sizeText,
        'storage': value.storageItem == null
            ? null
            : {
                'name': value.storageItem!.storageName,
                'type': value.storageItem!.storageType,
              },
      };
    }
    return value.toString();
  }
}
