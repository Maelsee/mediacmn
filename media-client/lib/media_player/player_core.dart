import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'playable_source.dart';
// import 'package:flutter/foundation.dart' show kIsWeb;

/// 媒体播放器核心类
///
/// 基于media_kit库封装的播放器核心功能，提供媒体播放的基础控制能力。
/// 该类封装了Player和VideoController，提供统一的播放控制接口。
///
/// 主要功能：
/// - 媒体打开与播放控制
/// - 音视频轨道切换
/// - 播放速度和音量控制
/// - 进度跳转
/// - 多格式支持（HLS、MP4等）
class PlayerCore {
  /// media_kit的Player实例
  /// 负责实际的媒体解码和播放
  final Player player;

  /// 视频控制器
  /// 用于在Flutter widget中显示视频内容
  late final VideoController controller;

  /// 构造函数
  /// 创建PlayerCore实例并初始化VideoController
  ///
  /// [player] media_kit的Player实例，必须已经创建
  PlayerCore(this.player) {
    controller = VideoController(player);
  }
  /// 打开并开始播放媒体源
  ///
  /// 根据PlayableSource中的配置打开媒体并自动开始播放。
  /// 支持HTTP头设置和起始位置跳转（续播功能）。
  ///
  /// [src] 可播放媒体源，包含URI、请求头、起始位置等信息
  ///
  /// 异常处理：
  /// - 起始位置跳转失败不会影响播放开始
  /// - 网络错误、格式不支持等异常会向上传播
  Future<void> open(PlayableSource src) async {
    // 使用Media对象封装URI和HTTP头
    await player.open(Media(src.uri, httpHeaders: src.headers));

    try {
      // 续播功能：跳转到上次播放位置
      final start = src.startPositionMs ?? 0;
      if (start > 0) {
        await player.seek(Duration(milliseconds: start));
      }
    } catch (_) {
      // 跳转失败不影响播放开始，静默处理
    }

    // 自动开始播放
    await player.play();
  }

  /// 开始播放
  ///
  /// 如果当前已处于播放状态，此方法不会产生任何效果
  Future<void> play() async {
    await player.play();
  }

  /// 暂停播放
  ///
  /// 如果当前已处于暂停状态，此方法不会产生任何效果
  Future<void> pause() async {
    await player.pause();
  }

  /// 切换播放/暂停状态
  ///
  /// 根据当前播放状态自动切换：
  /// - 正在播放 → 暂停
  /// - 已暂停 → 播放
  Future<void> toggle() async {
    if (player.state.playing) {
      // 使用fire-and-forget模式，不等待pause完成
      Future.microtask(() => player.pause());
    } else {
      // 使用fire-and-forget模式，不等待play完成
      Future.microtask(() => player.play());
    }
  }

  /// 快速播放 - 不等待完成
  void playFast() {
    Future.microtask(() => player.play());
  }

  /// 快速暂停 - 不等待完成
  void pauseFast() {
    Future.microtask(() => player.pause());
  }

  /// 跳转到指定播放位置
  ///
  /// [position] 目标播放位置
  Future<void> seek(Duration position) async {
    await player.seek(position);
  }

  /// 设置播放速度
  ///
  /// [rate] 播放倍速，1.0为正常速度，0.5为半速，2.0为两倍速
  Future<void> setRate(double rate) async {
    await player.setRate(rate);
  }

  /// 设置音量
  ///
  /// [volume] 音量值，范围0.0-1.0
  /// 注意：media_kit内部使用0.0-100.0的范围，这里进行了转换
  Future<void> setVolume(double volume) async {
    // media_kit 的音量范围是 0.0 ~ 100.0，需要将0.0-1.0转换为对应范围
    final v = (volume * 100.0).clamp(0.0, 100.0);
    await player.setVolume(v);
  }

  // ==================== 轨道相关方法 ====================

  /// 获取可用的视频轨道列表
  ///
  /// 返回当前媒体中包含的所有视频轨道
  List<VideoTrack> get videoTracks => player.state.tracks.video;

  /// 获取可用的音频轨道列表
  ///
  /// 返回当前媒体中包含的所有音频轨道（多语言、多音轨等）
  List<AudioTrack> get audioTracks => player.state.tracks.audio;

  /// 获取可用的字幕轨道列表
  ///
  /// 返回当前媒体中包含的所有字幕轨道
  List<SubtitleTrack> get subtitleTracks => player.state.tracks.subtitle;

  /// 设置音频轨道
  ///
  /// [track] 要切换到的音频轨道
  Future<void> setAudioTrack(AudioTrack track) async {
    await player.setAudioTrack(track);
  }

  /// 禁用音频（静音所有音频轨道）
  Future<void> setAudioNone() async {
    await player.setAudioTrack(AudioTrack.no());
  }

  /// 设置视频轨道
  ///
  /// [track] 要切换到的视频轨道
  Future<void> setVideoTrack(VideoTrack track) async {
    await player.setVideoTrack(track);
  }

  /// 设置字幕轨道
  ///
  /// [track] 要切换到的字幕轨道
  Future<void> setSubtitleTrack(SubtitleTrack track) async {
    await player.setSubtitleTrack(track);
  }

  /// 禁用字幕
  Future<void> setSubtitleNone() async {
    await player.setSubtitleTrack(SubtitleTrack.no());
  }

  /// 释放播放器资源
  ///
  /// 调用此方法后，播放器将无法再使用
  /// 应该在widget销毁时调用
  void dispose() {
    player.dispose();
  }
}
