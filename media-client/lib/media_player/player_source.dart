import '../core/api_client.dart';

/// 可播放媒体源模型
///
/// 封装媒体播放所需的所有信息，包括URI、请求头、格式、过期时间等。
/// 该类为播放器提供了统一的播放源数据结构，支持多种媒体格式和播放场景。
class PlayableSource {
  /// 媒体资源的URI地址
  /// 可以是HTTP/HTTPS链接、本地文件路径或其他支持的协议
  final String uri;

  /// HTTP请求头
  /// 用于媒体播放时的身份验证、防盗链等
  /// 在Web平台下会进行特殊处理以兼容浏览器限制
  final Map<String, String>? headers;

  /// 媒体格式
  /// 例如：'hls'、'mp4'、'webm'等
  /// 用于播放器选择合适的解码器
  final String? format;

  /// 链接过期时间
  /// 用于临时URL的过期检查和自动刷新
  /// 通常在预签名URL场景中使用
  final DateTime? expiresAt;

  /// 文件ID
  /// 媒体资源在数据库中的唯一标识
  /// 用于进度上报、播放历史记录等功能
  final int? fileId;

  /// 开始播放位置（毫秒）
  /// 用于续播功能，记录用户上次播放的位置
  /// 值为0或null时从头开始播放
  final int? startPositionMs;

  const PlayableSource({
    required this.uri,
    this.headers,
    this.format,
    this.expiresAt,
    this.fileId,
    this.startPositionMs,
  });
}

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
    // 1. 提取文件ID (File ID)
    final int? fileId = _extractFileId(input);

    if (fileId == null) {
      throw Exception('无法找到有效的文件ID (No valid fileId found)');
    }

    // 2. 获取播放信息 (Play URL & Progress)
    return await _fetchPlayData(fileId, api);
  }

  /// 从输入参数中提取文件ID
  ///
  /// 按照以下优先级查找：
  /// 1. 直接的 fileId 字段
  /// 2. asset 对象中的 fileId
  /// 3. candidates 列表中的 fileId
  /// 4. detail 对象中的视频资源 fileId
  int? _extractFileId(Map<String, dynamic> input) {
    // 1. 尝试直接获取
    if (input['fileId'] is int) return input['fileId'] as int;

    // 2. 尝试从 asset 获取
    final asset = input['asset'];
    if (asset != null) {
      final fid = _getFileIdFromObj(asset);
      if (fid != null) return fid;
    }

    // 3. 尝试从 candidates 获取
    final candidates = input['candidates'];
    if (candidates is List) {
      for (final c in candidates) {
        final fid = _getFileIdFromObj(c);
        if (fid != null) return fid;
      }
    }

    // 4. 尝试从 detail 获取
    final detail = input['detail'];
    if (detail != null) {
      return _extractFileIdFromDetail(detail);
    }

    return null;
  }

  /// 辅助方法：从对象（Map或Object）中获取 fileId
  int? _getFileIdFromObj(dynamic obj) {
    if (obj == null) return null;
    if (obj is Map) {
      return (obj['fileId'] as int?) ?? (obj['file_id'] as int?);
    }
    try {
      return (obj as dynamic).fileId as int?;
    } catch (_) {
      return null;
    }
  }

  /// 从 detail 对象中提取 fileId
  ///
  /// 支持解析版本(versions)、剧集(seasons/episodes)等结构
  int? _extractFileIdFromDetail(dynamic detail) {
    try {
      // 统一转换为 Map 处理
      Map<String, dynamic>? detailMap;
      if (detail is Map<String, dynamic>) {
        detailMap = detail;
      } else {
        try {
          // 尝试转换为 JSON Map
          final json = (detail as dynamic).toJson();
          if (json is Map<String, dynamic>) detailMap = json;
        } catch (_) {
          // 如果无法转换，尝试直接访问属性（较少见，通常 detail 是 Map 或 Model）
          return _extractFileIdFromDetailObject(detail);
        }
      }

      if (detailMap != null) {
        return _extractFileIdFromDetailMap(detailMap);
      }
    } catch (_) {
      // 忽略解析错误
    }
    return null;
  }

  /// 从 Detail Map 中提取
  int? _extractFileIdFromDetailMap(Map<String, dynamic> detail) {
    // 1. 检查 versions (电影/单集)
    final versions = detail['versions'];
    if (versions is List) {
      for (final v in versions) {
        if (v is Map) {
          final fid = _findVideoFileIdInAssets(v['assets']);
          if (fid != null) return fid;
        }
      }
    }

    // 2. 检查 seasons (电视剧)
    final seasons = detail['seasons'];
    if (seasons is List) {
      for (final s in seasons) {
        if (s is Map) {
          final episodes = s['episodes'];
          if (episodes is List) {
            for (final e in episodes) {
              if (e is Map) {
                final fid = _findVideoFileIdInAssets(e['assets']);
                if (fid != null) return fid;
              }
            }
          }
        }
      }
    }
    return null;
  }

  /// 针对 Object 类型的 detail 的备用提取逻辑
  int? _extractFileIdFromDetailObject(dynamic detail) {
    try {
      final versions = (detail as dynamic).versions as List?;
      if (versions != null) {
        for (final v in versions) {
          final assets = (v as dynamic).assets as List?;
          final fid = _findVideoFileIdInAssetsDynamic(assets);
          if (fid != null) return fid;
        }
      }
    } catch (_) {}
    return null;
  }

  /// 在 assets 列表中查找视频类型的 fileId (Map版本)
  int? _findVideoFileIdInAssets(dynamic assets) {
    if (assets is! List) return null;
    for (final a in assets) {
      if (a is Map) {
        final type = (a['type'] as String?)?.toLowerCase();
        final fid = (a['file_id'] as int?) ?? (a['fileId'] as int?);
        // 优先匹配 type == 'video'，或者 type 为空
        if (fid != null && (type == null || type == 'video')) {
          return fid;
        }
      }
    }
    return null;
  }

  /// 在 assets 列表中查找视频类型的 fileId (Dynamic对象版本)
  int? _findVideoFileIdInAssetsDynamic(List? assets) {
    if (assets == null) return null;
    for (final a in assets) {
      try {
        final type = (a as dynamic).type as String?;
        final fid = (a as dynamic).fileId as int?;
        if (fid != null && (type == null || type == 'video')) {
          return fid;
        }
      } catch (_) {}
    }
    return null;
  }

  /// 获取播放数据（URL和进度）
  Future<PlayableSource> _fetchPlayData(int fileId, ApiClient api) async {
    // 1. 获取播放链接
    final playUrlRes = await api.getPlayUrl(fileId);
    final String? url = playUrlRes['playurl'] ?? playUrlRes['url'];
    if (url == null) {
      throw Exception('无法获取播放链接 (Failed to get play URL)');
    }

    final Map<String, String>? headers =
        (playUrlRes['headers'] as Map?)?.cast<String, String>();

    // 2. 获取播放进度（续播）
    int startPosition = 0;
    try {
      final position = await api.getPlaybackProgress(fileId);
      if (position != null) {
        startPosition = position;
        // 如果进度接近结束（例如剩余不到5%或30秒），则从头开始
        // 这里暂时不处理，由用户决定
      }
    } catch (_) {
      // 获取进度失败不影响播放，默认从0开始
    }

    return PlayableSource(
      uri: url,
      headers: headers,
      fileId: fileId,
      startPositionMs: startPosition,
    );
  }
}
