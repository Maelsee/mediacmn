import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import 'media_models.dart';

/// 媒体详情数据 Provider
///
/// 功能：
/// - 按 `mediaId` 获取媒体详情数据
/// - 供详情页（MediaDetailPage）与手动匹配页（ManualMatchPage）共享同一份数据
/// - 支持手动刷新（invalidate）
final mediaDetailProvider = FutureProvider.family<MediaDetail, int>((
  ref,
  id,
) async {
  final api = ref.read(apiClientProvider);
  return api.getMediaDetail(id);
});
