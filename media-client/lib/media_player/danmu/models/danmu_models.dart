class DanmuComment {
  final int cid;
  final double time;      // 秒，从 p 字段解析
  final int mode;         // 1=滚动 4=底部 5=顶部
  final int color;        // 十进制颜色
  final String source;    // [qiyi] 等
  final String content;

  DanmuComment({required this.cid, required this.time, required this.mode,
    required this.color, required this.source, required this.content});

  factory DanmuComment.fromJson(Map<String, dynamic> json) {
    // 新格式：{text, time, color, type, extra: {cid, source}}
    final extra = json['extra'] as Map<String, dynamic>? ?? {};
    final colorStr = json['color'] as String? ?? '#FFFFFF';
    final colorValue = _parseColor(colorStr);
    final typeStr = json['type'] as String? ?? 'scroll';
    final mode = _modeFromType(typeStr);
    return DanmuComment(
      time: (json['time'] as num?)?.toDouble() ?? 0,
      mode: mode,
      color: colorValue,
      source: extra['source'] as String? ?? '',
      content: json['text'] as String? ?? '',
      cid: (extra['cid'] as num?)?.toInt() ?? 0,
    );
  }

  static int _parseColor(String hex) {
    final clean = hex.replaceFirst('#', '');
    final rgb = int.tryParse(clean, radix: 16) ?? 16777215;
    // 补全 alpha 通道为 0xFF（不透明）
    return rgb | 0xFF000000;
  }

  static int _modeFromType(String type) {
    switch (type) {
      case 'bottom': return 4;
      case 'top': return 5;
      default: return 1; // scroll
    }
  }
}

class DanmuSegment {
  final String type;
  final double segmentStart;
  final double segmentEnd;
  final String url;

  DanmuSegment({required this.type, required this.segmentStart,
    required this.segmentEnd, required this.url});

  factory DanmuSegment.fromJson(Map<String, dynamic> json) => DanmuSegment(
    type: json['type'] as String? ?? '',
    segmentStart: (json['segment_start'] as num?)?.toDouble() ?? 0,
    segmentEnd: (json['segment_end'] as num?)?.toDouble() ?? 0,
    url: json['url'] as String? ?? '',
  );
}

class DanmuData {
  final int episodeId;
  final int count;
  final List<DanmuComment> comments;
  final double videoDuration;
  final String loadMode;
  final List<DanmuSegment> segmentList;

  DanmuData({required this.episodeId, required this.count,
    required this.comments, required this.videoDuration,
    required this.loadMode, required this.segmentList});

  factory DanmuData.fromJson(Map<String, dynamic> json) {
    final comments = (json['comments'] as List?)
        ?.map((e) => DanmuComment.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [];
    final segments = (json['segment_list'] as List?)
        ?.map((e) => DanmuSegment.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [];
    return DanmuData(
      episodeId: (json['episode_id'] as num?)?.toInt() ?? 0,
      count: (json['count'] as num?)?.toInt() ?? 0,
      comments: comments,
      videoDuration: (json['video_duration'] as num?)?.toDouble() ?? 0,
      loadMode: json['load_mode'] as String? ?? 'full',
      segmentList: segments,
    );
  }
}

class DanmuSource {
  final int episodeId;
  final int animeId;
  final String animeTitle;
  final String episodeTitle;
  final String type;
  final String typeDescription;
  final int shift;
  final String imageUrl;

  DanmuSource({required this.episodeId, required this.animeId,
    required this.animeTitle, required this.episodeTitle,
    required this.type, required this.typeDescription,
    required this.shift, required this.imageUrl});

  factory DanmuSource.fromJson(Map<String, dynamic> json) => DanmuSource(
    episodeId: (json['episodeId'] as num?)?.toInt() ?? 0,
    animeId: (json['animeId'] as num?)?.toInt() ?? 0,
    animeTitle: json['animeTitle'] as String? ?? '',
    episodeTitle: json['episodeTitle'] as String? ?? '',
    type: json['type'] as String? ?? '',
    typeDescription: json['typeDescription'] as String? ?? '',
    shift: (json['shift'] as num?)?.toInt() ?? 0,
    imageUrl: json['imageUrl'] as String? ?? '',
  );
}

class DanmuMatchResult {
  final bool isMatched;
  final double confidence;
  final List<DanmuSource> sources;
  final DanmuSource? bestMatch;
  final DanmuBinding? binding;
  final DanmuData? danmuData;

  DanmuMatchResult({required this.isMatched, required this.confidence,
    required this.sources, this.bestMatch, this.binding, this.danmuData});

  factory DanmuMatchResult.fromJson(Map<String, dynamic> json) =>
    DanmuMatchResult(
      isMatched: json['is_matched'] as bool? ?? false,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      sources: (json['sources'] as List?)
          ?.map((e) => DanmuSource.fromJson(e as Map<String, dynamic>))
          .toList() ?? const [],
      bestMatch: json['best_match'] != null
          ? DanmuSource.fromJson(json['best_match'] as Map<String, dynamic>)
          : null,
      binding: json['binding'] != null
          ? DanmuBinding.fromJson(json['binding'] as Map<String, dynamic>)
          : null,
      danmuData: json['danmu_data'] != null
          ? DanmuData.fromJson(json['danmu_data'] as Map<String, dynamic>)
          : null,
    );
}

class DanmuSearchItem {
  final int animeId;
  final String animeTitle;
  final String type;
  final String typeDescription;
  final String imageUrl;
  final int episodeCount;
  final double rating;

  DanmuSearchItem({required this.animeId, required this.animeTitle,
    required this.type, required this.typeDescription,
    required this.imageUrl, required this.episodeCount,
    required this.rating});

  factory DanmuSearchItem.fromJson(Map<String, dynamic> json) =>
    DanmuSearchItem(
      animeId: (json['animeId'] as num?)?.toInt() ?? 0,
      animeTitle: json['animeTitle'] as String? ?? '',
      type: json['type'] as String? ?? '',
      typeDescription: json['typeDescription'] as String? ?? '',
      imageUrl: json['imageUrl'] as String? ?? '',
      episodeCount: (json['episodeCount'] as num?)?.toInt() ?? 0,
      rating: (json['rating'] as num?)?.toDouble() ?? 0,
    );
}

class DanmuBangumi {
  final int animeId;
  final String animeTitle;
  final String type;
  final String imageUrl;
  final List<DanmuSeason> seasons;
  final List<DanmuEpisode> episodes;

  DanmuBangumi({required this.animeId, required this.animeTitle,
    required this.type, required this.imageUrl,
    required this.seasons, required this.episodes});

  factory DanmuBangumi.fromJson(Map<String, dynamic> json) => DanmuBangumi(
    animeId: (json['animeId'] as num?)?.toInt() ?? 0,
    animeTitle: json['animeTitle'] as String? ?? '',
    type: json['type'] as String? ?? '',
    imageUrl: json['imageUrl'] as String? ?? '',
    seasons: (json['seasons'] as List?)
        ?.map((e) => DanmuSeason.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
    episodes: (json['episodes'] as List?)
        ?.map((e) => DanmuEpisode.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
  );
}

class DanmuSeason {
  final String id;
  final String name;
  final int episodeCount;

  DanmuSeason({required this.id, required this.name, required this.episodeCount});

  factory DanmuSeason.fromJson(Map<String, dynamic> json) => DanmuSeason(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    episodeCount: (json['episodeCount'] as num?)?.toInt() ?? 0,
  );
}

class DanmuEpisode {
  final String seasonId;
  final int episodeId;
  final String episodeTitle;
  final String episodeNumber;

  DanmuEpisode({required this.seasonId, required this.episodeId,
    required this.episodeTitle, required this.episodeNumber});

  factory DanmuEpisode.fromJson(Map<String, dynamic> json) => DanmuEpisode(
    seasonId: json['seasonId'] as String? ?? '',
    episodeId: (json['episodeId'] as num?)?.toInt() ?? 0,
    episodeTitle: json['episodeTitle'] as String? ?? '',
    episodeNumber: json['episodeNumber'] as String? ?? '',
  );
}

int _toInt(dynamic v) =>
    v is num ? v.toInt() : int.tryParse('$v') ?? 0;

class DanmuBinding {
  final int id;
  final String fileId;
  final int episodeId;
  final int animeId;
  final String animeTitle;
  final String episodeTitle;
  final double offset;
  final bool isManual;

  DanmuBinding({required this.id, required this.fileId, required this.episodeId,
    required this.animeId, required this.animeTitle, required this.episodeTitle,
    required this.offset, required this.isManual});

  factory DanmuBinding.fromJson(Map<String, dynamic> json) => DanmuBinding(
    id: _toInt(json['id']),
    fileId: json['file_id'] as String? ?? '',
    episodeId: _toInt(json['episode_id']),
    animeId: _toInt(json['anime_id']),
    animeTitle: json['anime_title'] as String? ?? '',
    episodeTitle: json['episode_title'] as String? ?? '',
    offset: (json['offset'] as num?)?.toDouble() ?? 0,
    isManual: json['is_manual'] as bool? ?? false,
  );
}

class DanmuNextSegmentResult {
  final int count;
  final List<DanmuComment> comments;
  final bool success;
  final int errorCode;
  final String errorMessage;

  DanmuNextSegmentResult({required this.count, required this.comments, required this.success, required this.errorCode, required this.errorMessage});

  factory DanmuNextSegmentResult.fromJson(Map<String, dynamic> json) => DanmuNextSegmentResult(
    count: json['count'] as int? ?? 0,
    comments: (json['comments'] as List?)
        ?.map((e) => DanmuComment.fromJson(e as Map<String, dynamic>))
        .toList() ?? const [],
    success: json['success'] as bool? ?? false,
    errorCode: json['errorCode'] as int? ?? 0,
    errorMessage: json['errorMessage'] as String? ?? '',
  );
}
