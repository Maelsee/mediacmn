import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:convert';
import 'package:hive_flutter/hive_flutter.dart';
import '../core/api_client.dart';
// apiClientProvider 已从 core/api_client.dart 导出，无需额外引入 tasks 模块
import 'media_models.dart';

class MediaHomeState {
  /// 首页媒体库状态
  /// - `data`: 后端返回的首页卡片数据（分类、电影、剧集、最近）
  /// - `loading`: 是否处于加载中（用于展示加载指示器）
  /// - `error`: 加载失败时的错误信息
  final HomeCardsResponse? data;
  final bool loading;
  final String? error;
  const MediaHomeState({this.data, this.loading = false, this.error});
}

class MediaHomeNotifier extends StateNotifier<MediaHomeState> {
  final ApiClient api;
  MediaHomeNotifier(this.api) : super(const MediaHomeState());

  /// 加载首页媒体库数据
  /// 流程：
  /// 1. 若未登录则直接返回空状态
  /// 2. 读取 Hive 缓存并优先显示（提升首屏体验）
  /// 3. 调用后端刷新最新数据并更新状态和缓存
  Future<void> load() async {
    if (!api.isLoggedIn) {
      state = const MediaHomeState(loading: false);
      return;
    }
    final box = await Hive.openBox('library_home_box');
    final cached = box.get('home_cache_v2') as String?;
    if (cached != null && cached.isNotEmpty) {
      try {
        final json = jsonDecode(cached) as Map<String, dynamic>;
        final data = HomeCardsResponse.fromJson(json);
        state = MediaHomeState(data: data);
      } catch (_) {
        state = const MediaHomeState(loading: true);
      }
    } else {
      state = const MediaHomeState(loading: true);
    }
    try {
      // 获取后端最新首页卡片数据
      final fresh = await api.getLibraryHome();
      state = MediaHomeState(data: fresh);
      try {
        // 将简化后的结构写入缓存，降低解析成本
        final map = {
          'genres': fresh.genres
              .map((c) => {
                    'id': c.id,
                    'name': c.name,
                  })
              .toList(),
          'movie': fresh.movie
              .map((m) => {
                    'id': m.id,
                    'name': m.name,
                    'cover_url': m.coverUrl,
                    'rating': m.rating,
                    'release_date': m.releaseDate,
                    'media_type': m.mediaType,
                  })
              .toList(),
          'tv': fresh.tv
              .map((m) => {
                    'id': m.id,
                    'name': m.name,
                    'cover_url': m.coverUrl,
                    'rating': m.rating,
                    'release_date': m.releaseDate,
                    'media_type': m.mediaType,
                  })
              .toList(),
        };
        await box.put('home_cache_v2', jsonEncode(map));
      } catch (_) {}
    } catch (e) {
      state = MediaHomeState(error: '$e');
    }
  }
}

final mediaHomeProvider =
    StateNotifierProvider<MediaHomeNotifier, MediaHomeState>((ref) {
  final api = ref.watch(apiClientProvider);
  final n = MediaHomeNotifier(api);
  n.load();
  return n;
});
