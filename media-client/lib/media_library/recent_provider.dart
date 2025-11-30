import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import 'media_models.dart';

class RecentState {
  /// 最近观看状态
  /// - `items`: 最近观看的媒体条目列表（后端精简字段映射到 `RecentCardItem`）
  /// - `loading`: 是否正在加载
  /// - `error`: 加载失败错误信息
  final List<RecentCardItem> items;
  final bool loading;
  final String? error;
  const RecentState({this.items = const [], this.loading = false, this.error});
}

class RecentNotifier extends StateNotifier<RecentState> {
  final ApiClient api;
  RecentNotifier(this.api) : super(const RecentState());

  /// 加载最近观看列表
  /// - `limit`: 最大返回条数（默认 20）
  /// 会在未登录时返回空列表，避免触发未授权错误
  Future<void> load({int limit = 20}) async {
    if (!api.isLoggedIn) {
      state = const RecentState(items: []);
      return;
    }

    try {
      // 从后端获取最近观看列表（已按系列去重）
      final items = await api.getRecent(limit: limit);
      state = RecentState(items: items);
    } catch (e) {
      state = RecentState(error: '$e', items: state.items);
    }
  }
}

final recentProvider =
    StateNotifierProvider<RecentNotifier, RecentState>((ref) {
  final api = ref.watch(apiClientProvider);
  final n = RecentNotifier(api);
  // Remove automatic load() here to prevent side effects during provider initialization
  // The load() should be called explicitly by the UI
  return n;
});
