import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:floating/floating.dart';
import 'package:hive_flutter/hive_flutter.dart';
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

  const PlaybackSettings({
    this.skipIntroOutro = false,
    this.introTime = Duration.zero,
    this.outroTime = Duration.zero,
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
      introTime: Duration(
        milliseconds: (json['intro_ms'] as num?)?.toInt() ?? 0,
      ),
      outroTime: Duration(
        milliseconds: (json['outro_ms'] as num?)?.toInt() ?? 0,
      ),
      applyToAllEpisodes: (json['apply_all'] as bool?) ?? false,
      subtitleFontSize: (json['sub_size'] as num?)?.toDouble() ?? 40.0,
      subtitleBottomPadding: (json['sub_padding'] as num?)?.toDouble() ?? 24.0,
    );
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

class PlaybackNotifier extends StateNotifier<PlaybackState> {
  static const _settingsBox = 'player_settings_box';
  static const _settingsKey = 'playback_settings_v1';
  static const _playlistModeKey = 'playlist_mode_v1';

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

  /// 本地进度保存定时器（用于节流写入）。
  Timer? _localProgressTimer;

  /// 最近一次保存的进度（毫秒），用于减少重复写入。
  int _lastSavedPositionMs = -1;
  bool _initialized = false;

  /// 记录最近一次打开媒体的时间，用于抑制“切源/切集/重开”过程中误触发的自动下一集。
  DateTime? _lastOpenAt;

  /// 字幕切换中标记。
  ///
  /// 目的：避免用户连续点击导致重复切换，造成明显卡顿或长时间无响应。
  bool _subtitleSwitching = false;

  /// 音轨切换中标记。
  ///
  /// 目的：避免用户连续点击导致频繁重建解码管线，造成卡顿或长时间无响应。
  bool _audioSwitching = false;

  /// 路由入参中原始的标题文案（只在初始化时赋值一次，用于降级拼接）。
  String? _routeTitleHint;

  String? _seriesNameHint;
  int? _seasonIndexHint;

  PlaybackNotifier({
    required this.api,
    required this.service,
    required this.config,
    required this.progressRepository,
  }) : super(const PlaybackState());

  Future<void> initialize({
    required String coreId,
    required Object? extra,
  }) async {
    if (_initialized) return;
    _initialized = true;

    await _loadSettings();
    try {
      await _applyPlaylistModeToService(state.playlistMode);
    } catch (_) {}

    final parsedCoreId = int.tryParse(coreId);
    final payload = extra is Map ? extra : const <String, dynamic>{};

    final seriesNameHint =
        (payload['seriesName'] ?? payload['series_name'])?.toString();
    final seasonIndexHintRaw =
        payload['seasonIndex'] ?? payload['season_index'];
    int? seasonIndexHint;
    if (seasonIndexHintRaw is int) {
      seasonIndexHint = seasonIndexHintRaw;
    } else if (seasonIndexHintRaw != null) {
      seasonIndexHint = int.tryParse('$seasonIndexHintRaw');
    }
    if (seriesNameHint != null && seriesNameHint.trim().isNotEmpty) {
      _seriesNameHint = seriesNameHint.trim();
    }
    if (seasonIndexHint != null && seasonIndexHint > 0) {
      _seasonIndexHint = seasonIndexHint;
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
        _seriesNameHint = detail.title.trim();
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
        _seriesNameHint ??= seriesName.trim();
      }
      if (seasonIndex != null && seasonIndex > 0) {
        _seasonIndexHint ??= seasonIndex;
      }
    }

    // 仅在初始化阶段记录一次路由原始标题，用于后续无系列名/季信息时的降级处理。
    if (title != null && title.trim().isNotEmpty) {
      _routeTitleHint ??= title.trim();
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

    _syncTitleForCurrentEpisode();

    _bindPlayerStreams();

    try {
      await WakelockPlus.enable();
    } catch (_) {}

    if (fileId == null) {
      state = state.copyWith(loading: false, error: '缺少可播放的资源');
      return;
    }

    unawaited(_ensureEpisodesLoaded(fileId: fileId));

    _loadVideoSpecificSettings();

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

      _startLocalProgressSave();
      _recomputeEpisodeNav();
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
      _syncTitleForCurrentEpisode();
      _recomputeEpisodeNav();
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
      _syncTitleForCurrentEpisode();
      _recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(episodesLoading: false, episodesError: '$e');
    }
  }

  Future<void> toggleControls() async {
    // 锁屏状态下不允许隐藏控制层，避免误触导致无法解锁。
    if (state.isLocked) return;
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
    // 自动保存视频特定配置（包含 fit）
    await _saveVideoSpecificSettings(
        applyToAll: state.settings.applyToAllEpisodes);
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
    await _saveVideoSpecificSettings(
        applyToAll: state.settings.applyToAllEpisodes);
  }

  /// 重置画面缩放与位置。
  void resetVideoTransform() {
    state = state.copyWith(videoScale: 1.0, videoOffset: Offset.zero);
  }

  Future<void> setPlaylistMode(PlaylistMode mode) async {
    state = state.copyWith(playlistMode: mode);
    await _savePlaylistMode(mode);
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
      _startLocalProgressSave();
      _recomputeEpisodeNav();
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
    final next = _resolveAdjacentEpisode(previous: true);
    if (next == null) return;
    final episode = _findEpisodeByFirstAssetFileId(next);
    if (episode != null) {
      await _openEpisode(episode);
      return;
    }
    await _openEpisodeFileId(next);
  }

  Future<void> playNextEpisode() async {
    final next = _resolveAdjacentEpisode(previous: false);
    if (next == null) return;
    final episode = _findEpisodeByFirstAssetFileId(next);
    if (episode != null) {
      await _openEpisode(episode);
      return;
    }
    await _openEpisodeFileId(next);
  }

  Future<void> updateSettings(PlaybackSettings settings) async {
    // 检查 applyToAllEpisodes 是否发生变化，或者片头片尾时间是否变化
    final bool specificChanged =
        settings.introTime != state.settings.introTime ||
            settings.outroTime != state.settings.outroTime ||
            settings.applyToAllEpisodes != state.settings.applyToAllEpisodes;

    state = state.copyWith(settings: settings);
    await _saveSettings(settings);

    if (specificChanged) {
      await _saveVideoSpecificSettings(applyToAll: settings.applyToAllEpisodes);
    }
  }

  @override
  void dispose() {
    _shutdown();
    super.dispose();
  }

  void _shutdown() {
    unawaited(_reportCloseIfNeeded().catchError((_) {}));
    _localProgressTimer?.cancel();
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
        unawaited(_saveLocalProgressNow().catchError((_) {}));
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

  /// 启动本地进度保存定时器。
  ///
  /// 说明：
  /// - 播放过程中高频写本地，提升离线续播与最近观看进度的实时性。
  /// - 不在该定时器内进行远端上报，远端上报由 open/close 关键点触发。
  void _startLocalProgressSave() {
    _localProgressTimer?.cancel();
    _localProgressTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      if (!state.playing) return;
      await _saveLocalProgressNow();
    });
  }

  /// 将当前播放状态写入本地进度。
  Future<void> _saveLocalProgressNow() async {
    final fileId = state.fileId;
    if (fileId == null) return;

    final positionMs = state.position.inMilliseconds;
    if (positionMs == _lastSavedPositionMs) return;
    _lastSavedPositionMs = positionMs;

    final durationMs =
        state.duration == Duration.zero ? null : state.duration.inMilliseconds;

    await progressRepository.saveLocalProgress(
      fileId: fileId,
      coreId: state.coreId,
      mediaType: state.mediaType,
      positionMs: positionMs,
      durationMs: durationMs,
      title: state.title,
      coverUrl: state.posterUrl,
    );
  }

  /// 在退出播放器时上报一次 close 关键点。
  Future<void> _reportCloseIfNeeded() async {
    final fileId = state.fileId;
    if (fileId == null) return;

    final durationMs =
        state.duration == Duration.zero ? null : state.duration.inMilliseconds;

    await progressRepository.enqueueCloseReport(
      fileId: fileId,
      coreId: state.coreId,
      mediaType: state.mediaType,
      positionMs: state.position.inMilliseconds,
      durationMs: durationMs,
      title: state.title,
      coverUrl: state.posterUrl,
    );
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
      _syncTitleForCurrentEpisode();
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
      _startLocalProgressSave();
      _recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  int? _currentSeasonNumber() {
    final detail = state.detail;
    if (detail == null) {
      // 无详情对象时，优先使用路由携带的季序号提示。
      if (_seasonIndexHint != null && _seasonIndexHint! > 0) {
        return _seasonIndexHint;
      }
      // 若仍然缺失，但媒体类型为剧集，则默认按第 1 季展示，
      // 以提升“最近观看”等入口下的可读性。
      if (state.mediaType == 'tv' || state.mediaType == 'tv_episode') {
        return 1;
      }
      return null;
    }
    if (detail.mediaType != 'tv') {
      return null;
    }
    final vId = state.seasonVersionId;
    if (vId == null) {
      return _seasonIndexHint;
    }
    for (final season in detail.seasons ?? const []) {
      for (final version in season.versions ?? const []) {
        if (version.id == vId) {
          return season.seasonNumber;
        }
      }
    }
    return _seasonIndexHint;
  }

  String _composeEpisodeTitle(EpisodeDetail episode) {
    String seriesName = '';
    final detail = state.detail;
    if (detail != null && detail.title.trim().isNotEmpty) {
      seriesName = detail.title.trim();
    } else if (_seriesNameHint != null && _seriesNameHint!.trim().isNotEmpty) {
      seriesName = _seriesNameHint!.trim();
    }

    final parts = <String>[];
    if (seriesName.isNotEmpty) {
      parts.add(seriesName);
    }

    final seasonNo = _currentSeasonNumber();
    if (seasonNo != null && seasonNo > 0) {
      parts.add('第$seasonNo季');
    }

    final epNo = episode.episodeNumber;
    if (epNo > 0) {
      parts.add('第$epNo集');
    }

    var epTitle = episode.title.trim();
    if (epTitle.isNotEmpty) {
      final prefix = RegExp(r'^第\d+集\s*');
      epTitle = epTitle.replaceFirst(prefix, '');
      if (epTitle.isNotEmpty) {
        parts.add(epTitle);
      }
    }

    return parts.isEmpty ? '' : parts.join(' ');
  }

  void _syncTitleForCurrentEpisode() {
    final keyFileId = state.currentEpisodeFileId ?? state.fileId;
    if (keyFileId == null) return;

    final episode = _findEpisodeByFirstAssetFileId(keyFileId);
    if (episode == null) return;

    final nextTitle = _composeEpisodeTitle(episode);
    if (nextTitle.isEmpty) return;
    if (state.title == nextTitle) return;

    state = state.copyWith(title: nextTitle);
  }

  /// 根据当前文件 ID 定位对应的选集条目。
  ///
  /// 优先按“每集首个资源 fileId”匹配，保证与上一集/下一集导航使用的
  /// 键一致；若未命中（例如从“最近观看”入口进入时，fileId 可能是某集
  /// 的非首个资源），则回退在该集的所有资源中查找，确保仍能正确识别
  /// 当前所属的剧集。
  EpisodeDetail? _findEpisodeByFirstAssetFileId(int fileId) {
    // 第一步：按首个资源 fileId 快速匹配，兼容详情页传入的标准场景。
    for (final e in state.episodes) {
      if (e.assets.isEmpty) continue;
      if (e.assets.first.fileId == fileId) return e;
    }

    // 第二步：兼容“最近观看”等入口，fileId 不一定等于首个资源 fileId，
    // 在所有资源中做一次完整扫描以反查所属剧集。
    for (final e in state.episodes) {
      for (final a in e.assets) {
        if (a.fileId == fileId) return e;
      }
    }

    return null;
  }

  /// 获取用于上一集/下一集的 fileId 序列。
  ///
  /// 优先使用 state.episodes（选集面板的数据源），
  /// 若为空则回退使用 detail.seasons 结构。
  List<int> _episodeFileIdList() {
    final fromState = <int>[];
    for (final e in state.episodes) {
      if (e.assets.isEmpty) continue;
      fromState.add(e.assets.first.fileId);
    }
    if (fromState.isNotEmpty) return fromState;

    final detail = state.detail;
    if (detail == null || detail.mediaType == 'movie') return const [];

    final fromDetail = <int>[];
    for (final season in detail.seasons ?? const []) {
      for (final version in season.versions ?? const []) {
        for (final ep in version.episodes) {
          if (ep.assets.isEmpty) continue;
          fromDetail.add(ep.assets.first.fileId);
        }
      }
    }
    return fromDetail;
  }

  void _maybeApplySkipIntroOutro() {
    final s = state.settings;
    if (!s.skipIntroOutro) return;
    if (state.duration == Duration.zero) return;

    if (s.introTime > Duration.zero && state.position < s.introTime) {
      unawaited(service.seek(s.introTime));
      return;
    }

    if (s.outroTime > Duration.zero && state.position >= s.outroTime) {
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
    // 片尾跳过属于“提前结束”，同样按播放模式执行。
    // fromOutroSkip 目前仅用于语义区分，保留扩展点。
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

  Future<void> _loadSettings() async {
    try {
      final box = await Hive.openBox(_settingsBox);
      final raw = box.get(_settingsKey);
      if (raw is Map) {
        final m = raw.cast<String, dynamic>();
        state = state.copyWith(
          settings: state.settings.copyWith(
            skipIntroOutro: (m['skip'] as bool?) ?? false,
            subtitleFontSize: (m['sub_size'] as num?)?.toDouble() ?? 40.0,
            subtitleBottomPadding:
                (m['sub_padding'] as num?)?.toDouble() ?? 24.0,
          ),
        );
      }

      final rawMode = box.get(_playlistModeKey);
      final mode = _parsePlaylistMode(rawMode);
      state = state.copyWith(playlistMode: mode);
    } catch (_) {}
  }

  /// 加载当前视频或季度的片头片尾及画面配置（缩放/比例）。
  ///
  /// 优先级：单集配置 > 季度/系列配置 > 全局默认。
  Future<void> _loadVideoSpecificSettings() async {
    final fileId = state.fileId;
    final seasonId = state.seasonVersionId;
    if (fileId == null) return;

    try {
      final box = await Hive.openBox(_settingsBox);

      // 1. 尝试加载单集配置
      final fileKey = 'video_settings_file_$fileId';
      final fileData = box.get(fileKey);

      if (fileData is Map) {
        final m = fileData.cast<String, dynamic>();
        state = state.copyWith(
          settings: state.settings.copyWith(
            introTime: Duration(milliseconds: (m['intro_ms'] as int?) ?? 0),
            outroTime: Duration(milliseconds: (m['outro_ms'] as int?) ?? 0),
            applyToAllEpisodes: false,
          ),
          fit: _parseBoxFit(m['fit']),
          videoScale: (m['scale'] as num?)?.toDouble() ?? 1.0,
          videoOffset: Offset(
            (m['offset_dx'] as num?)?.toDouble() ?? 0.0,
            (m['offset_dy'] as num?)?.toDouble() ?? 0.0,
          ),
        );
        return;
      }

      // 2. 尝试加载季度/系列通用配置
      if (seasonId != null) {
        final seasonKey = 'video_settings_season_$seasonId';
        final seasonData = box.get(seasonKey);

        if (seasonData is Map) {
          final m = seasonData.cast<String, dynamic>();
          state = state.copyWith(
            settings: state.settings.copyWith(
              introTime: Duration(milliseconds: (m['intro_ms'] as int?) ?? 0),
              outroTime: Duration(milliseconds: (m['outro_ms'] as int?) ?? 0),
              applyToAllEpisodes: true,
            ),
            fit: _parseBoxFit(m['fit']),
            videoScale: (m['scale'] as num?)?.toDouble() ?? 1.0,
            videoOffset: Offset(
              (m['offset_dx'] as num?)?.toDouble() ?? 0.0,
              (m['offset_dy'] as num?)?.toDouble() ?? 0.0,
            ),
          );
          return;
        }
      }
    } catch (_) {}
  }

  /// 保存视频特定的配置（片头片尾、缩放、比例）。
  ///
  /// 根据 [applyToAll] 参数决定是保存为单集配置还是季度配置。
  Future<void> _saveVideoSpecificSettings({bool applyToAll = false}) async {
    final fileId = state.fileId;
    final seasonId = state.seasonVersionId;
    if (fileId == null) return;

    try {
      final box = await Hive.openBox(_settingsBox);

      final data = {
        'intro_ms': state.settings.introTime.inMilliseconds,
        'outro_ms': state.settings.outroTime.inMilliseconds,
        'fit': state.fit.name,
        'scale': state.videoScale,
        'offset_dx': state.videoOffset.dx,
        'offset_dy': state.videoOffset.dy,
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      };

      if (applyToAll && seasonId != null) {
        // 保存为季度配置，并清除当前集的单集配置以避免冲突
        await box.put('video_settings_season_$seasonId', data);
        await box.delete('video_settings_file_$fileId');
      } else {
        // 仅保存为单集配置
        await box.put('video_settings_file_$fileId', data);
      }
    } catch (_) {}
  }

  BoxFit _parseBoxFit(String? name) {
    if (name == null) return BoxFit.contain;
    return BoxFit.values.firstWhere(
      (e) => e.name == name,
      orElse: () => BoxFit.contain,
    );
  }

  Future<void> _saveSettings(PlaybackSettings settings) async {
    try {
      final box = await Hive.openBox(_settingsBox);
      // 仅保存全局通用设置，视频特定设置由 _saveVideoSpecificSettings 处理
      final globalData = {
        'skip': settings.skipIntroOutro,
        'sub_size': settings.subtitleFontSize,
        'sub_padding': settings.subtitleBottomPadding,
      };
      // 保留旧数据中的其他字段
      final raw = box.get(_settingsKey);
      if (raw is Map) {
        final m = raw.cast<String, dynamic>();
        m.addAll(globalData);
        await box.put(_settingsKey, m);
      } else {
        await box.put(_settingsKey, globalData);
      }
    } catch (_) {}
  }

  /// 解析本地存储的播放模式。
  ///
  /// 兼容历史版本可能存入的 int（0/1/2）或 string（枚举 name）。
  PlaylistMode _parsePlaylistMode(Object? raw) {
    if (raw is String) {
      for (final v in PlaylistMode.values) {
        if (v.name == raw) return v;
      }
      return PlaylistMode.none;
    }
    if (raw is int) {
      if (raw >= 0 && raw < PlaylistMode.values.length) {
        return PlaylistMode.values[raw];
      }
      return PlaylistMode.none;
    }
    return PlaylistMode.none;
  }

  Future<void> _savePlaylistMode(PlaylistMode mode) async {
    try {
      final box = await Hive.openBox(_settingsBox);
      await box.put(_playlistModeKey, mode.name);
    } catch (_) {}
  }

  void _recomputeEpisodeNav() {
    // 若没有任何选集列表（既没有 state.episodes，也无法从 detail 推导），
    // 则认为当前媒体不支持上一集/下一集导航，直接关闭连续播放导航能力。
    final current = state.fileId ?? state.currentEpisodeFileId;
    if (current == null) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }

    final episodeFileIds = _episodeFileIdList();
    if (episodeFileIds.length <= 1) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }

    // 默认按 fileId 在“首个资源 fileId 列表”中的位置计算上一集/下一集。
    var idx = episodeFileIds.indexOf(current);

    // 若未命中（例如当前播放的是该集的第二个或第三个资源），则退回
    // 通过选集列表查找当前 fileId 所属的剧集索引，保证“最近观看”等
    // 入口同样可以正确计算上一集/下一集。
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
      hasNextEpisode: idx + 1 < episodeFileIds.length,
    );
  }

  int? _resolveAdjacentEpisode({required bool previous}) {
    // 仅当存在至少两集可导航时才计算上一集/下一集，避免在单集场景下
    // 误触发连续播放逻辑。
    final current = state.fileId ?? state.currentEpisodeFileId;
    if (current == null) return null;

    final episodeFileIds = _episodeFileIdList();
    if (episodeFileIds.length <= 1) return null;

    // 先按“首个资源 fileId 列表”查找当前索引。
    var idx = episodeFileIds.indexOf(current);

    // 若未命中，则根据选集列表中任意资源 fileId 反查索引，
    // 解决“最近观看”入口 fileId 不等于首个资源 fileId 时
    // 连续播放无法找到下一集的问题。
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
      if (idx == -1) return null;
    }

    final nextIdx = previous ? idx - 1 : idx + 1;
    if (nextIdx < 0 || nextIdx >= episodeFileIds.length) return null;
    return episodeFileIds[nextIdx];
  }
}
