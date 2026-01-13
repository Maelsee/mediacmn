import 'dart:async';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart';

import '../core/state/playback_state.dart';
import 'desktop_player_window_layout.dart';

class DesktopPlayerWindowPage extends ConsumerStatefulWidget {
  final Map<String, dynamic> initialPayload;

  const DesktopPlayerWindowPage({
    super.key,
    required this.initialPayload,
  });

  @override
  ConsumerState<DesktopPlayerWindowPage> createState() =>
      _DesktopPlayerWindowPageState();
}

class _DesktopPlayerWindowPageState
    extends ConsumerState<DesktopPlayerWindowPage> {
  WindowController? _window;
  StreamSubscription? _windowCloseSub;

  @override
  void initState() {
    super.initState();
    unawaited(_initWindow());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_openFromPayload(widget.initialPayload));
    });
  }

  @override
  void dispose() {
    _windowCloseSub?.cancel();
    super.dispose();
  }

  Future<void> _initWindow() async {
    await windowManager.ensureInitialized();
    await windowManager.waitUntilReadyToShow(
      const WindowOptions(
        size: Size(980, 620),
        minimumSize: Size(720, 420),
        center: true,
        backgroundColor: Colors.black,
        title: 'Media Player',
      ),
      () async {
        await windowManager.show();
        await windowManager.focus();
      },
    );

    try {
      _window = await WindowController.fromCurrentEngine();
      await _window!.setWindowMethodHandler((call) async {
        switch (call.method) {
          case 'focus':
            await windowManager.show();
            await windowManager.focus();
            return true;
          case 'open':
            final args = call.arguments;
            if (args is Map) {
              final map = args.cast<String, dynamic>();
              await _openFromPayload(map);
              return true;
            }
            return false;
          default:
            return null;
        }
      });
    } catch (_) {}
  }

  Future<void> _openFromPayload(Map<String, dynamic> payload) async {
    final coreId = payload['coreId']?.toString() ?? '';
    final extra = payload['extra'];
    final extraMap = extra is Map ? extra.cast<String, dynamic>() : const {};

    if (coreId.isEmpty) {
      ref.read(playbackProvider.notifier).showError('缺少 coreId');
      return;
    }

    await ref.read(playbackProvider.notifier).reload(coreId: coreId, extra: extraMap);
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Colors.black,
      body: DesktopPlayerWindowLayout(),
    );
  }
}

