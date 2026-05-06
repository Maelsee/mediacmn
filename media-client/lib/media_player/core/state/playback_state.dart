import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:floating/floating.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../../core/player/player_config.dart';
import '../../core/player/player_service.dart';
import '../../utils/player_utils.dart';
import '../../../core/api_client.dart';
import '../../../core/playback_history/playback_progress_repository.dart';
import '../../../core/playback_history/providers.dart';
import '../../../media_library/media_models.dart';
import 'episode_navigation_mixin.dart';
import 'progress_tracker.dart';
import 'settings_persistence.dart';

/// 哨兵值：表示用户未配置片头/片尾时间。
/// 负数 Duration 确保 `> Duration.zero` 检查自动将其视为"未设置"。
const Duration kUnsetDuration = Duration(milliseconds: -1);

class PlaybackSettings {
  /// 是否开启片头片尾跳过。
  final bool skipIntroOutro;

  /// 片头结束时间点。
  final Duration introTime;

  /// 片尾开始时间点。
  final Duration outroTime;

  /// 是否对所有剧集生效。
  final bool applyToAllEpisodes;

  /// 字幕字体大小。
  final double subtitleFontSize;

  /// 字幕底部边距。
  final double subtitleBottomPadding;

  /// introTime 是否已被用户显式配置。
  bool get hasIntroTime => introTime != kUnsetDuration;

  /// outroTime 是否已被用户显式配置。
  bool get hasOutroTime => outroTime != kUnsetDuration;

  const PlaybackSettings({
    this.skipIntroOutro = false,
    this.introTime = kUnsetDuration,
    this.outroTime = kUnsetDuration,
    this.applyToAllEpisodes = false,
    this.subtitleFontSize = 40.0,
    this.subtitleBottomPadding = 24.0,
  });

  PlaybackSettings copyWith({
    bool? skipIntroOutro,
    Duration? introTime,
    Duration? outroTime,
    bool? applyToAllEpisodes,
    double? subtitleFontSize,
    double? subtitleBottomPadding,
  }) {
    return PlaybackSettings(
      skipIntroOutro: skipIntroOutro ?? this.skipIntroOutro,
      introTime: introTime ?? this.introTime,
      outroTime: outroTime ?? this.outroTime,
      applyToAllEpisodes: applyToAllEpisodes ?? this.applyToAllEpisodes,
      subtitleFontSize: subtitleFontSize ?? this.subtitleFontSize,
      subtitleBottomPadding:
          subtitleBottomPadding ?? this.subtitleBottomPadding,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'skip': skipIntroOutro,
      'intro_ms': introTime.inMilliseconds,
      'outro_ms': outroTime.inMilliseconds,
      'apply_all': applyToAllEpisodes,
      'sub_size': subtitleFontSize,
      'sub_padding': subtitleBottomPadding,
    };
  }

  static PlaybackSettings fromJson(Map<String, dynamic> json) {
    return PlaybackSettings(
      skipIntroOutro: (json['skip'] as bool?) ?? false,
      introTime: _parseDurationFromJson(json['intro_ms']),
      outroTime: _parseDurationFromJson(json['outro_ms']),
      applyToAllEpisodes: (json['apply_all'] as bool?) ?? false,
      subtitleFontSize: (json['sub_size'] as num?)?.toDouble() ?? 40.0,
      subtitleBottomPadding: (json['sub_padding'] as num?)?.toDouble() ?? 24.0,
    );
  }

  static Duration _parseDurationFromJson(Object? raw) {
    final ms = (raw as num?)?.toInt() ?? -1;
    if (ms < 0) return kUnsetDuration;
    return Duration(milliseconds: ms);
  }
}

class PlaybackState {
  /// 是否处于初始化/切集加载中。
  final bool loading;

  /// 错误信息（为空表示无错误）。
  final String? error;

  /// 是否显示控制层。
  final bool controlsVisible;

  /// 是否锁定屏幕。
  final bool isLocked;

  /// 是否处于全屏。
  final bool isFullscreen;

  final String? title;
  final String? posterUrl;
  final String? mediaType;

  final int? coreId;
  final int? fileId;

  /// 当前正在播放的地址。
  final String? playUrl;

  /// 播放资源的 HTTP 请求头（例如 WebDAV 的 BasicAuth）。
  final Map<String, String> playHeaders;

  final bool playing;
  final bool buffering;
  final Duration position;
  final Duration duration;
  final Duration buffered;

  final double volume;
  final double speed;

  final List<AssetItem> candidates;
  final int selectedCandidateIndex;

  final MediaDetail? detail;
  final int? currentEpisodeFileId;
  final bool hasPrevEpisode;
  final bool hasNextEpisode;

  /// 选集列表。
  ///
  /// 数据来源：
  /// 1) 详情页跳转播放器时传入的季版本 episodes；
  /// 2) 通过后端接口 /api/media/file/{file_id}/episodes 拉取。
  final List<EpisodeDetail> episodes;

  /// 选集列表对应的季版本 ID（可能为空）。
  final int? seasonVersionId;

  /// 是否正在加载选集列表。
  final bool episodesLoading;

  /// 选集列表加载错误（为空表示无错误）。
  final String? episodesError;

  // UI 控制相关状态
  /// 画面适配模式（自适应/铺满/裁切等）。
  final BoxFit fit;

  /// 画面缩放倍数。
  ///
  /// 用于双指缩放调整画面大小（仅影响渲染层，不影响播放进度与解码）。
  final double videoScale;

  /// 画面平移偏移（逻辑像素）。
  ///
  /// 用于双指拖动调整画面位置。
  final Offset videoOffset;

  /// 可用视频轨道列表（通常对应画质/分辨率）。
  final List<VideoTrack> videoTracks;

  /// 当前选中的视频轨道。
  final VideoTrack? selectedVideoTrack;

  /// 可用音频轨道列表（音轨）。
  final List<AudioTrack> audioTracks;

  /// 当前选中的音频轨道。
  final AudioTrack? selectedAudioTrack;

  /// 可用字幕轨道列表。
  final List<SubtitleTrack> subtitleTracks;

  /// 当前选中的字幕轨道。
  final SubtitleTrack? selectedSubtitleTrack;
  final PlaylistMode playlistMode;

  final PlaybackSettings settings;

  const PlaybackState({
    this.loading = true,
    this.error,
    this.controlsVisible = true,
    this.isLocked = false,
    this.isFullscreen = false,
    this.title,
    this.posterUrl,
    this.mediaType,
    this.coreId,
    this.fileId,
    this.playUrl,
    this.playHeaders = const {},
    this.playing = false,
    this.buffering = false,
    this.position = Duration.zero,
    this.duration = Duration.zero,
    this.buffered = Duration.zero,
    this.volume = 80,
    this.speed = 1.0,
    this.candidates = const [],
    this.selectedCandidateIndex = 0,
    this.detail,
    this.currentEpisodeFileId,
    this.hasPrevEpisode = false,
    this.hasNextEpisode = false,
    this.episodes = const [],
    this.seasonVersionId,
    this.episodesLoading = false,
    this.episodesError,
    this.fit = BoxFit.contain,
    this.videoScale = 1.0,
    this.videoOffset = Offset.zero,
    this.videoTracks = const [],
    this.selectedVideoTrack,
    this.audioTracks = const [],
    this.selectedAudioTrack,
    this.subtitleTracks = const [],
    this.selectedSubtitleTrack,
    this.playlistMode = PlaylistMode.none,
    this.settings = const PlaybackSettings(),
  });

  PlaybackState copyWith({
    bool? loading,
    String? error,
    bool? controlsVisible,
    bool? isLocked,
    bool? isFullscreen,
    String? title,
    String? posterUrl,
    String? mediaType,
    int? coreId,
    int? fileId,
    String? playUrl,
    Map<String, String>? playHeaders,
    bool? playing,
    bool? buffering,
    Duration? position,
    Duration? duration,
    Duration? buffered,
    double? volume,
    double? speed,
    List<AssetItem>? candidates,
    int? selectedCandidateIndex,
    MediaDetail? detail,
    int? currentEpisodeFileId,
    bool? hasPrevEpisode,
    bool? hasNextEpisode,
    List<EpisodeDetail>? episodes,
    int? seasonVersionId,
    bool? episodesLoading,
    String? episodesError,
    BoxFit? fit,
    double? videoScale,
    Offset? videoOffset,
    List<VideoTrack>? videoTracks,
    VideoTrack? selectedVideoTrack,
    List<AudioTrack>? audioTracks,
    AudioTrack? selectedAudioTrack,
    List<SubtitleTrack>? subtitleTracks,
    SubtitleTrack? selectedSubtitleTrack,
    PlaylistMode? playlistMode,
    PlaybackSettings? settings,
  }) {
    return PlaybackState(
      loading: loading ?? this.loading,
      error: error,
      controlsVisible: controlsVisible ?? this.controlsVisible,
      isLocked: isLocked ?? this.isLocked,
      isFullscreen: isFullscreen ?? this.isFullscreen,
      title: title ?? this.title,
      posterUrl: posterUrl ?? this.posterUrl,
      mediaType: mediaType ?? this.mediaType,
      coreId: coreId ?? this.coreId,
      fileId: fileId ?? this.fileId,
      playUrl: playUrl ?? this.playUrl,
      playHeaders: playHeaders ?? this.playHeaders,
      playing: playing ?? this.playing,
      buffering: buffering ?? this.buffering,
      position: position ?? this.position,
      duration: duration ?? this.duration,
      buffered: buffered ?? this.buffered,
      volume: volume ?? this.volume,
      speed: speed ?? this.speed,
      candidates: candidates ?? this.candidates,
      selectedCandidateIndex:
          selectedCandidateIndex ?? this.selectedCandidateIndex,
      detail: detail ?? this.detail,
      currentEpisodeFileId: currentEpisodeFileId ?? this.currentEpisodeFileId,
      hasPrevEpisode: hasPrevEpisode ?? this.hasPrevEpisode,
      hasNextEpisode: hasNextEpisode ?? this.hasNextEpisode,
      episodes: episodes ?? this.episodes,
      seasonVersionId: seasonVersionId ?? this.seasonVersionId,
      episodesLoading: episodesLoading ?? this.episodesLoading,
      episodesError: episodesError,
      fit: fit ?? this.fit,
      videoScale: videoScale ?? this.videoScale,
      videoOffset: videoOffset ?? this.videoOffset,
      videoTracks: videoTracks ?? this.videoTracks,
      selectedVideoTrack: selectedVideoTrack ?? this.selectedVideoTrack,
      audioTracks: audioTracks ?? this.audioTracks,
      selectedAudioTrack: selectedAudioTrack ?? this.selectedAudioTrack,
      subtitleTracks: subtitleTracks ?? this.subtitleTracks,
      selectedSubtitleTrack:
          selectedSubtitleTrack ?? this.selectedSubtitleTrack,
      playlistMode: playlistMode ?? this.playlistMode,
      settings: settings ?? this.settings,
    );
  }
}

final playerConfigProvider = Provider<PlayerConfig>(
  (ref) => const PlayerConfig(),
);

/// 画中画控制器（同一播放页内复用同一个实例，确保 UI 能正确感知 PiP 状态）。
final floatingProvider = Provider.autoDispose<Floating>((ref) => Floating());

final playerServiceProvider = Provider.autoDispose<PlayerServiceBase>((ref) {
  final config = ref.watch(playerConfigProvider);
  final service = PlayerService.create(config: config);
  ref.onDispose(service.dispose);
  return service;
});

final playbackProvider =
    StateNotifierProvider.autoDispose<PlaybackNotifier, PlaybackState>((ref) {
  final api = ref.watch(apiClientProvider);
  final service = ref.watch(playerServiceProvider);
  final config = ref.watch(playerConfigProvider);
  final progressRepo = ref.watch(playbackProgressRepositoryProvider);
  final notifier = PlaybackNotifier(
    api: api,
    service: service,
    config: config,
    progressRepository: progressRepo,
  );
  return notifier;
});

class PlaybackNotifier extends StateNotifier<PlaybackState>
    with EpisodeNavigationMixin {
  final ApiClient api;
  final PlayerServiceBase service;
  final PlayerConfig config;

  /// 播放进度仓库（本地优先 + outbox 同步）。
  final PlaybackProgressRepository progressRepository;

  StreamSubscription? _playingSub;
  StreamSubscription? _bufferingSub;
  StreamSubscription? _posSub;
  StreamSubscription? _durSub;
  StreamSubscription? _bufSub;
  StreamSubscription? _volSub;
  StreamSubscription? _speedSub;
  StreamSubscription? _completedSub;
  StreamSubscription? _tracksSub;
  StreamSubscription? _trackSub;

  /// 进度追踪器（本地保存 + 远端上报）。
  late final ProgressTracker _progressTracker;

  /// 设置持久化。
  late final SettingsPersistence _settingsPersistence;

  bool _initialized = false;

  /// 记录最近一次打开媒体的时间，用于抑制”切源/切集/重开”过程中误触发的自动下一集。
  DateTime? _lastOpenAt;

  /// 当前媒体是否已完成首次片头跳过。
  ///
  /// 每次打开新媒体时重置为 false，首次跳过片头后设为 true。
  /// 之后仅在用户手动拖动进度条进入片头时间 ±5 秒窗口时才再次触发。
  bool _introSkippedForCurrentMedia = false;

  /// 片尾跳过是否已触发（防重入保护）。
  ///
  /// 避免 position 流每帧回调导致连续触发多次 `_handlePlaybackCompleted`。
  bool _outroSkipTriggered = false;

  /// 弹幕开关偏好（跨集保持，不随 fileId 变化而重置）。
  bool danmuEnabled = false;

  /// 字幕切换中标记。
  ///
  /// 目的：避免用户连续点击导致重复切换，造成明显卡顿或长时间无响应。
  bool _subtitleSwitching = false;

  /// 音轨切换中标记。
  ///
  /// 目的：避免用户连续点击导致频繁重建解码管线，造成卡顿或长时间无响应。
  bool _audioSwitching = false;

  /// 路由入参中原始的标题文案（只在初始化时赋值一次，用于降级拼接）。
  @override
  String? routeTitleHint;

  @override
  String? seriesNameHint;

  @override
  int? seasonIndexHint;

  PlaybackNotifier({
    required this.api,
    required this.service,
    required this.config,
    required this.progressRepository,
  }) : super(const PlaybackState()) {
    _progressTracker = ProgressTracker(repository: progressRepository);
    _settingsPersistence = SettingsPersistence();
  }

  /// 从当前 state 构建进度快照。
  ProgressSnapshot _snapshot() => ProgressSnapshot(
        fileId: state.fileId,
        coreId: state.coreId,
        mediaType: state.mediaType,
        title: state.title,
        coverUrl: state.posterUrl,
        positionMs: state.position.inMilliseconds,
        durationMs: state.duration == Duration.zero
            ? null
            : state.duration.inMilliseconds,
        playing: state.playing,
      );

  Future<void> initialize({
    required String coreId,
    required Object? extra,
  }) async {
    if (_initialized) return;
    _initialized = true;

    final globalResult = await _settingsPersistence.loadGlobalSettings();
    if (globalResult.settings != null) {
      state = state.copyWith(settings: globalResult.settings);
    }
    if (globalResult.playlistMode != null) {
      state = state.copyWith(playlistMode: globalResult.playlistMode);
    }
    try {
      await _applyPlaylistModeToService(state.playlistMode);
    } catch (_) {}

    final parsedCoreId = int.tryParse(coreId);
    final payload = extra is Map ? extra : const <String, dynamic>{};

    var parsedSeriesName =
        (payload['seriesName'] ?? payload['series_name'])?.toString();
    final seasonIndexHintRaw =
        payload['seasonIndex'] ?? payload['season_index'];
    int? parsedSeasonIndex;
    if (seasonIndexHintRaw is int) {
      parsedSeasonIndex = seasonIndexHintRaw;
    } else if (seasonIndexHintRaw != null) {
      parsedSeasonIndex = int.tryParse('$seasonIndexHintRaw');
    }
    if (parsedSeriesName != null && parsedSeriesName.trim().isNotEmpty) {
      parsedSeriesName = parsedSeriesName.trim();
    }
    if (parsedSeasonIndex != null && parsedSeasonIndex > 0) {
      seasonIndexHint = parsedSeasonIndex;
    }

    // 本地播放：在 extra 参数中传入 filePath/path 即可
    final filePath =
        payload['filePath']?.toString() ?? payload['path']?.toString();
    if (filePath != null && filePath.isNotEmpty) {
      state = state.copyWith(
        loading: false,
        error: null,
        coreId: parsedCoreId,
        playUrl: filePath,
        playHeaders: const {},
        title: filePath.split('/').last,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );
      _lastOpenAt = DateTime.now();
      _introSkippedForCurrentMedia = false;
      _outroSkipTriggered = false;
      await service.openUrl(filePath);
      try {
        await _applyPlaylistModeToService(state.playlistMode);
      } catch (_) {}
      return;
    }

    final detail = payload['detail'];
    MediaDetail? detailModel;
    String? title;
    String? posterUrl;
    String? mediaType;
    if (detail is MediaDetail) {
      detailModel = detail;
      title = detail.title;
      posterUrl = detail.posterPath ?? detail.backdropPath;
      mediaType = detail.mediaType;
      if (detail.title.trim().isNotEmpty) {
        parsedSeriesName = detail.title.trim();
      }
    } else if (detail is Map) {
      title = (detail['name'] ?? detail['title'])?.toString();
      posterUrl = (detail['poster_path'] ??
              detail['backdrop_path'] ??
              detail['cover_url'])
          ?.toString();
      mediaType = (detail['media_type'] ?? detail['kind'])?.toString();

      final seriesName =
          (detail['series_name'] ?? detail['seriesName'])?.toString();
      final seasonIndexRaw = detail['season_index'] ?? detail['seasonIndex'];
      final seasonIndex = seasonIndexRaw is int
          ? seasonIndexRaw
          : int.tryParse('$seasonIndexRaw');
      if (seriesName != null && seriesName.trim().isNotEmpty) {
        parsedSeriesName ??= seriesName.trim();
      }
      if (seasonIndex != null && seasonIndex > 0) {
        seasonIndexHint ??= seasonIndex;
      }
    }

    // 仅在初始化阶段记录一次路由原始标题，用于后续无系列名/季信息时的降级处理。
    if (title != null && title.trim().isNotEmpty) {
      routeTitleHint ??= title.trim();
    }

    final candidatesRaw = payload['candidates'];
    final candidates = <AssetItem>[];
    if (candidatesRaw is List) {
      for (final c in candidatesRaw) {
        if (c is AssetItem) {
          candidates.add(c);
        } else if (c is Map) {
          candidates.add(AssetItem.fromJson(c.cast<String, dynamic>()));
        }
      }
    }

    final episodesRaw = payload['episodes'];
    final episodes = _parseEpisodes(episodesRaw);

    final seasonVersionId = payload['seasonVersionId'] is int
        ? payload['seasonVersionId'] as int
        : int.tryParse(
            '${payload['seasonVersionId'] ?? payload['season_version_id'] ?? ''}',
          );

    int? fileId = payload['fileId'] is int
        ? payload['fileId'] as int
        : int.tryParse('${payload['fileId']}');
    final asset = payload['asset'];
    if (fileId == null) {
      if (asset is AssetItem) {
        fileId = asset.fileId;
      } else if (asset is Map) {
        final a = AssetItem.fromJson(asset.cast<String, dynamic>());
        fileId = a.fileId;
        if (candidates.isEmpty) {
          candidates.add(a);
        }
      }
    }
    if (fileId == null && candidates.isNotEmpty) {
      fileId = candidates.first.fileId;
    }

    state = state.copyWith(
      loading: true,
      error: null,
      coreId: parsedCoreId,
      fileId: fileId,
      title: title,
      posterUrl: posterUrl,
      mediaType: mediaType,
      candidates: candidates,
      selectedCandidateIndex: 0,
      detail: detailModel,
      currentEpisodeFileId: fileId,
      episodes: episodes,
      seasonVersionId: seasonVersionId,
    );

    seriesNameHint = parsedSeriesName;
    syncTitleForCurrentEpisode();

    _bindPlayerStreams();

    try {
      await WakelockPlus.enable();
    } catch (_) {}

    if (fileId == null) {
      state = state.copyWith(loading: false, error: '缺少可播放的资源');
      return;
    }

    unawaited(_ensureEpisodesLoaded(fileId: fileId));

    unawaited(_loadVideoSpecificSettingsFromPersistence());

    try {
      // 统一进度获取逻辑：路由参数优先，本地优先，远端兜底。
      final routeStartMs = (payload['start'] is int)
          ? payload['start'] as int
          : (payload['positionMs'] is int)
              ? payload['positionMs'] as int
              : null;

      final resumeMs = await progressRepository.getResumePositionMs(
        fileId: fileId,
        routeStartMs: routeStartMs,
      );

      final playData = await api.getPlayUrl(fileId);
      final url = extractPlayableUrl(playData);
      final headers = extractPlayableHeaders(playData);
      if (url == null || url.isEmpty) {
        state = state.copyWith(loading: false, error: '获取播放地址失败');
        return;
      }

      state = state.copyWith(
        playUrl: url,
        playHeaders: headers,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );

      _lastOpenAt = DateTime.now();
      _introSkippedForCurrentMedia = false;
      _outroSkipTriggered = false;
      await service.openUrl(
        url,
        headers: headers,
        start: resumeMs != null ? Duration(milliseconds: resumeMs) : null,
      );
      try {
        await _applyPlaylistModeToService(state.playlistMode);
      } catch (_) {}
      state = state.copyWith(loading: false, error: null);

      unawaited(
        progressRepository
            .enqueueOpenReport(
              fileId: fileId,
              coreId: state.coreId,
              mediaType: state.mediaType,
              positionMs: resumeMs ?? 0,
              durationMs: state.duration == Duration.zero
                  ? null
                  : state.duration.inMilliseconds,
              title: state.title,
              coverUrl: state.posterUrl,
            )
            .catchError((_) {}),
      );

      _progressTracker.start(_snapshot);
      recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  /// 解析路由参数中的选集列表。
  ///
  /// 兼容两种输入：
  /// - `List<EpisodeDetail>`
  /// - `List<Map<String, dynamic>>`
  List<EpisodeDetail> _parseEpisodes(Object? raw) {
    if (raw is! List) return const [];
    final parsed = <EpisodeDetail>[];
    for (final e in raw) {
      if (e is EpisodeDetail) {
        parsed.add(e);
      } else if (e is Map) {
        parsed.add(EpisodeDetail.fromJson(e.cast<String, dynamic>()));
      }
    }
    return parsed;
  }

  /// 确保选集列表已准备好。
  ///
  /// - 若路由参数已传入 episodes，则不再请求后端。
  /// - 否则按当前 fileId 请求 /api/media/file/{file_id}/episodes。
  Future<void> _ensureEpisodesLoaded({required int fileId}) async {
    // 不再按媒体类型区分，统一基于 fileId 拉取选集列表，
    // 以兼容“最近观看”等只携带 fileId 的入口，同时支持电影的单集选集展示。
    if (state.episodes.isNotEmpty) {
      syncTitleForCurrentEpisode();
      recomputeEpisodeNav();
      return;
    }
    if (state.episodesLoading) return;

    state = state.copyWith(episodesLoading: true, episodesError: null);

    try {
      final res = await api.getEpisodes(fileId);
      state = state.copyWith(
        episodes: res.episodes,
        seasonVersionId: res.seasonVersionId,
        episodesLoading: false,
        episodesError: null,
      );
      syncTitleForCurrentEpisode();
      recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(episodesLoading: false, episodesError: '$e');
    }
  }

  Future<void> toggleControls() async {
    state = state.copyWith(controlsVisible: !state.controlsVisible);
  }

  void toggleLock() {
    final next = !state.isLocked;
    // 切换锁屏时强制显示控制层，确保用户随时可见解锁按钮。
    state = state.copyWith(isLocked: next, controlsVisible: true);
  }

  Future<void> playPause() => service.playPause();
  Future<void> stop() => service.stop();
  Future<void> seek(Duration position) => service.seek(position);

  Future<void> seekRelative(Duration delta) => service.seekRelative(delta);

  Future<void> setVolume(double volume) => service.setVolume(volume);
  Future<void> setSpeed(double speed) => service.setSpeed(speed);

  Future<void> setFit(BoxFit fit) async {
    state = state.copyWith(fit: fit);
    await _persistVideoSpecificSettings();
  }

  /// 设置画面缩放与位置（用于手势缩放/拖动）。
  void setVideoTransform({required double scale, required Offset offset}) {
    state = state.copyWith(videoScale: scale, videoOffset: offset);
    // 手势操作频繁，这里建议通过防抖或仅在结束时保存，但为了简化逻辑暂且在每次确定的设置变更时保存。
    // 注意：如果是连续手势，建议在手势结束时调用单独的 save 方法。
    // 这里假设 setVideoTransform 是手势过程中的实时调用，因此不在此处保存。
    // 应该提供一个 saveVideoTransform 方法供手势结束时调用。
  }

  /// 手势结束时保存画面状态
  Future<void> saveVideoTransform() async {
    await _persistVideoSpecificSettings();
  }

  /// 重置画面缩放与位置。
  void resetVideoTransform() {
    state = state.copyWith(videoScale: 1.0, videoOffset: Offset.zero);
  }

  Future<void> setPlaylistMode(PlaylistMode mode) async {
    state = state.copyWith(playlistMode: mode);
    await _settingsPersistence.savePlaylistMode(mode);
    try {
      await _applyPlaylistModeToService(mode);
    } catch (_) {}
  }

  Future<void> setVideoTrack(VideoTrack track) => service.setVideoTrack(track);

  /// 设置音轨。
  ///
  /// 说明：音轨切换可能触发底层解码器重建，先更新状态以保证 UI 立即反馈。
  Future<void> setAudioTrack(AudioTrack track) async {
    final current = state.selectedAudioTrack;
    if (current?.id == track.id) return;
    if (_audioSwitching) return;

    _audioSwitching = true;
    state = state.copyWith(selectedAudioTrack: track);
    unawaited(
      service
          .setAudioTrack(track)
          .catchError((_) {})
          .whenComplete(() => _audioSwitching = false),
    );
  }

  Future<void> setSubtitleTrack(SubtitleTrack track) async {
    final current = state.selectedSubtitleTrack;
    if (current?.id == track.id) return;
    if (_subtitleSwitching) return;

    _subtitleSwitching = true;
    // 先更新选中状态，保证 UI 立即反馈。
    state = state.copyWith(selectedSubtitleTrack: track);
    // 字幕切换可能涉及解码器重新加载，使用异步方式避免阻塞 UI 事件处理。
    unawaited(
      service
          .setSubtitleTrack(track)
          .catchError((_) {})
          .whenComplete(() => _subtitleSwitching = false),
    );
  }

  Future<void> setFullscreen(bool fullscreen) async {
    state = state.copyWith(isFullscreen: fullscreen);
    try {
      if (fullscreen) {
        await SystemChrome.setEnabledSystemUIMode(
          SystemUiMode.immersiveSticky,
          overlays: [],
        );
        await SystemChrome.setPreferredOrientations([
          DeviceOrientation.landscapeLeft,
          DeviceOrientation.landscapeRight,
        ]);
      } else {
        await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
        await SystemChrome.setPreferredOrientations(DeviceOrientation.values);
      }
    } catch (_) {}
  }

  Future<void> toggleFullscreen() async {
    await setFullscreen(!state.isFullscreen);
  }

  Future<void> selectCandidate(int index) async {
    final candidates = state.candidates;
    if (index < 0 || index >= candidates.length) return;
    final fileId = candidates[index].fileId;
    try {
      state = state.copyWith(
        loading: true,
        error: null,
        selectedCandidateIndex: index,
        fileId: fileId,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );
      final resumeMs = await progressRepository.getResumePositionMs(
        fileId: fileId,
      );
      final playData = await api.getPlayUrl(fileId);
      final url = extractPlayableUrl(playData);
      final headers = extractPlayableHeaders(playData);
      if (url == null || url.isEmpty) {
        state = state.copyWith(loading: false, error: '获取播放地址失败');
        return;
      }
      state = state.copyWith(
        playUrl: url,
        playHeaders: headers,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );
      await service.openUrl(
        url,
        headers: headers,
        start: resumeMs != null ? Duration(milliseconds: resumeMs) : null,
      );
      try {
        await _applyPlaylistModeToService(state.playlistMode);
      } catch (_) {}
      state = state.copyWith(loading: false);
      unawaited(
        progressRepository
            .enqueueOpenReport(
              fileId: fileId,
              coreId: state.coreId,
              mediaType: state.mediaType,
              positionMs: resumeMs ?? 0,
              durationMs: state.duration == Duration.zero
                  ? null
                  : state.duration.inMilliseconds,
              title: state.title,
              coverUrl: state.posterUrl,
            )
            .catchError((_) {}),
      );
      _progressTracker.start(_snapshot);
      recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  /// 根据选集索引播放指定剧集。
  Future<void> openEpisodeAtIndex(int index) async {
    final episodes = state.episodes;
    if (index < 0 || index >= episodes.length) return;
    await _openEpisode(episodes[index]);
  }

  Future<void> playPrevEpisode() async {
    final next = resolveAdjacentEpisode(previous: true);
    if (next == null) return;
    final episode = findEpisodeByFirstAssetFileId(next);
    if (episode != null) {
      await _openEpisode(episode);
      return;
    }
    await _openEpisodeFileId(next);
  }

  Future<void> playNextEpisode() async {
    final next = resolveAdjacentEpisode(previous: false);
    if (next == null) return;
    final episode = findEpisodeByFirstAssetFileId(next);
    if (episode != null) {
      await _openEpisode(episode);
      return;
    }
    await _openEpisodeFileId(next);
  }

  Future<void> updateSettings(PlaybackSettings settings) async {
    final bool specificChanged =
        settings.introTime != state.settings.introTime ||
            settings.outroTime != state.settings.outroTime ||
            settings.applyToAllEpisodes != state.settings.applyToAllEpisodes;

    state = state.copyWith(settings: settings);
    await _settingsPersistence.saveGlobalSettings(settings);

    if (specificChanged) {
      await _persistVideoSpecificSettings();
    }

    assert(() {
      debugPrint('[PlaybackNotifier] Settings saved: '
          'skipIntroOutro=${settings.skipIntroOutro}, '
          'introTime=${settings.introTime}, '
          'outroTime=${settings.outroTime}, '
          'fileId=${state.fileId}, '
          'seasonVersionId=${state.seasonVersionId}, '
          'specificChanged=$specificChanged');
      return true;
    }());
  }

  @override
  void dispose() {
    _shutdown();
    super.dispose();
  }

  void _shutdown() {
    unawaited(_progressTracker.reportClose(_snapshot()).catchError((_) {}));
    _progressTracker.dispose();
    _playingSub?.cancel();
    _bufferingSub?.cancel();
    _posSub?.cancel();
    _durSub?.cancel();
    _bufSub?.cancel();
    _volSub?.cancel();
    _speedSub?.cancel();
    _completedSub?.cancel();
    _tracksSub?.cancel();
    _trackSub?.cancel();
    try {
      unawaited(
        SystemChrome.setEnabledSystemUIMode(
          SystemUiMode.edgeToEdge,
        ).catchError((_) {}),
      );
      unawaited(
        SystemChrome.setPreferredOrientations(
          DeviceOrientation.values,
        ).catchError((_) {}),
      );
      unawaited(WakelockPlus.disable().catchError((_) {}));
    } catch (_) {}
  }

  void _bindPlayerStreams() {
    _playingSub = service.playingStream.listen((v) {
      state = state.copyWith(playing: v);
      if (!v) {
        unawaited(_progressTracker.saveLocalProgress(_snapshot()).catchError((_) {}));
      }
    });
    _bufferingSub = service.bufferingStream.listen((v) {
      state = state.copyWith(buffering: v);
    });
    _posSub = service.positionStream.listen((v) {
      state = state.copyWith(position: v);
      _maybeApplySkipIntroOutro();
    });
    _durSub = service.durationStream.listen((v) {
      state = state.copyWith(duration: v);
    });
    _bufSub = service.bufferStream.listen((v) {
      state = state.copyWith(buffered: v);
    });
    _volSub = service.volumeStream.listen((v) {
      state = state.copyWith(volume: v);
    });
    _speedSub = service.speedStream.listen((v) {
      state = state.copyWith(speed: v);
    });
    _completedSub = service.completedStream.listen((completed) {
      if (!completed) return;

      /// 防止以下场景误触发自动下一集：
      /// 1) 切集/重开媒体时底层先 stop 再 open；
      /// 2) 模拟器/解码异常导致短暂 completed 事件抖动。
      /// 仅当“非加载中 + 已接近片尾”时才自动播放下一集。
      final lastOpenAt = _lastOpenAt;
      if (state.loading) return;
      if (lastOpenAt != null &&
          DateTime.now().difference(lastOpenAt) < const Duration(seconds: 2)) {
        return;
      }
      final d = state.duration;
      if (d == Duration.zero) return;
      if (state.position + const Duration(seconds: 2) < d) return;
      unawaited(_handlePlaybackCompleted());
    });
    _tracksSub = service.tracksStream.listen((tracks) {
      state = state.copyWith(
        videoTracks: tracks.video,
        audioTracks: tracks.audio,
        subtitleTracks: tracks.subtitle,
      );
    });
    _trackSub = service.trackStream.listen((track) {
      state = state.copyWith(
        selectedVideoTrack: track.video,
        selectedAudioTrack: track.audio,
        selectedSubtitleTrack: track.subtitle,
      );
    });
  }

  /// 打开指定选集。
  ///
  /// 规则：默认选择该集的第一个资源作为播放文件，并刷新候选资源列表。
  Future<void> _openEpisode(EpisodeDetail episode) async {
    if (episode.assets.isEmpty) {
      state = state.copyWith(error: '当前剧集没有可播放资源');
      return;
    }

    final fileId = episode.assets.first.fileId;
    await _openEpisodeFileId(
      fileId,
      candidates: episode.assets,
      selectedCandidateIndex: 0,
    );
  }

  /// 打开一个剧集文件 ID，并按需同步候选资源与标题。
  Future<void> _openEpisodeFileId(
    int fileId, {
    List<AssetItem>? candidates,
    int? selectedCandidateIndex,
    bool restoreProgress = true,
  }) async {
    try {
      state = state.copyWith(
        loading: true,
        error: null,
        fileId: fileId,
        currentEpisodeFileId: fileId,
        candidates: candidates,
        selectedCandidateIndex: selectedCandidateIndex,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );
      syncTitleForCurrentEpisode();
      final resumeMs = restoreProgress
          ? await progressRepository.getResumePositionMs(fileId: fileId)
          : null;
      final playData = await api.getPlayUrl(fileId);
      final url = extractPlayableUrl(playData);
      final headers = extractPlayableHeaders(playData);
      if (url == null || url.isEmpty) {
        state = state.copyWith(loading: false, error: '获取播放地址失败');
        return;
      }
      state = state.copyWith(
        playUrl: url,
        playHeaders: headers,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );

      _lastOpenAt = DateTime.now();
      _introSkippedForCurrentMedia = false;
      _outroSkipTriggered = false;
      await service.openUrl(
        url,
        headers: headers,
        start: resumeMs != null ? Duration(milliseconds: resumeMs) : null,
      );
      try {
        await _applyPlaylistModeToService(state.playlistMode);
      } catch (_) {}
      state = state.copyWith(loading: false);
      unawaited(
        progressRepository
            .enqueueOpenReport(
              fileId: fileId,
              coreId: state.coreId,
              mediaType: state.mediaType,
              positionMs: resumeMs ?? 0,
              durationMs: state.duration == Duration.zero
                  ? null
                  : state.duration.inMilliseconds,
              title: state.title,
              coverUrl: state.posterUrl,
            )
            .catchError((_) {}),
      );
      _progressTracker.start(_snapshot);
      recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  void _maybeApplySkipIntroOutro() {
    final s = state.settings;
    if (!s.skipIntroOutro) return;
    if (state.duration == Duration.zero) return;
    // 加载中不触发（防重入：切集时 position 流仍在回调）。
    if (state.loading) return;

    const graceWindow = Duration(seconds: 5);

    // 片头跳过：
    // - 首次加载（_introSkippedForCurrentMedia == false）：position < introTime 即跳过
    // - 之后：仅当用户手动拖入 introTime 前 5 秒窗口内才跳过
    if (s.introTime > Duration.zero) {
      if (!_introSkippedForCurrentMedia && state.position < s.introTime) {
        _introSkippedForCurrentMedia = true;
        unawaited(service.seek(s.introTime));
        return;
      }
      if (_introSkippedForCurrentMedia &&
          state.position >= s.introTime - graceWindow &&
          state.position < s.introTime) {
        unawaited(service.seek(s.introTime));
        return;
      }
    }

    // 片尾跳过：仅在 outroTime 前 5 秒窗口内触发一次。
    // 用户手动拖过 outroTime 则不强制跳回。
    if (!_outroSkipTriggered &&
        s.outroTime > Duration.zero &&
        state.position >= s.outroTime - graceWindow &&
        state.position < s.outroTime) {
      _introSkippedForCurrentMedia = false;
      _outroSkipTriggered = true;
      unawaited(_handlePlaybackCompleted(fromOutroSkip: true));
      return;
    }
  }

  /// 将 UI 侧的播放模式（连续播放/单集循环/不循环）映射为底层播放器的循环策略。
  ///
  /// 说明：
  /// - UI 的“连续播放”需要依赖 completed 事件切换到下一集；
  /// - 若把底层设置为 PlaylistMode.loop，在“单文件播放”场景会表现为单集循环，导致无法触发下一集逻辑；
  /// - 因此连续播放时强制把底层循环关闭（none），由上层负责切集。
  PlaylistMode _toUnderlyingPlaylistMode(PlaylistMode mode) {
    if (mode == PlaylistMode.loop) return PlaylistMode.none;
    return mode;
  }

  /// 将当前播放模式同步到播放器底层。
  Future<void> _applyPlaylistModeToService(PlaylistMode mode) async {
    await service.setPlaylistMode(_toUnderlyingPlaylistMode(mode));
  }

  /// 播放结束后的模式分发逻辑。
  ///
  /// - 连续播放：自动播放下一集（若无下一集则停留在结束态）
  /// - 单集循环：从头重新播放当前集
  /// - 不循环：不做额外动作（保持结束态）
  Future<void> _handlePlaybackCompleted({bool fromOutroSkip = false}) async {
    // 片尾跳过时，如果有下一集则强制连播（用户配置片尾时间的意图就是跳到下一集）。
    if (fromOutroSkip) {
      final next = resolveAdjacentEpisode(previous: false);
      if (next != null) {
        await playNextEpisode();
        return;
      }
    }

    switch (state.playlistMode) {
      case PlaylistMode.loop:
        await playNextEpisode();
        return;
      case PlaylistMode.single:
        await service.seek(Duration.zero);
        await service.play();
        return;
      case PlaylistMode.none:
        return;
    }
  }

  /// 从持久化层加载视频特定设置并应用到 state。
  Future<void> _loadVideoSpecificSettingsFromPersistence() async {
    final result = await _settingsPersistence.loadVideoSpecificSettings(
      fileId: state.fileId,
      seasonVersionId: state.seasonVersionId,
    );

    assert(() {
      debugPrint('[PlaybackNotifier] Video settings loaded: '
          'fileId=${state.fileId}, '
          'seasonVersionId=${state.seasonVersionId}, '
          'introTime=${result.introTime}, '
          'outroTime=${result.outroTime}, '
          'applyToAll=${result.applyToAllEpisodes}');
      return true;
    }());

    if (result.introTime == null && result.outroTime == null) return;

    state = state.copyWith(
      settings: state.settings.copyWith(
        introTime: result.introTime ?? state.settings.introTime,
        outroTime: result.outroTime ?? state.settings.outroTime,
        applyToAllEpisodes:
            result.applyToAllEpisodes ?? state.settings.applyToAllEpisodes,
      ),
      fit: result.fit ?? state.fit,
      videoScale: result.videoScale ?? state.videoScale,
      videoOffset: result.videoOffset ?? state.videoOffset,
    );
  }

  /// 将当前视频特定设置持久化。
  Future<void> _persistVideoSpecificSettings() async {
    await _settingsPersistence.saveVideoSpecificSettings(
      fileId: state.fileId,
      seasonVersionId: state.seasonVersionId,
      settings: state.settings,
      fit: state.fit,
      videoScale: state.videoScale,
      videoOffset: state.videoOffset,
      applyToAll: state.settings.applyToAllEpisodes,
    );
  }

}
