/// TMDB 搜索结果条目模型
class TmdbSearchItem {
  final int tmdbId;
  final String type; // 'movie' | 'tv'
  final String title;
  final String originalTitle;
  final String? overview;
  final String? posterPath;
  final String? backdropPath;
  final String? releaseDate; // release_date or first_air_date
  final List<String> originCountry;

  TmdbSearchItem({
    required this.tmdbId,
    required this.type,
    required this.title,
    required this.originalTitle,
    this.overview,
    this.posterPath,
    this.backdropPath,
    this.releaseDate,
    this.originCountry = const [],
  });

  factory TmdbSearchItem.fromJson(Map<String, dynamic> json) {
    // 兼容 Movie (title/release_date) 和 TV (name/first_air_date)
    final title = json['title'] as String? ?? json['name'] as String? ?? '';
    final releaseDate =
        json['release_date'] as String? ?? json['first_air_date'] as String?;

    return TmdbSearchItem(
      tmdbId: json['tmdb_id'] as int,
      type: json['type'] as String? ?? 'tv', // 默认为 TV，或者由调用方指定
      title: title,
      originalTitle:
          (json['original_title'] ?? json['original_name'] ?? '') as String,
      overview: json['overview'] as String?,
      posterPath: json['poster_path'] as String?,
      backdropPath: json['backdrop_path'] as String?,
      releaseDate: releaseDate,
      originCountry:
          (json['origin_country'] as List?)?.cast<String>() ?? const [],
    );
  }
}

/// TMDB 季信息模型
class TmdbSeasonItem {
  final int? tmdbSeasonId;
  final int seasonNumber;
  final String name;
  final String? posterPath;
  final String? airDate;
  final int? episodeCount;

  TmdbSeasonItem({
    this.tmdbSeasonId,
    required this.seasonNumber,
    required this.name,
    this.posterPath,
    this.airDate,
    this.episodeCount,
  });

  factory TmdbSeasonItem.fromJson(Map<String, dynamic> json) {
    return TmdbSeasonItem(
      tmdbSeasonId: json['tmdb_season_id'] as int?,
      seasonNumber: json['season_number'] as int,
      name: json['name'] as String,
      posterPath: json['poster_path'] as String?,
      airDate: json['air_date'] as String?,
      episodeCount: json['episode_count'] as int?,
    );
  }
}

/// TMDB 集信息模型
class TmdbEpisodeItem {
  final int tmdbEpisodeId;
  final int episodeNumber;
  final String name;
  final String? airDate;
  final String? stillPath;

  TmdbEpisodeItem({
    required this.tmdbEpisodeId,
    required this.episodeNumber,
    required this.name,
    this.airDate,
    this.stillPath,
  });

  factory TmdbEpisodeItem.fromJson(Map<String, dynamic> json) {
    return TmdbEpisodeItem(
      // 兼容 tmdb_episode_id (旧) 和 episode_tmdb_id (新)
      tmdbEpisodeId:
          (json['tmdb_episode_id'] ?? json['episode_tmdb_id']) as int,
      episodeNumber: json['episode_number'] as int,
      name: json['name'] as String,
      airDate: json['air_date'] as String?,
      stillPath: json['still_path'] as String?,
    );
  }
}

/// 手动匹配文件列表项（视图模型）
class ManualMatchFileItem {
  final int fileId;
  final String path;
  final String displayName;
  final String? storageName;
  final int? currentSeasonNumber;
  final int? currentEpisodeNumber;
  final String? currentEpisodeTitle;

  ManualMatchFileItem({
    required this.fileId,
    required this.path,
    required this.displayName,
    this.storageName,
    this.currentSeasonNumber,
    this.currentEpisodeNumber,
    this.currentEpisodeTitle,
  });
}

/// 用户绑定选择（草稿）
///
/// 使用 sealed class 或简单的类结构。这里为了兼容性使用普通类 + 类型标识。
class ManualMatchChoice {
  // 'keep' | 'other' | 'bind_movie' | 'bind_episode'
  final String action;

  // 仅 bind_movie / bind_episode 有效
  final int? tmdbMovieId;
  final int? tmdbTvId;
  final int? tmdbSeasonId;
  final int? tmdbEpisodeId;
  final int? seasonNumber;
  final int? episodeNumber;

  ManualMatchChoice({
    required this.action,
    this.tmdbMovieId,
    this.tmdbTvId,
    this.tmdbSeasonId,
    this.tmdbEpisodeId,
    this.seasonNumber,
    this.episodeNumber,
  });

  factory ManualMatchChoice.keep() => ManualMatchChoice(action: 'keep');

  factory ManualMatchChoice.other() => ManualMatchChoice(action: 'other');

  factory ManualMatchChoice.bindMovie({required int tmdbMovieId}) =>
      ManualMatchChoice(action: 'bind_movie', tmdbMovieId: tmdbMovieId);

  factory ManualMatchChoice.bindEpisode({
    required int tmdbTvId,
    required int tmdbSeasonId,
    required int tmdbEpisodeId,
    required int seasonNumber,
    required int episodeNumber,
  }) =>
      ManualMatchChoice(
        action: 'bind_episode',
        tmdbTvId: tmdbTvId,
        tmdbSeasonId: tmdbSeasonId,
        tmdbEpisodeId: tmdbEpisodeId,
        seasonNumber: seasonNumber,
        episodeNumber: episodeNumber,
      );

  Map<String, dynamic> toJson() {
    return {
      'action': action,
      if (tmdbMovieId != null) 'tmdb': {'tmdb_movie_id': tmdbMovieId},
      if (tmdbTvId != null)
        'tmdb': {
          'tmdb_tv_id': tmdbTvId,
          'tmdb_season_id': tmdbSeasonId,
          'tmdb_episode_id': tmdbEpisodeId,
          'season_number': seasonNumber,
          'episode_number': episodeNumber,
        },
    };
  }
}
