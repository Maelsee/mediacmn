import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';
import '../core/api_client.dart';
import 'player_core.dart';
import 'source_adapter.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../media_library/media_provider.dart';
import 'player_view.dart';

/// 媒体播放页面
///
/// 提供完整的媒体播放功能，包括：
/// - 播放源解析和加载
/// - 播放进度上报（心跳机制）
/// - 错误处理和重试机制
/// - 续播功能
/// - 页面生命周期管理
class PlayPage extends StatefulWidget {
  /// 核心ID
  /// 通常对应媒体内容的ID，用于获取详细信息
  final String coreId;

  /// 额外参数
  /// 包含播放所需的各种信息，如fileId、asset、candidates、detail等
  final Object? extra;

  const PlayPage({super.key, required this.coreId, this.extra});

  @override
  State<PlayPage> createState() => _PlayPageState();
}

class _PlayPageState extends State<PlayPage> {
  /// 播放器核心实例
  late final PlayerCore _core;

  /// 错误信息
  /// 用于显示加载或播放失败的原因
  String? _error;

  /// 最后一次播放的文件ID
  /// 用于进度上报和页面销毁时的状态记录
  int? _lastFileId;

  /// 最后一次使用的详细信息对象
  /// 用于进度上报时的媒体类型识别
  Object? _lastDetail;

  @override
  void initState() {
    super.initState();
    // 初始化播放器核心
    _core = PlayerCore(Player());
    // 开始初始化播放
    _init();
  }

  /// 初始化播放
  ///
  /// 解析传入的参数，获取fileId，请求播放链接并开始播放。
  /// 支持多种数据源和参数格式。
  Future<void> _init() async {
    try {
      final extra = widget.extra as Map<String, dynamic>?;

      // 第一优先级：从路由参数中直接获取fileId
      int? fileId;
      if (extra != null) {
        if (extra.containsKey('fileId')) {
          fileId = extra['fileId'] as int?;
        } else if (extra.containsKey('file_id')) {
          fileId = extra['file_id'] as int?;
        }
      }

      // 第二优先级：从asset对象中获取fileId
      if (fileId == null && extra != null && extra.containsKey('asset')) {
        final asset = extra['asset'];
        if (asset is Map) {
          // Map格式的asset
          fileId = (asset['fileId'] as int?) ?? (asset['file_id'] as int?);
        } else {
          try {
            // 对象格式的asset
            fileId = (asset as dynamic).fileId as int?;
          } catch (_) {
            // 解析失败，fileId保持null
          }
        }
      }

      // 准备API客户端和其他参数
      final api = ApiClient();
      final candidates = (extra != null && extra['candidates'] is List)
          ? (extra['candidates'] as List)
          : const [];
      Object? dObj = (extra != null) ? extra['detail'] : null;
      Map<String, dynamic>? dMap;

      // 尝试将detail对象解析为Map格式
      if (dObj is Map<String, dynamic>) {
        dMap = dObj;
      } else if (dObj != null) {
        try {
          // 尝试调用toJson()方法（适用于模型对象）
          final any = (dObj as dynamic).toJson();
          if (any is Map<String, dynamic>) {
            dMap = any;
          }
        } catch (_) {
          // toJson()调用失败，保持dObj原样
        }
      }

      // 第三优先级：通过coreId获取详细信息
      // 如果没有detail且coreId有效，尝试从后端获取
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
            } catch (_) {
              // 转换失败，但获取到了detail对象
            }
          } catch (_) {
            // 获取详情失败不应阻塞播放尝试，只要有fileId即可
          }
        }
      }

      // 使用DefaultSourceAdapter解析播放源
      final src = await DefaultSourceAdapter().resolve({
        'fileId': fileId,
        'candidates': candidates,
        'detail': dMap ?? dObj,
      }, api);

      // 开始播放
      await _core.open(src);

      // 启动播放进度心跳上报
      _startProgressHeartbeat(src.fileId ?? fileId, detail: dMap ?? dObj);
    } catch (e) {
      // 显示错误信息
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
            mediaType = (detail['media_type'] as String?) ??
                (detail['kind'] as String?);
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
      body: _error != null
          ? Center(child: Text(_error!))
          : Center(
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: PlayerView(core: _core),
              ),
            ),
    );
  }
}
