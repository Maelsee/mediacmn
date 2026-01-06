import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/playback_history/providers.dart';
import '../core/playback_history/recent_repository.dart';
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
  /// 最近观看仓库。
  final RecentRepository _repository;

  RecentNotifier(this._repository) : super(const RecentState());

  /// 加载最近观看列表
  /// - `limit`: 最大返回条数（默认 20）
  /// 会在未登录时返回空列表，避免触发未授权错误
  Future<void> load({int limit = 20}) async {
    try {
      final items = await _repository.getRecent(limit: limit);
      state = RecentState(items: items);
    } catch (e) {
      state = RecentState(error: '$e', items: state.items);
    }
  }
}

final recentProvider =
    StateNotifierProvider<RecentNotifier, RecentState>((ref) {
  final repo = ref.watch(recentRepositoryProvider);
  return RecentNotifier(repo);
});
