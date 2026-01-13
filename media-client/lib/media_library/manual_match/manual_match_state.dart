import 'manual_match_models.dart';

class ManualMatchState {
  /// 搜索相关
  final String query;
  final bool searching;
  final List<TmdbSearchItem> searchResults;
  final String? searchError;

  /// 选中目标相关
  final TmdbSearchItem? selectedTmdbItem; // 当前选中的 TV 或 Movie
  final bool loadingSeasons; // 正在加载季列表
  final List<TmdbSeasonItem> seasonList; // TV 的季列表

  /// TV 季选择
  final TmdbSeasonItem? selectedSeason; // 当前选中的季
  final bool loadingEpisodes; // 正在加载集列表
  final List<TmdbEpisodeItem> episodeList; // 当前季的所有集

  /// 文件列表（从详情页初始化）
  final List<ManualMatchFileItem> fileItems;
  final String? filePathHint;
  final int? localMediaId; // 当前选中的本地季ID (TV) 或 电影ID (Movie)
  final int? localMediaVersionId; // 当前选中的本地版本ID

  /// 绑定草稿：fileId -> Choice
  final Map<int, ManualMatchChoice> draftChoices;

  /// 保存状态
  final bool saving;
  final String? saveError;

  const ManualMatchState({
    this.query = '',
    this.searching = false,
    this.searchResults = const [],
    this.searchError,
    this.selectedTmdbItem,
    this.loadingSeasons = false,
    this.seasonList = const [],
    this.selectedSeason,
    this.loadingEpisodes = false,
    this.episodeList = const [],
    this.fileItems = const [],
    this.filePathHint,
    this.localMediaId,
    this.localMediaVersionId,
    this.draftChoices = const {},
    this.saving = false,
    this.saveError,
  });

  ManualMatchState copyWith({
    String? query,
    bool? searching,
    List<TmdbSearchItem>? searchResults,
    String? searchError, // 允许置空，需特殊处理
    bool clearSearchError = false,
    TmdbSearchItem? selectedTmdbItem,
    bool clearSelectedTmdbItem = false,
    bool? loadingSeasons,
    List<TmdbSeasonItem>? seasonList,
    TmdbSeasonItem? selectedSeason,
    bool? loadingEpisodes,
    List<TmdbEpisodeItem>? episodeList,
    List<ManualMatchFileItem>? fileItems,
    String? filePathHint,
    int? localMediaId,
    int? localMediaVersionId,
    Map<int, ManualMatchChoice>? draftChoices,
    bool? saving,
    String? saveError, // 允许置空
    bool clearSaveError = false,
  }) {
    return ManualMatchState(
      query: query ?? this.query,
      searching: searching ?? this.searching,
      searchResults: searchResults ?? this.searchResults,
      searchError: clearSearchError ? null : (searchError ?? this.searchError),
      selectedTmdbItem: clearSelectedTmdbItem
          ? null
          : (selectedTmdbItem ?? this.selectedTmdbItem),
      loadingSeasons: loadingSeasons ?? this.loadingSeasons,
      seasonList: seasonList ?? this.seasonList,
      selectedSeason: selectedSeason ?? this.selectedSeason,
      loadingEpisodes: loadingEpisodes ?? this.loadingEpisodes,
      episodeList: episodeList ?? this.episodeList,
      fileItems: fileItems ?? this.fileItems,
      filePathHint: filePathHint ?? this.filePathHint,
      localMediaId: localMediaId ?? this.localMediaId,
      localMediaVersionId: localMediaVersionId ?? this.localMediaVersionId,
      draftChoices: draftChoices ?? this.draftChoices,
      saving: saving ?? this.saving,
      saveError: clearSaveError ? null : (saveError ?? this.saveError),
    );
  }
}
