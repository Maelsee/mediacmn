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
