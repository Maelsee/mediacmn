import 'package:flutter/foundation.dart';
import 'package:media_kit/media_kit.dart';

/// 高性能播放器状态管理器
///
/// 使用ValueNotifier减少不必要的UI重建，
/// 提供更流畅的控制响应
class PlayerStateManager {
  final Player _player;

  // 使用ValueNotifier替代多个StreamSubscription
  final ValueNotifier<bool> _playingNotifier = ValueNotifier(false);
  final ValueNotifier<Duration> _positionNotifier = ValueNotifier(Duration.zero);
  final ValueNotifier<Duration> _durationNotifier = ValueNotifier(Duration.zero);
  final ValueNotifier<bool> _bufferingNotifier = ValueNotifier(false);
  final ValueNotifier<List<AudioTrack>> _audioTracksNotifier = ValueNotifier([]);
  final ValueNotifier<List<SubtitleTrack>> _subtitleTracksNotifier = ValueNotifier([]);

  // 节流控制 - 避免过于频繁的状态更新
  Duration _lastPositionUpdate = Duration.zero;
  static const Duration _positionThrottle = Duration(milliseconds: 200);

  PlayerStateManager(this._player) {
    _initializeListeners();
  }

  void _initializeListeners() {
    // 播放状态监听
    _player.stream.playing.listen((isPlaying) {
      if (_playingNotifier.value != isPlaying) {
        _playingNotifier.value = isPlaying;
      }
    });

    // 位置监听 - 带节流控制
    _player.stream.position.listen((position) {
      final now = DateTime.now().millisecondsSinceEpoch;
      final lastUpdate = _lastPositionUpdate.inMilliseconds;

      // 节流：只有变化超过200ms或跳跃超过1秒才更新
      if (now - lastUpdate > _positionThrottle.inMilliseconds ||
          (position - _lastPositionUpdate).inMilliseconds.abs() > 1000) {
        _positionNotifier.value = position;
        _lastPositionUpdate = position;
      }
    });

    // 时长监听
    _player.stream.duration.listen((duration) {
      if (_durationNotifier.value != duration) {
        _durationNotifier.value = duration;
      }
    });

    // 缓冲状态监听
    _player.stream.buffering.listen((isBuffering) {
      if (_bufferingNotifier.value != isBuffering) {
        _bufferingNotifier.value = isBuffering;
      }
    });

    // 轨道监听
    _player.stream.tracks.listen((tracks) {
      _audioTracksNotifier.value = tracks.audio;
      _subtitleTracksNotifier.value = tracks.subtitle;
    });
  }

  // Getters for ValueNotifiers
  ValueNotifier<bool> get playingNotifier => _playingNotifier;
  ValueNotifier<Duration> get positionNotifier => _positionNotifier;
  ValueNotifier<Duration> get durationNotifier => _durationNotifier;
  ValueNotifier<bool> get bufferingNotifier => _bufferingNotifier;
  ValueNotifier<List<AudioTrack>> get audioTracksNotifier => _audioTracksNotifier;
  ValueNotifier<List<SubtitleTrack>> get subtitleTracksNotifier => _subtitleTracksNotifier;

  // 获取当前状态的便捷方法
  bool get isPlaying => _playingNotifier.value;
  Duration get position => _positionNotifier.value;
  Duration get duration => _durationNotifier.value;
  bool get isBuffering => _bufferingNotifier.value;
  List<AudioTrack> get audioTracks => _audioTracksNotifier.value;
  List<SubtitleTrack> get subtitleTracks => _subtitleTracksNotifier.value;

  // 允许直接更新位置（用于进度条拖拽）
  void updatePosition(Duration position) {
    _positionNotifier.value = position;
  }

  void dispose() {
    _playingNotifier.dispose();
    _positionNotifier.dispose();
    _durationNotifier.dispose();
    _bufferingNotifier.dispose();
    _audioTracksNotifier.dispose();
    _subtitleTracksNotifier.dispose();
  }
}