import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import '../core/api_client.dart';
import 'player_core.dart';
import 'source_adapter.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../media_library/media_provider.dart';

class PlayPage extends StatefulWidget {
  final String coreId;
  final Object? extra;
  const PlayPage({super.key, required this.coreId, this.extra});
  @override
  State<PlayPage> createState() => _PlayPageState();
}

class _PlayPageState extends State<PlayPage> {
  late final PlayerCore _core;
  String? _error;
  int? _lastFileId;
  Object? _lastDetail;

  @override
  void initState() {
    super.initState();
    _core = PlayerCore(Player());
    _init();
  }

  Future<void> _init() async {
    try {
      final extra = widget.extra as Map<String, dynamic>?;
      // 优先从路由参数中获取 fileId
      int? fileId;
      if (extra != null) {
        if (extra.containsKey('fileId')) {
          fileId = extra['fileId'] as int?;
        } else if (extra.containsKey('file_id')) {
          fileId = extra['file_id'] as int?;
        }
      }

      // 如果没有直接传递 fileId，尝试从 asset 对象中获取
      if (fileId == null && extra != null && extra.containsKey('asset')) {
        final asset = extra['asset'];
        if (asset is Map) {
          fileId = (asset['fileId'] as int?) ?? (asset['file_id'] as int?);
        } else {
           try {
             fileId = (asset as dynamic).fileId as int?;
           } catch (_) {}
        }
      }

      final api = ApiClient();
      final candidates = (extra != null && extra['candidates'] is List)
          ? (extra['candidates'] as List)
          : const [];
      Object? dObj = (extra != null) ? extra['detail'] : null;
      Map<String, dynamic>? dMap;
      
      // 尝试解析 detail 对象为 Map
      if (dObj is Map<String, dynamic>) {
        dMap = dObj;
      } else if (dObj != null) {
        try {
          final any = (dObj as dynamic).toJson();
          if (any is Map<String, dynamic>) {
            dMap = any;
          }
        } catch (_) {}
      }

      // 如果没有 detail 或 detail 不完整，尝试通过 coreId 获取
      if (dObj == null) {
         final cid = int.tryParse(widget.coreId);
         if (cid != null && cid > 0) {
            try {
              final detail = await api.getMediaDetail(cid);
              dObj = detail;
               try {
                final any = (detail as dynamic).toJson();
                if (any is Map<String, dynamic>) {
                  dMap = any;
                }
              } catch (_) {}
            } catch (_) {
              // 获取详情失败不应阻塞播放尝试，只要有 fileId 即可
            }
         }
      }

      // 解析播放源
      final src = await DefaultSourceAdapter().resolve({
        'fileId': fileId,
        'candidates': candidates,
        'detail': dMap ?? dObj,
      }, api);

      await _core.open(src);
      _startProgressHeartbeat(src.fileId ?? fileId, detail: dMap ?? dObj);
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  Future<void> _startProgressHeartbeat(int? fileId, {Object? detail}) async {
    if (fileId == null) return;
    _lastFileId = fileId;
    _lastDetail = detail;
    final api = ApiClient();
    Duration interval = const Duration(seconds: 10);
    Future<void> tick() async {
      try {
        final pos = _core.player.state.position;
        final dur = _core.player.state.duration;
        String? mediaType;
        try {
          if (detail is Map<String, dynamic>) {
            mediaType = (detail['media_type'] as String?) ?? (detail['kind'] as String?);
          } else if (detail != null) {
            mediaType = (detail as dynamic).mediaType as String?;
          }
        } catch (_) {}
        await api.reportPlaybackProgress(
          fileId: fileId,
          coreId: (detail is Map<String, dynamic>)
              ? (detail['id'] as int?)
              : (detail != null ? (detail as dynamic).id as int? : null),
          positionMs: pos.inMilliseconds,
          durationMs: dur.inMilliseconds,
          status: 'playing',
          platform: 'web',
          mediaType: mediaType,
        );
      } catch (_) {}
    }

    await tick();

    void schedule() {
      Future.delayed(interval, () async {
        if (!mounted) return;
        await tick();
        schedule();
      });
    }

    schedule();
  }

  @override
  void dispose() {
    try {
      final fid = _lastFileId;
      if (fid != null) {
        final api = ApiClient();
        final pos = _core.player.state.position;
        final dur = _core.player.state.duration;
        final d = _lastDetail;
        String? mediaType;
        try {
          if (d is Map<String, dynamic>) {
            mediaType = (d['media_type'] as String?) ?? (d['kind'] as String?);
          } else if (d != null) {
            mediaType = (d as dynamic).mediaType as String?;
          }
        } catch (_) {}
        final coreId = d is Map<String, dynamic>
            ? (d['id'] as int?)
            : (d != null ? (d as dynamic).id as int? : null);
        api.reportPlaybackProgress(
          fileId: fid,
          coreId: coreId,
          positionMs: pos.inMilliseconds,
          durationMs: dur.inMilliseconds,
          status: 'stopped',
          platform: 'web',
          mediaType: mediaType,
        );
      }
    } catch (_) {}
    try {
      final container = ProviderScope.containerOf(context, listen: false);
      container.read(mediaHomeProvider.notifier).load();
    } catch (_) {}
    _core.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('播放')),
      body: _error != null
          ? Center(child: Text(_error!))
          : Center(
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: Video(controller: _core.controller),
              ),
            ),
    );
  }
}
