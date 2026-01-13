import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:media_kit/media_kit.dart';
import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'dart:convert';
import 'app.dart';
import 'core/api_client.dart';
import 'media_player/desktop_window/desktop_player_window_app.dart';

Future<void> main([List<String>? args]) async {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();

  final windowArgs = await _tryReadMultiWindowArguments();
  if (windowArgs != null && windowArgs['type'] == 'player') {
    final payload = windowArgs['payload'];
    // 说明：桌面端新窗口由新的 Flutter 引擎承载。
    // Hive 在桌面端会对 box 文件加进程级锁（例如 auth.lock），多个引擎共享默认目录会导致锁冲突并白屏。
    // 新窗口使用独立的 Hive 子目录，且不再打开 auth box；登录态由主窗口通过 arguments 透传。
    await Hive.initFlutter('player_window');

    final initialPayload = payload is Map
        ? payload.cast<String, dynamic>()
        : const <String, dynamic>{};
    final auth = initialPayload['auth'];
    final authMap =
        auth is Map ? auth.cast<String, dynamic>() : const <String, dynamic>{};

    final api = ApiClient();
    api.setToken(authMap['token']?.toString());
    api.setRefreshToken(authMap['refresh_token']?.toString());
    api.setTokenType(authMap['token_type']?.toString());
    final expiresIn = (authMap['expires_in'] as num?)?.toInt();
    api.setTokenExpiresIn(expiresIn);

    runApp(ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: DesktopPlayerWindowApp(initialPayload: initialPayload)));
    return;
  }

  await Hive.initFlutter();
  await Hive.openBox('auth');

  runApp(const ProviderScope(child: MediaClientApp()));
}

Future<Map<String, dynamic>?> _tryReadMultiWindowArguments() async {
  try {
    final controller = await WindowController.fromCurrentEngine();
    final raw = controller.arguments;
    if (raw.isEmpty) return null;
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return decoded.cast<String, dynamic>();
    return null;
  } catch (_) {
    return null;
  }
}
