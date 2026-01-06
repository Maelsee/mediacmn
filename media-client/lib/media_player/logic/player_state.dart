import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

/// 播放器状态类
///
/// 包含播放器的所有状态信息，用于 UI 响应式更新。
class MediaPlayerState {
  final bool playing;
  final Duration position;
  final Duration duration;
  final bool buffering;
  final double volume;
  final double rate;
  final Tracks tracks;
  final Track track;
  final String? error;
  final bool isCompleted;
  final VideoController? videoController;
  final bool hardwareAccelerationEnabled;
  // 当前播放的文件ID
  final int? fileId;

  const MediaPlayerState({
    this.playing = false,
    this.position = Duration.zero,
    this.duration = Duration.zero,
    this.buffering = false,
    this.volume = 100.0,
    this.rate = 1.0,
    this.tracks = const Tracks(audio: [], video: [], subtitle: []),
    this.track = const Track(),
    this.error,
    this.isCompleted = false,
    this.videoController,
    this.hardwareAccelerationEnabled = true,
    this.fileId,
  });

  MediaPlayerState copyWith({
    bool? playing,
    Duration? position,
    Duration? duration,
    bool? buffering,
    double? volume,
    double? rate,
    Tracks? tracks,
    Track? track,
    String? error,
    bool? isCompleted,
    VideoController? videoController,
    bool? hardwareAccelerationEnabled,
    int? fileId,
  }) {
    return MediaPlayerState(
      playing: playing ?? this.playing,
      position: position ?? this.position,
      duration: duration ?? this.duration,
      buffering: buffering ?? this.buffering,
      volume: volume ?? this.volume,
      rate: rate ?? this.rate,
      tracks: tracks ?? this.tracks,
      track: track ?? this.track,
      error: error ?? this.error,
      isCompleted: isCompleted ?? this.isCompleted,
      videoController: videoController ?? this.videoController,
      hardwareAccelerationEnabled:
          hardwareAccelerationEnabled ?? this.hardwareAccelerationEnabled,
      fileId: fileId ?? this.fileId,
    );
  }
}
