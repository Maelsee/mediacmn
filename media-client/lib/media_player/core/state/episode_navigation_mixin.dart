import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../media_library/media_models.dart';
import 'playback_state.dart';

/// 剧集导航逻辑 mixin。
///
/// 从 PlaybackNotifier 中提取的剧集导航相关方法，
/// 包含：上一集/下一集计算、剧集索引查找、标题组装等。
mixin EpisodeNavigationMixin on StateNotifier<PlaybackState> {
  /// 路由入参中的原始标题（只在初始化时赋值一次）。
  String? get routeTitleHint;
  set routeTitleHint(String? value);

  /// 系列名称提示（从路由参数或详情中获取）。
  String? get seriesNameHint;
  set seriesNameHint(String? value);

  /// 季序号提示（从路由参数中获取）。
  int? get seasonIndexHint;
  set seasonIndexHint(int? value);

  /// 根据当前文件 ID 定位对应的选集条目。
  ///
  /// 优先按"每集首个资源 fileId"匹配；若未命中（例如从"最近观看"入口进入时，
  /// fileId 可能是某集的非首个资源），则回退在该集的所有资源中查找。
  EpisodeDetail? findEpisodeByFirstAssetFileId(int fileId) {
    // 第一步：按首个资源 fileId 快速匹配
    for (final e in state.episodes) {
      if (e.assets.isEmpty) continue;
      if (e.assets.first.fileId == fileId) return e;
    }

    // 第二步：兼容"最近观看"等入口，在所有资源中做完整扫描
    for (final e in state.episodes) {
      for (final a in e.assets) {
        if (a.fileId == fileId) return e;
      }
    }

    return null;
  }

  /// 获取用于上一集/下一集的 fileId 序列。
  ///
  /// 优先使用 state.episodes，若为空则回退使用 detail.seasons 结构。
  List<int> episodeFileIdList() {
    final fromState = <int>[];
    for (final e in state.episodes) {
      if (e.assets.isEmpty) continue;
      fromState.add(e.assets.first.fileId);
    }
    if (fromState.isNotEmpty) return fromState;

    final detail = state.detail;
    if (detail == null || detail.mediaType == 'movie') return const [];

    // 仅使用当前季的版本，避免跨季混排导致索引错位。
    final currentSeasonVersionId = state.seasonVersionId;
    for (final season in detail.seasons ?? const []) {
      for (final version in season.versions ?? const []) {
        if (currentSeasonVersionId != null &&
            version.id != currentSeasonVersionId) {
          continue;
        }
        final fromDetail = <int>[];
        for (final ep in version.episodes) {
          if (ep.assets.isEmpty) continue;
          fromDetail.add(ep.assets.first.fileId);
        }
        if (fromDetail.isNotEmpty) return fromDetail;
      }
    }

    // 最后兜底：返回所有季的 fileId（不应走到这里）。
    final fallback = <int>[];
    for (final season in detail.seasons ?? const []) {
      for (final version in season.versions ?? const []) {
        for (final ep in version.episodes) {
          if (ep.assets.isEmpty) continue;
          fallback.add(ep.assets.first.fileId);
        }
      }
    }
    return fallback;
  }

  /// 计算相邻剧集的 fileId。
  ///
  /// 始终基于 `state.episodes` 的顺序进行导航，避免因空资源集导致索引错位。
  int? resolveAdjacentEpisode({required bool previous}) {
    final current = state.fileId ?? state.currentEpisodeFileId;
    if (current == null) return null;

    final episodes = state.episodes;
    if (episodes.length <= 1) return null;

    // 在 episodes 中查找当前集的索引（搜索所有资源，兼容非首个资源的情况）。
    var idx = -1;
    for (var i = 0; i < episodes.length; i++) {
      for (final a in episodes[i].assets) {
        if (a.fileId == current) {
          idx = i;
          break;
        }
      }
      if (idx != -1) break;
    }
    if (idx == -1) return null;

    final nextIdx = previous ? idx - 1 : idx + 1;
    if (nextIdx < 0 || nextIdx >= episodes.length) return null;
    final nextEp = episodes[nextIdx];
    if (nextEp.assets.isEmpty) return null;
    return nextEp.assets.first.fileId;
  }

  /// 重新计算上一集/下一集导航状态。
  void recomputeEpisodeNav() {
    final current = state.fileId ?? state.currentEpisodeFileId;
    if (current == null) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }

    final ids = episodeFileIdList();
    if (ids.length <= 1) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }

    var idx = ids.indexOf(current);

    if (idx == -1) {
      final episodes = state.episodes;
      for (var i = 0; i < episodes.length; i++) {
        final ep = episodes[i];
        for (final a in ep.assets) {
          if (a.fileId == current) {
            idx = i;
            break;
          }
        }
        if (idx != -1) break;
      }
      if (idx == -1) {
        state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
        return;
      }
    }

    state = state.copyWith(
      hasPrevEpisode: idx > 0,
      hasNextEpisode: idx + 1 < ids.length,
    );
  }

  /// 同步当前剧集的标题到 state.title。
  void syncTitleForCurrentEpisode() {
    final keyFileId = state.currentEpisodeFileId ?? state.fileId;
    if (keyFileId == null) return;

    final episode = findEpisodeByFirstAssetFileId(keyFileId);
    if (episode == null) return;

    final nextTitle = composeEpisodeTitle(episode);
    if (nextTitle.isEmpty) return;
    if (state.title == nextTitle) return;

    state = state.copyWith(title: nextTitle);
  }

  /// 组装剧集标题（系列名 + 季 + 集 + 集名）。
  String composeEpisodeTitle(EpisodeDetail episode) {
    String name = '';
    final detail = state.detail;
    if (detail != null && detail.title.trim().isNotEmpty) {
      name = detail.title.trim();
    } else if (seriesNameHint != null && seriesNameHint!.trim().isNotEmpty) {
      name = seriesNameHint!.trim();
    }

    final parts = <String>[];
    if (name.isNotEmpty) parts.add(name);

    final seasonNo = currentSeasonNumber();
    if (seasonNo != null && seasonNo > 0) parts.add('第$seasonNo季');

    final epNo = episode.episodeNumber;
    if (epNo > 0) parts.add('第$epNo集');

    var epTitle = episode.title.trim();
    if (epTitle.isNotEmpty) {
      final prefix = RegExp(r'^第\\d+集\\s*');
      epTitle = epTitle.replaceFirst(prefix, '');
      if (epTitle.isNotEmpty) parts.add(epTitle);
    }

    return parts.isEmpty ? '' : parts.join(' ');
  }

  /// 获取当前播放的季序号。
  int? currentSeasonNumber() {
    final detail = state.detail;
    if (detail == null) {
      if (seasonIndexHint != null && seasonIndexHint! > 0) {
        return seasonIndexHint;
      }
      if (state.mediaType == 'tv' || state.mediaType == 'tv_episode') {
        return 1;
      }
      return null;
    }
    if (detail.mediaType != 'tv') return null;

    final vId = state.seasonVersionId;
    if (vId == null) return seasonIndexHint;

    for (final season in detail.seasons ?? const []) {
      for (final version in season.versions ?? const []) {
        if (version.id == vId) return season.seasonNumber;
      }
    }
    return seasonIndexHint;
  }
}
