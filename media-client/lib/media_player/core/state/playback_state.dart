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

  const PlaybackSettings({
    this.skipIntroOutro = false,
    this.introTime = Duration.zero,
    this.outroTime = Duration.zero,
    this.applyToAllEpisodes = false,
  });

  PlaybackSettings copyWith({
    bool? skipIntroOutro,
    Duration? introTime,
    Duration? outroTime,
    bool? applyToAllEpisodes,
  }) {
    return PlaybackSettings(
      skipIntroOutro: skipIntroOutro ?? this.skipIntroOutro,
      introTime: introTime ?? this.introTime,
      outroTime: outroTime ?? this.outroTime,
      applyToAllEpisodes: applyToAllEpisodes ?? this.applyToAllEpisodes,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'skip': skipIntroOutro,
      'intro_ms': introTime.inMilliseconds,
      'outro_ms': outroTime.inMilliseconds,
      'apply_all': applyToAllEpisodes,
    };
  }

  static PlaybackSettings fromJson(Map<String, dynamic> json) {
    return PlaybackSettings(
      skipIntroOutro: (json['skip'] as bool?) ?? false,
      introTime:
          Duration(milliseconds: (json['intro_ms'] as num?)?.toInt() ?? 0),
      outroTime:
          Duration(milliseconds: (json['outro_ms'] as num?)?.toInt() ?? 0),
      applyToAllEpisodes: (json['apply_all'] as bool?) ?? false,
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

final playerConfigProvider =
    Provider<PlayerConfig>((ref) => const PlayerConfig());

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

    final parsedCoreId = int.tryParse(coreId);
    final payload = extra is Map ? extra : const <String, dynamic>{};

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
    } else if (detail is Map) {
      title = (detail['name'] ?? detail['title'])?.toString();
      posterUrl = (detail['poster_path'] ??
              detail['backdrop_path'] ??
              detail['cover_url'])
          ?.toString();
      mediaType = (detail['media_type'] ?? detail['kind'])?.toString();
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
            '${payload['seasonVersionId'] ?? payload['season_version_id'] ?? ''}');

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
      await service.openUrl(url,
          headers: headers,
          start: resumeMs != null ? Duration(milliseconds: resumeMs) : null);
      state = state.copyWith(loading: false, error: null);

      unawaited(progressRepository
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
          .catchError((_) {}));

      _startLocalProgressSave();
      _recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  Future<void> reload({
    required String coreId,
    required Object? extra,
  }) async {
    _shutdown();
    _initialized = false;
    state = const PlaybackState();
    await initialize(coreId: coreId, extra: extra);
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

    state = state.copyWith(
      episodesLoading: true,
      episodesError: null,
    );

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
      state = state.copyWith(
        episodesLoading: false,
        episodesError: '$e',
      );
    }
  }

  Future<void> toggleControls() async {
    // 锁屏状态下不允许隐藏控制层，避免误触导致无法解锁。
    if (state.isLocked) return;
    state = state.copyWith(controlsVisible: !state.controlsVisible);
  }

  void showControls() {
    if (state.isLocked) return;
    if (state.controlsVisible) return;
    state = state.copyWith(controlsVisible: true);
  }

  void hideControls() {
    if (state.isLocked) return;
    if (!state.controlsVisible) return;
    state = state.copyWith(controlsVisible: false);
  }

  void showError(String message) {
    state = state.copyWith(
      loading: false,
      error: message,
      controlsVisible: true,
    );
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
  }

  /// 设置画面缩放与位置（用于手势缩放/拖动）。
  void setVideoTransform({required double scale, required Offset offset}) {
    state = state.copyWith(videoScale: scale, videoOffset: offset);
  }

  /// 重置画面缩放与位置。
  void resetVideoTransform() {
    state = state.copyWith(videoScale: 1.0, videoOffset: Offset.zero);
  }

  Future<void> setPlaylistMode(PlaylistMode mode) async {
    state = state.copyWith(playlistMode: mode);
    await service.setPlaylistMode(mode);
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
    unawaited(service
        .setAudioTrack(track)
        .catchError((_) {})
        .whenComplete(() => _audioSwitching = false));
  }

  Future<void> setSubtitleTrack(SubtitleTrack track) async {
    final current = state.selectedSubtitleTrack;
    if (current?.id == track.id) return;
    if (_subtitleSwitching) return;

    _subtitleSwitching = true;
    // 先更新选中状态，保证 UI 立即反馈。
    state = state.copyWith(selectedSubtitleTrack: track);
    // 字幕切换可能涉及解码器重新加载，使用异步方式避免阻塞 UI 事件处理。
    unawaited(service
        .setSubtitleTrack(track)
        .catchError((_) {})
        .whenComplete(() => _subtitleSwitching = false));
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
      final resumeMs =
          await progressRepository.getResumePositionMs(fileId: fileId);
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
      await service.openUrl(url,
          headers: headers,
          start: resumeMs != null ? Duration(milliseconds: resumeMs) : null);
      state = state.copyWith(loading: false);
      unawaited(progressRepository
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
          .catchError((_) {}));
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
    state = state.copyWith(settings: settings);
    await _saveSettings(settings);
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
      unawaited(SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge)
          .catchError((_) {}));
      unawaited(SystemChrome.setPreferredOrientations(DeviceOrientation.values)
          .catchError((_) {}));
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

      unawaited(playNextEpisode());
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
      title: _composeEpisodeTitle(episode),
    );
  }

  /// 打开一个剧集文件 ID，并按需同步候选资源与标题。
  Future<void> _openEpisodeFileId(
    int fileId, {
    List<AssetItem>? candidates,
    int? selectedCandidateIndex,
    String? title,
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
        title: title,
        videoScale: 1.0,
        videoOffset: Offset.zero,
      );
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
      await service.openUrl(url,
          headers: headers,
          start: resumeMs != null ? Duration(milliseconds: resumeMs) : null);
      state = state.copyWith(loading: false);
      unawaited(progressRepository
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
          .catchError((_) {}));
      _startLocalProgressSave();
      _recomputeEpisodeNav();
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  String _composeEpisodeTitle(EpisodeDetail episode) {
    final base = state.detail?.title ?? state.title;

    if (state.mediaType == 'movie') {
      return (base == null || base.isEmpty) ? episode.title : base;
    }

    final parts = <String>[];
    if (base != null && base.trim().isNotEmpty) {
      parts.add(base.trim());
    }

    final epNo = episode.episodeNumber;
    if (epNo > 0) {
      parts.add('第$epNo集');
    }

    final epTitle = episode.title.trim();
    if (epTitle.isNotEmpty) {
      parts.add(epTitle);
    }

    return parts.isEmpty ? '' : parts.join(' ');
  }

  void _syncTitleForCurrentEpisode() {
    if (state.mediaType == 'movie') return;

    final keyFileId = state.currentEpisodeFileId ?? state.fileId;
    if (keyFileId == null) return;

    final episode = _findEpisodeByFirstAssetFileId(keyFileId);
    if (episode == null) return;

    final nextTitle = _composeEpisodeTitle(episode);
    if (nextTitle.isEmpty) return;
    if (state.title == nextTitle) return;

    state = state.copyWith(title: nextTitle);
  }

  /// 根据“每集的首个资源 fileId”定位对应的选集条目。
  EpisodeDetail? _findEpisodeByFirstAssetFileId(int fileId) {
    for (final e in state.episodes) {
      if (e.assets.isEmpty) continue;
      if (e.assets.first.fileId == fileId) return e;
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
      unawaited(playNextEpisode());
      return;
    }
  }

  Future<void> _loadSettings() async {
    try {
      final box = await Hive.openBox(_settingsBox);
      final raw = box.get(_settingsKey);
      if (raw is Map) {
        final m = raw.cast<String, dynamic>();
        state = state.copyWith(settings: PlaybackSettings.fromJson(m));
      }
    } catch (_) {}
  }

  Future<void> _saveSettings(PlaybackSettings settings) async {
    try {
      final box = await Hive.openBox(_settingsBox);
      await box.put(_settingsKey, settings.toJson());
    } catch (_) {}
  }

  void _recomputeEpisodeNav() {
    if (state.mediaType == 'movie') {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }

    final current = state.fileId ?? state.currentEpisodeFileId;
    if (current == null) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }

    final episodeFileIds = _episodeFileIdList();
    if (episodeFileIds.isEmpty) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }
    final idx = episodeFileIds.indexOf(current);
    if (idx == -1) {
      state = state.copyWith(hasPrevEpisode: false, hasNextEpisode: false);
      return;
    }
    state = state.copyWith(
        hasPrevEpisode: idx > 0,
        hasNextEpisode: idx + 1 < episodeFileIds.length);
  }

  int? _resolveAdjacentEpisode({required bool previous}) {
    if (state.mediaType == 'movie') return null;

    final current = state.fileId ?? state.currentEpisodeFileId;
    if (current == null) return null;

    final episodeFileIds = _episodeFileIdList();
    if (episodeFileIds.isEmpty) return null;

    final idx = episodeFileIds.indexOf(current);
    if (idx == -1) return null;
    final nextIdx = previous ? idx - 1 : idx + 1;
    if (nextIdx < 0 || nextIdx >= episodeFileIds.length) return null;
    return episodeFileIds[nextIdx];
  }
}
