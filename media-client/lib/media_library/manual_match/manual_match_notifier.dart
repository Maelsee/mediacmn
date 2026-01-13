import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import '../../core/api_client.dart';
import '../media_models.dart';
import 'manual_match_models.dart';
import 'manual_match_state.dart';

class ManualMatchNotifier extends StateNotifier<ManualMatchState> {
  final ApiClient api;
  final int mediaId;

  ManualMatchNotifier(this.api, this.mediaId) : super(const ManualMatchState());

  /// 初始化文件列表（从详情页传入）
  /// [detail] 详情数据
  /// [seasonIndex] 当前详情页选中的季索引（仅 TV 有效）
  /// [versionIndex] 当前详情页选中的版本索引
  void initFiles(MediaDetail detail,
      {int seasonIndex = 0, int versionIndex = 0}) {
    final List<ManualMatchFileItem> files = [];
    int? localMediaId;
    int? localMediaVersionId;
    String? filePathHint;

    if (detail.mediaType == 'movie') {
      localMediaId = detail.id;
      // 电影：只取选中的版本
      if (detail.versions != null && detail.versions!.isNotEmpty) {
        final vIdx = versionIndex.clamp(0, detail.versions!.length - 1);
        final version = detail.versions![vIdx];
        localMediaVersionId = version.id;

        if (version.assets.isNotEmpty) {
          filePathHint = version.assets.first.path;
        }

        for (final asset in version.assets) {
          // 简单起见，暂不严格过滤 type='video'，因为后端可能没返 type
          // 但为了体验，尽量过滤
          if (asset.type == 'video' || asset.type.isEmpty) {
            files.add(_mapAsset(asset, null, null, null));
          }
        }
      }
    } else {
      // TV：扁平化选中季、选中版本的所有 episodes -> assets
      if (detail.seasons != null && detail.seasons!.isNotEmpty) {
        final idx = seasonIndex.clamp(0, detail.seasons!.length - 1);
        final season = detail.seasons![idx];
        localMediaId = season.id;

        if (season.versions != null && season.versions!.isNotEmpty) {
          final vIdx = versionIndex.clamp(0, season.versions!.length - 1);
          final version = season.versions![vIdx];
          localMediaVersionId = version.id;
          if (version.seasonVersionPath?.isNotEmpty == true) {
            filePathHint = version.seasonVersionPath;
          }

          for (final ep in version.episodes) {
            for (final asset in ep.assets) {
              if (asset.type == 'video' || asset.type.isEmpty) {
                files.add(_mapAsset(
                    asset, season.seasonNumber, ep.episodeNumber, ep.title));
              }
            }
          }

          if (filePathHint == null && files.isNotEmpty) {
            filePathHint = files.first.path;
          }
        }
      }
    }

    state = state.copyWith(
        fileItems: files,
        filePathHint: filePathHint,
        localMediaId: localMediaId,
        localMediaVersionId: localMediaVersionId);
  }

  ManualMatchFileItem _mapAsset(
      AssetItem asset, int? seasonNum, int? epNum, String? epTitle) {
    return ManualMatchFileItem(
      fileId: asset.fileId,
      path: asset.path,
      displayName: asset.path.split('/').last.split('\\').last,
      storageName: asset.storageItem?.storageName,
      currentSeasonNumber: seasonNum,
      currentEpisodeNumber: epNum,
      currentEpisodeTitle: epTitle,
    );
  }

  /// 搜索 TMDB
  Future<void> search(String query) async {
    if (query.isEmpty) return;
    state =
        state.copyWith(searching: true, query: query, clearSearchError: true);
    try {
      // 默认搜索 multi 或分别搜 movie/tv？需求说“输入电影或电视剧名称”，
      // 且 UI 结果混排。这里调用 searchTmdb 传 'multi' 或者前端根据 tab 分开？
      // 简化：传 'multi' 如果后端支持，或者默认搜 'tv' 和 'movie' 并发？
      // 根据 ApiClient 定义，我们传 'multi' 试试，如果后端不支持则需改。
      // 假设后端支持 'multi'，或者我们分别搜。
      // 这里的 ApiClient.searchTmdb 接收 type。
      // 为了稳妥，我们可以先搜 tv 再搜 movie 合并，或者看后端实现。
      // 假设 type 参数是必须的 'movie' 或 'tv'。
      // 我们并发搜两个吧，然后合并。
      final results = <TmdbSearchItem>[];

      // 并发请求，但独立处理错误，防止一方 404 导致整个搜索失败
      final movieFuture = api.searchTmdb(query, 'movie').then((res) {
        return (res['items'] as List? ?? []).map((e) {
          final item = Map<String, dynamic>.from(e);
          item['type'] = 'movie';
          return TmdbSearchItem.fromJson(item);
        }).toList();
      }).catchError((e) {
        // 忽略 Movie 接口错误（如 404），返回空列表
        return <TmdbSearchItem>[];
      });

      final tvFuture = api.searchTmdb(query, 'tv').then((res) {
        return (res['items'] as List? ?? []).map((e) {
          final item = Map<String, dynamic>.from(e);
          item['type'] = 'tv';
          return TmdbSearchItem.fromJson(item);
        }).toList();
      }).catchError((e) {
        // 记录 TV 接口错误，但在 catchError 中返回空列表，避免中断
        // 如果两个都空，用户界面会显示无结果
        return <TmdbSearchItem>[];
      });

      final outcomes = await Future.wait([movieFuture, tvFuture]);
      results.addAll(outcomes[0]);
      results.addAll(outcomes[1]);

      state = state.copyWith(searching: false, searchResults: results);
    } catch (e) {
      state = state.copyWith(searching: false, searchError: e.toString());
    }
  }

  /// 选中 TMDB 条目
  Future<void> selectTmdbItem(TmdbSearchItem item) async {
    state = state.copyWith(
        selectedTmdbItem: item,
        seasonList: [],
        episodeList: [],
        selectedSeason: null);

    // 如果是 TV，拉取季列表
    if (item.type == 'tv') {
      state = state.copyWith(loadingSeasons: true);
      try {
        final res = await api.getTmdbTvSeasons(item.tmdbId);
        final list = (res['seasons'] as List? ?? [])
            .map((e) => TmdbSeasonItem.fromJson(e))
            .toList();
        state = state.copyWith(loadingSeasons: false, seasonList: list);
      } catch (e) {
        state =
            state.copyWith(loadingSeasons: false, searchError: '获取季列表失败: $e');
      }
    } else {
      // Movie，直接进入匹配模式（不需要选季）
      // 默认把所有文件绑定到该 Movie
      final newDraft = <int, ManualMatchChoice>{};
      for (final f in state.fileItems) {
        newDraft[f.fileId] =
            ManualMatchChoice.bindMovie(tmdbMovieId: item.tmdbId);
      }
      state = state.copyWith(draftChoices: newDraft);
    }
  }

  /// 清除选中状态（回到搜索结果页）
  void clearSelection() {
    state = state.copyWith(
      clearSelectedTmdbItem: true,
      seasonList: [],
      episodeList: [],
      selectedSeason: null,
      draftChoices: {},
      // 保持 query 和 searchResults 不变，以便用户继续浏览
    );
  }

  /// 选中 TV 的季
  Future<void> selectSeason(TmdbSeasonItem season) async {
    if (state.selectedTmdbItem == null) return;
    state = state.copyWith(selectedSeason: season, loadingEpisodes: true);

    try {
      final res = await api.getTmdbTvSeasonEpisodes(
          state.selectedTmdbItem!.tmdbId, season.seasonNumber);
      final list = (res['episodes'] as List? ?? [])
          .map((e) => TmdbEpisodeItem.fromJson(e))
          .toList();
      state = state.copyWith(loadingEpisodes: false, episodeList: list);

      // 智能预选（可选）：按文件名里的集号匹配？
      // 暂时先全部置空，或保持“暂不改动”
      // 需求：下面 listview 中都是视频文件条目...为每一个视频文件选择集信息。
      // 初始状态下，draft 为空，UI 显示“暂不改动”或原状态。
    } catch (e) {
      state =
          state.copyWith(loadingEpisodes: false, searchError: '获取集列表失败: $e');
    }
  }

  /// 更新某个文件的绑定选择
  void updateChoice(int fileId, ManualMatchChoice choice) {
    final newDraft = Map<int, ManualMatchChoice>.from(state.draftChoices);
    newDraft[fileId] = choice;
    state = state.copyWith(draftChoices: newDraft);
  }

  /// 保存
  Future<bool> save() async {
    if (state.saving) return false;

    // 校验：必须选中 TMDB 条目
    if (state.selectedTmdbItem == null) {
      state = state.copyWith(saveError: '请先选择 TMDB 影片');
      return false;
    }

    // TV 必须选中季
    if (state.selectedTmdbItem!.type == 'tv' && state.selectedSeason == null) {
      state = state.copyWith(saveError: '请先选择季');
      return false;
    }

    state = state.copyWith(saving: true, clearSaveError: true);

    try {
      final target = <String, dynamic>{
        'type': state.selectedTmdbItem!.type,
        'provider': 'tmdb',
        if (state.localMediaId != null) 'local_media_id': state.localMediaId,
        if (state.localMediaVersionId != null)
          'local_media_version_id': state.localMediaVersionId,
      };

      if (state.selectedTmdbItem!.type == 'tv') {
        target['tmdb_tv_id'] = state.selectedTmdbItem!.tmdbId;
        target['season_number'] = state.selectedSeason!.seasonNumber;
        if (state.selectedSeason!.tmdbSeasonId != null) {
          target['tmdb_season_id'] = state.selectedSeason!.tmdbSeasonId;
        }
      } else {
        target['tmdb_movie_id'] = state.selectedTmdbItem!.tmdbId;
      }

      final items = state.draftChoices.entries.map((e) {
        return {
          'file_id': e.key,
          ...e.value.toJson(),
        };
      }).toList();

      // 如果 items 为空（用户没做任何改变），是否提交？
      // 需求：默认只上传“用户明确变更过”的 file。
      // 如果 draftChoices 为空，说明没变。
      // 但这里我们只把 draftChoices 里的传上去。
      // 另外，那些没有在 draftChoices 里的 file，视作 keep，不传。

      final payload = {
        'target': target,
        'items': items,
        'client_request_id': const Uuid().v4(),
      };

      final res = await api.saveManualMatch(mediaId, payload);
      final taskId = res['task_id'] as String?;

      if (taskId != null && taskId.isNotEmpty) {
        // 轮询任务状态，直到完成
        while (true) {
          await Future.delayed(const Duration(milliseconds: 500));
          try {
            final taskStatus = await api.getTaskStatus(taskId);
            var status = taskStatus['status'] as String?;
            // 如果根节点没有 status，尝试从 task 对象中获取
            if (status == null && taskStatus.containsKey('task')) {
              final taskObj = taskStatus['task'];
              if (taskObj is Map) {
                status = taskObj['status'] as String?;
              }
            }
            if (status == 'done' || status == 'success') {
              break;
            }
            if (status == 'failed' || status == 'cancelled') {
              throw Exception('后台任务执行失败: $status');
            }
            // other statuses: pending, running, etc. -> continue waiting
          } catch (e) {
            // 如果获取状态失败，可能是临时的，也可能是任务不存在
            // 这里选择抛出异常还是继续重试？为了安全，如果连续失败应该退出
            // 简单起见，这里抛出
            rethrow;
          }
        }
      }

      state = state.copyWith(saving: false);
      return true;
    } catch (e) {
      state = state.copyWith(saving: false, saveError: e.toString());
      return false;
    }
  }
}
