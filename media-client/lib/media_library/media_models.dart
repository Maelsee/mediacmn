// 新增首页卡片数据结构
class HomeCardGenre {
  final int id;
  final String name;
  HomeCardGenre({required this.id, required this.name});
  factory HomeCardGenre.fromJson(Map<String, dynamic> json) => HomeCardGenre(
        id: json['id'] as int,
        name: json['name'] as String,
      );
}

class HomeCardItem {
  final int id;
  final String name;
  final String? coverUrl;
  final double? rating;
  final String? releaseDate;
  final String mediaType;

  HomeCardItem({
    required this.id,
    required this.name,
    this.coverUrl,
    this.rating,
    this.releaseDate,
    required this.mediaType,
  });

  factory HomeCardItem.fromJson(Map<String, dynamic> json) => HomeCardItem(
        id: json['id'] as int,
        name: json['name'] as String,
        coverUrl: json['cover_url'] as String?,
        rating:
            (json['rating'] is num) ? (json['rating'] as num).toDouble() : null,
        releaseDate: json['release_date'] as String?,
        mediaType: json['media_type'] as String,
      );
}

class HomeCardsResponse {
  final List<HomeCardGenre> genres;
  final List<HomeCardItem> movie;
  final List<HomeCardItem> tv;

  HomeCardsResponse({
    required this.genres,
    required this.movie,
    required this.tv,
  });

  factory HomeCardsResponse.fromJson(Map<String, dynamic> json) =>
      HomeCardsResponse(
        genres: (json['genres'] as List?)
                ?.cast<Map<String, dynamic>>()
                .map(HomeCardGenre.fromJson)
                .toList() ??
            const [],
        movie: (json['movie'] as List?)
                ?.cast<Map<String, dynamic>>()
                .map(HomeCardItem.fromJson)
                .toList() ??
            const [],
        tv: (json['tv'] as List?)
                ?.cast<Map<String, dynamic>>()
                .map(HomeCardItem.fromJson)
                .toList() ??
            const [],
      );
}

class PagedMediaResponse {
  final int total;
  final List<HomeCardItem> items;
  PagedMediaResponse({required this.total, required this.items});
  factory PagedMediaResponse.fromJson(Map<String, dynamic> json) =>
      PagedMediaResponse(
        total: (json['total'] ?? 0) as int,
        items: (json['items'] as List?)
                ?.cast<Map<String, dynamic>>()
                .map(HomeCardItem.fromJson)
                .toList() ??
            const [],
      );
}

class FilterCardsResponse {
  final int page;
  final int pageSize;
  final int total;
  final List<HomeCardItem> items;

  FilterCardsResponse({
    required this.page,
    required this.pageSize,
    required this.total,
    required this.items,
  });

  factory FilterCardsResponse.fromJson(Map<String, dynamic> json) =>
      FilterCardsResponse(
        page: (json['page'] ?? 1) as int,
        pageSize: (json['page_size'] ?? 30) as int,
        total: (json['total'] ?? 0) as int,
        items: (json['items'] as List?)
                ?.cast<Map<String, dynamic>>()
                .map(HomeCardItem.fromJson)
                .toList() ??
            const [],
      );
}

class MediaDetail {
  final int id;
  final String title;
  final List<String> genres;
  final String mediaType; // movie|tv
  final List<SeasonDetail>? seasons;
  final int? seasonCount;
  final int? episodeCount;
  // Movie specific fields
  final String? posterPath;
  final String? backdropPath;
  final double? rating;
  final String? releaseDate;
  final String? overview;
  final int? runtime;
  final String? runtimeText;
  final List<VersionItem>? versions;
  final List<CastItem>? cast;
  final List<String>? directors;
  final List<String>? writers;

  MediaDetail({
    required this.id,
    required this.title,
    required this.genres,
    required this.mediaType,
    this.seasons,
    this.seasonCount,
    this.episodeCount,
    this.posterPath,
    this.backdropPath,
    this.rating,
    this.releaseDate,
    this.overview,
    this.runtime,
    this.runtimeText,
    this.versions,
    this.cast,
    this.directors,
    this.writers,
  });

  factory MediaDetail.fromJson(Map<String, dynamic> json) => MediaDetail(
        id: (json['id'] ?? 0) as int,
        title: (json['title'] ?? '') as String,
        genres: (json['genres'] as List?)?.cast<String>() ?? const [],
        mediaType: (json['media_type'] ?? 'movie') as String,
        seasons: ((json['seasons'] as List?)?.cast<Map<String, dynamic>>() ??
                const [])
            .map(SeasonDetail.fromJson)
            .toList(),
        seasonCount: (json['season_count'] as num?)?.toInt(),
        episodeCount: (json['episode_count'] as num?)?.toInt(),
        posterPath: json['poster_path'] as String?,
        backdropPath: json['backdrop_path'] as String?,
        rating:
            (json['rating'] is num) ? (json['rating'] as num).toDouble() : null,
        releaseDate: json['release_date'] as String?,
        overview: json['overview'] as String?,
        runtime: (json['runtime'] as num?)?.toInt(),
        runtimeText: json['runtime_text'] as String?,
        versions: ((json['versions'] as List?)?.cast<Map<String, dynamic>>() ??
                const [])
            .map(VersionItem.fromJson)
            .toList(),
        cast:
            ((json['cast'] as List?)?.cast<Map<String, dynamic>>() ?? const [])
                .map(CastItem.fromJson)
                .toList(),
        directors: (json['directors'] as List?)?.cast<String>(),
        writers: (json['writers'] as List?)?.cast<String>(),
      );
}

class VersionItem {
  final int id;
  final String? label;
  final String? quality;
  final String? source;
  final String? edition;
  final List<AssetItem> assets;

  VersionItem(
      {required this.id,
      this.label,
      this.quality,
      this.source,
      this.edition,
      this.assets = const []});
  factory VersionItem.fromJson(Map<String, dynamic> json) => VersionItem(
        id: (json['id'] ?? 0) as int,
        label: json['label'] as String?,
        quality: json['quality'] as String?,
        source: json['source'] as String?,
        edition: json['edition'] as String?,
        assets: ((json['assets'] as List?)?.cast<Map<String, dynamic>>() ??
                const [])
            .map(AssetItem.fromJson)
            .toList(),
      );
}

class SeasonDetail {
  final int seasonNumber;
  final String? overview;
  final double? rating;
  final String? cover;
  final String? airDate;
  final List<CastItem>? cast;
  final int? runtime;
  final String? runtimeText;
  final List<EpisodeDetail> episodes;
  SeasonDetail({
    required this.seasonNumber,
    this.overview,
    this.rating,
    this.cover,
    this.airDate,
    this.cast,
    this.runtime,
    this.runtimeText,
    this.episodes = const [],
  });
  factory SeasonDetail.fromJson(Map<String, dynamic> json) => SeasonDetail(
        seasonNumber: (json['season_number'] ?? 0) as int,
        overview: json['overview'] as String?,
        rating:
            (json['rating'] is num) ? (json['rating'] as num).toDouble() : null,
        cover: json['cover'] as String?,
        airDate: json['air_date'] as String?,
        cast:
            ((json['cast'] as List?)?.cast<Map<String, dynamic>>() ?? const [])
                .map(CastItem.fromJson)
                .toList(),
        runtime: (json['runtime'] as num?)?.toInt(),
        runtimeText: json['runtime_text'] as String?,
        episodes: ((json['episodes'] as List?)?.cast<Map<String, dynamic>>() ??
                const [])
            .map(EpisodeDetail.fromJson)
            .toList(),
      );
}

class EpisodeDetail {
  final int episodeNumber;
  final String title;
  final int? runtime;
  final String? runtimeText;
  final List<AssetItem> assets;
  final Map<String, dynamic>? technical;
  final String? stillPath;
  EpisodeDetail(
      {required this.episodeNumber,
      required this.title,
      this.runtime,
      this.runtimeText,
      this.assets = const [],
      this.technical,
      this.stillPath});
  factory EpisodeDetail.fromJson(Map<String, dynamic> json) => EpisodeDetail(
        episodeNumber: (json['episode_number'] ?? 0) as int,
        title: (json['title'] ?? '') as String,
        runtime: (json['runtime'] as num?)?.toInt(),
        runtimeText: json['runtime_text'] as String?,
        assets: ((json['assets'] as List?)?.cast<Map<String, dynamic>>() ??
                const [])
            .map(AssetItem.fromJson)
            .toList(),
        technical: json['technical'] as Map<String, dynamic>?,
        stillPath: json['still_path'] as String?,
      );
}

class AssetItem {
  final int fileId;
  final String path;
  final String type;
  final int? size;
  final String? sizeText;
  AssetItem(
      {required this.fileId,
      required this.path,
      required this.type,
      this.size,
      this.sizeText});
  factory AssetItem.fromJson(Map<String, dynamic> json) => AssetItem(
        fileId: (json['file_id'] ?? 0) as int,
        path: (json['path'] ?? '') as String,
        type: (json['type'] ?? '') as String,
        size: (json['size'] as num?)?.toInt(),
        sizeText: json['size_text'] as String?,
      );
}

class CastItem {
  final String name;
  final String? character;
  final String? imageUrl;
  CastItem({required this.name, this.character, this.imageUrl});
  factory CastItem.fromJson(Map<String, dynamic> json) => CastItem(
        name: (json['name'] ?? '') as String,
        character: json['character'] as String?,
        imageUrl: json['image_url'] as String?,
      );
}

class RecentCardItem {
  final int id;
  final String name;
  final String? coverUrl;
  final String mediaType;
  final int? positionMs;
  final int? durationMs;
  final int? fileId;

  RecentCardItem({
    required this.id,
    required this.name,
    this.coverUrl,
    required this.mediaType,
    this.positionMs,
    this.durationMs,
    this.fileId,
  });

  factory RecentCardItem.fromJson(Map<String, dynamic> json) {
    return RecentCardItem(
      id: json['id'] as int,
      name: json['name'] as String,
      coverUrl: json['cover_url'] as String?,
      mediaType: json['media_type'] as String,
      positionMs: json['position_ms'] as int?,
      durationMs: json['duration_ms'] as int?,
      fileId: json['file_id'] as int?,
    );
  }

  factory RecentCardItem.fromApi(Map<String, dynamic> json) {
    final kind =
        json['kind'] as String? ?? json['media_type'] as String? ?? 'movie';
    final title = (json['name'] ?? json['title']) as String? ?? '';

    // Cover Logic
    final stillPath = json['still_path'] as String?;
    final backdropPath = json['backdrop_path'] as String?;
    final poster = (json['poster'] ?? json['cover_url']) as String?;
    final coverUrl = stillPath ?? backdropPath ?? poster;

    // Name/Title Logic
    String displayName = title;
    if (kind == 'tv' || kind == 'tv_episode') {
      final seriesName = json['series_name'] as String?;
      final seasonIndex = (json['season_index'] as num?)?.toInt();
      final episodeIndex = (json['episode_index'] as num?)?.toInt();
      final episodeTitle = json['episode_title'] as String?;

      if (seriesName != null && seasonIndex != null && episodeIndex != null) {
        final s = seasonIndex.toString().padLeft(2, '0');
        final e = episodeIndex.toString().padLeft(2, '0');
        displayName = '$seriesName S${s}E$e ${episodeTitle ?? ''}';
      }
    }

    return RecentCardItem(
      id: (json['id'] is int)
          ? json['id'] as int
          : int.tryParse('${json['id']}') ?? 0,
      name: displayName,
      coverUrl: coverUrl,
      mediaType: kind,
      positionMs: (json['position_ms'] as num?)?.toInt(),
      durationMs: (json['duration_ms'] as num?)?.toInt(),
      fileId: (json['file_id'] as num?)?.toInt(),
    );
  }
}
