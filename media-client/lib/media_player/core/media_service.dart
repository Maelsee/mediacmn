import 'dart:async';
import 'package:media_kit/media_kit.dart';
import '../player_source.dart';

/// 媒体服务层
///
/// 封装 media_kit 的 Player 实例，提供底层播放能力。
/// 不包含任何 UI 状态逻辑，仅负责与 native 播放器通信。
class MediaService {
  final Player _player;

  MediaService() : _player = Player();

  /// 获取 Player 实例
  Player get player => _player;

  /// 播放流
  Stream<bool> get playingStream => _player.stream.playing;
  Stream<Duration> get positionStream => _player.stream.position;
  Stream<Duration> get durationStream => _player.stream.duration;
  Stream<bool> get bufferingStream => _player.stream.buffering;
  Stream<Tracks> get tracksStream => _player.stream.tracks;
  Stream<Track> get trackStream => _player.stream.track;
  Stream<String> get errorStream => _player.stream.error;
  Stream<double> get volumeStream => _player.stream.volume;
  Stream<double> get rateStream => _player.stream.rate;
  Stream<bool> get completedStream => _player.stream.completed;

  /// 初始化播放器
  Future<void> initialize() async {
    // 可以在这里进行一些全局配置
  }

  /// 打开媒体源
  Future<void> open(PlayableSource src, {bool autoPlay = true}) async {
    await _player.open(
      Media(src.uri, httpHeaders: src.headers),
      play: autoPlay,
    );
  }

  /// 播放
  Future<void> play() async {
    await _player.play();
  }

  /// 暂停
  Future<void> pause() async {
    await _player.pause();
  }

  /// 切换播放/暂停
  Future<void> toggle() async {
    await _player.playOrPause();
  }

  /// 跳转
  Future<void> seek(Duration position) async {
    await _player.seek(position);
  }

  /// 设置音量 (0.0 - 100.0)
  Future<void> setVolume(double volume) async {
    await _player.setVolume(volume);
  }

  /// 设置倍速
  Future<void> setRate(double rate) async {
    await _player.setRate(rate);
  }

  /// 设置音轨
  Future<void> setAudioTrack(AudioTrack track) async {
    await _player.setAudioTrack(track);
  }

  /// 设置字幕轨
  Future<void> setSubtitleTrack(SubtitleTrack track) async {
    await _player.setSubtitleTrack(track);
  }

  /// 设置视频轨
  Future<void> setVideoTrack(VideoTrack track) async {
    await _player.setVideoTrack(track);
  }

  /// 释放资源
  Future<void> dispose() async {
    await _player.dispose();
  }
}
