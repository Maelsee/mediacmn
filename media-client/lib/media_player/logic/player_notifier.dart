import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import '../core/media_service.dart';
import '../core/video_controller_service.dart';
import '../player_source.dart';
import 'player_state.dart';

/// 播放器状态提供者
final playerProvider =
    StateNotifierProvider.autoDispose<PlayerNotifier, MediaPlayerState>((ref) {
  return PlayerNotifier();
});

/// 播放器控制器
class PlayerNotifier extends StateNotifier<MediaPlayerState> {
  late final MediaService _mediaService;
  late final VideoControllerService _videoControllerService;

  final List<StreamSubscription> _subscriptions = [];
  Timer? _positionThrottleTimer;
  Duration _lastPosition = Duration.zero;

  PlayerNotifier() : super(const MediaPlayerState()) {
    _mediaService = MediaService();
    _videoControllerService = VideoControllerService();
    _init();
  }

  Future<void> _init() async {
    await _mediaService.initialize();
    _videoControllerService.initialize(_mediaService.player);

    // 更新初始状态
    state = state.copyWith(
      videoController: _videoControllerService.controller,
      hardwareAccelerationEnabled:
          _videoControllerService.isHardwareAccelerationEnabled,
    );

    _subscribeToStreams();
  }

  void _subscribeToStreams() {
    _subscriptions.addAll([
      _mediaService.playingStream.listen((playing) {
        state = state.copyWith(playing: playing);
      }),
      _mediaService.positionStream.listen((position) {
        // 简单的节流逻辑，防止高频刷新
        if ((position - _lastPosition).inMilliseconds.abs() > 200) {
          state = state.copyWith(position: position);
          _lastPosition = position;
        }
      }),
      _mediaService.durationStream.listen((duration) {
        state = state.copyWith(duration: duration);
      }),
      _mediaService.bufferingStream.listen((buffering) {
        state = state.copyWith(buffering: buffering);
      }),
      _mediaService.volumeStream.listen((volume) {
        state = state.copyWith(volume: volume);
      }),
      _mediaService.rateStream.listen((rate) {
        state = state.copyWith(rate: rate);
      }),
      _mediaService.tracksStream.listen((tracks) {
        state = state.copyWith(tracks: tracks);
      }),
      _mediaService.trackStream.listen((track) {
        state = state.copyWith(track: track);
      }),
      _mediaService.errorStream.listen((error) {
        state = state.copyWith(error: error);
      }),
      _mediaService.completedStream.listen((completed) {
        state = state.copyWith(isCompleted: completed);
      }),
    ]);
  }

  /// 打开播放源
  Future<void> open(PlayableSource source, {bool autoPlay = true}) async {
    try {
      await _mediaService.open(source, autoPlay: autoPlay);

      // 处理续播
      if ((source.startPositionMs ?? 0) > 0) {
        await _mediaService
            .seek(Duration(milliseconds: source.startPositionMs!));
      }
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  /// 播放
  Future<void> play() async => await _mediaService.play();

  /// 暂停
  Future<void> pause() async => await _mediaService.pause();

  /// 切换播放/暂停
  Future<void> toggle() async => await _mediaService.toggle();

  /// 跳转
  Future<void> seek(Duration position) async {
    // 立即更新状态以获得更好的 UI 响应
    state = state.copyWith(position: position);
    _lastPosition = position;
    await _mediaService.seek(position);
  }

  /// 设置音量
  Future<void> setVolume(double volume) async =>
      await _mediaService.setVolume(volume);

  /// 设置倍速
  Future<void> setRate(double rate) async => await _mediaService.setRate(rate);

  /// 切换硬件加速
  Future<void> toggleHardwareAcceleration() async {
    final newValue = !state.hardwareAccelerationEnabled;
    _videoControllerService.setHardwareAcceleration(
        _mediaService.player, newValue);
    state = state.copyWith(
      hardwareAccelerationEnabled: newValue,
      videoController: _videoControllerService.controller,
    );
  }

  /// 设置音轨
  Future<void> setAudioTrack(AudioTrack track) async =>
      await _mediaService.setAudioTrack(track);

  /// 设置字幕
  Future<void> setSubtitleTrack(SubtitleTrack track) async =>
      await _mediaService.setSubtitleTrack(track);

  /// 设置视频轨
  Future<void> setVideoTrack(VideoTrack track) async =>
      await _mediaService.setVideoTrack(track);

  @override
  void dispose() {
    for (final s in _subscriptions) {
      s.cancel();
    }
    _positionThrottleTimer?.cancel();
    _mediaService.dispose();
    super.dispose();
  }
}
