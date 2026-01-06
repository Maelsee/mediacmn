import '../api_client.dart';
import 'models.dart';

/// 播放历史的远端数据源封装。
///
/// 说明：
/// - 统一对 ApiClient 的播放历史相关接口进行适配。
/// - 上层通过 Repository 决定何时调用，避免 UI 或播放器状态层直接打网。
class RemotePlaybackDataSource {
  /// 网络 API 客户端。
  final ApiClient api;

  const RemotePlaybackDataSource({required this.api});

  /// 拉取指定文件的历史进度（毫秒）。
  Future<int?> fetchProgressMs(int fileId) => api.getPlaybackProgress(fileId);

  /// 上报一次播放进度。
  Future<void> reportProgress(ProgressReportTask task) {
    return api.reportPlaybackProgress(
      fileId: task.fileId,
      coreId: task.coreId,
      positionMs: task.positionMs,
      durationMs: task.durationMs,
      status: task.status,
      platform: task.platform,
      deviceId: task.deviceId,
      mediaType: task.mediaType,
    );
  }
}
