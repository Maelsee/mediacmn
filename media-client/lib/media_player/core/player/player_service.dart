import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

import 'mpv_speed_profile.dart';
import 'player_config.dart';

/// 播放器服务抽象。
///
/// 用于隔离 UI/状态层与具体播放器实现，方便测试时注入假实现。
abstract class PlayerServiceBase {
  /// 视频控制器（用于渲染 Video Widget）。
  VideoController? get videoController;

  /// 播放状态流。
  Stream<bool> get playingStream;

  /// 缓冲状态流。
  Stream<bool> get bufferingStream;

  /// 播放位置流。
  Stream<Duration> get positionStream;

  /// 媒体时长流。
  Stream<Duration> get durationStream;

  /// 已缓冲时长流。
  Stream<Duration> get bufferStream;

  /// 音量流。
  Stream<double> get volumeStream;

  /// 倍速流。
  Stream<double> get speedStream;

  /// 播放完成流。
  Stream<bool> get completedStream;

  /// 轨道列表流（视频、音频、字幕）。
  Stream<Tracks> get tracksStream;

  /// 当前选中轨道流。
  Stream<Track> get trackStream;

  /// 打开一个媒体 URL。
  Future<void> openUrl(
    String url, {
    /// 可选的 HTTP 请求头（用于 WebDAV BasicAuth 等）。
    Map<String, String>? headers,
    Duration? start,
    bool play,
  });

  /// 开始播放。
  Future<void> play();

  /// 暂停播放。
  Future<void> pause();

  /// 停止播放。
  Future<void> stop();

  /// 播放/暂停切换。
  Future<void> playPause();

  /// 精准跳转到指定位置。
  Future<void> seek(Duration position);

  /// 相对当前进度快进/快退。
  Future<void> seekRelative(Duration delta);

  /// 设置音量（0~100）。
  Future<void> setVolume(double volume);

  /// 设置倍速。
  Future<void> setSpeed(double speed);

  /// 静音/取消静音。
  Future<void> setMute(bool mute);

  /// 设置播放模式（单曲循环、列表循环等）。
  Future<void> setPlaylistMode(PlaylistMode mode);

  /// 设置字幕轨道。
  Future<void> setSubtitleTrack(SubtitleTrack track);

  /// 设置音频轨道（音轨）。
  Future<void> setAudioTrack(AudioTrack track);

  /// 设置视频轨道（画质）。
  Future<void> setVideoTrack(VideoTrack track);

  /// 释放资源。
  void dispose();
}

/// 基于 media_kit 的播放器服务实现。
class PlayerService implements PlayerServiceBase {
  /// media_kit 播放器。
  final Player _player;
  @override
  final VideoController videoController;
  final PlayerConfig config;

  /// 续播 seek 的容忍误差。
  ///
  /// 说明：部分解码器在 seek 后上报的位置可能略有偏差，允许一定误差视为成功。
  static const Duration _seekTolerance = Duration(milliseconds: 1200);

  /// 等待播放器时长就绪的超时时间。
  ///
  /// 说明：某些网络源在 open 返回后，duration 仍然为 0，过早 seek 可能会被忽略。
  static const Duration _durationReadyTimeout = Duration(seconds: 6);

  /// 单次 seek 成功确认的等待时间。
  static const Duration _seekConfirmTimeout = Duration(seconds: 2);

  /// 是否处于 Flutter 测试环境。
  ///
  /// 说明：测试环境下禁止发起真实网络探测，避免 HttpClient 警告与不可控失败。
  static const bool _isFlutterTest = bool.fromEnvironment('FLUTTER_TEST');

  PlayerService._({
    required Player player,
    required this.videoController,
    required this.config,
  }) : _player = player;

  factory PlayerService.create({PlayerConfig config = const PlayerConfig()}) {
    final player = Player(
      configuration: const PlayerConfiguration(
        /// 启用硬件加速解码，提升4K高帧率视频播放性能
        vo: 'gpu',
      ),
    );

    /// 针对移动端性能的激进优化配置 (通过底层属性设置)
    /// 解决 4K 60fps 2x 倍速下的音画不同步问题
    try {
      final platform = player.platform as dynamic;
      // // 自动选择最佳硬件解码器 (mediacodec/videotoolbox)
      // platform.setProperty('hwdec', 'auto');
      // // 关键：解码性能不足时，在解码层丢帧以保持音画同步
      // platform.setProperty('framedrop', 'decoder');
      // // 跳过非参考帧的去块滤波，大幅降低 CPU/GPU 负载
      // platform.setProperty('vd-lavc-skiploopfilter', 'nonref');
      // 1) 根据平台选择更合适的 hwdec 策略
      if (Platform.isAndroid) {
        // 偏稳定：优先用官方默认的 auto-safe；你想激进一点可以用 mediacodec-copy
        // platform.setProperty('hwdec', 'auto-safe');
        // 如果已知设备兼容，也可以尝试：
        platform.setProperty('hwdec', 'mediacodec');
      } else if (Platform.isIOS) {
        // iOS 上通常不需要额外设置 hwdec；保留默认即可
      } else {
        // 桌面端可按平台选择合适后端，比如：
        if (Platform.isWindows) {
          platform.setProperty('hwdec', 'd3d11va');
        } else if (Platform.isLinux) {
          platform.setProperty('hwdec', 'vaapi');
        }
      }

      // 2) 同步策略：高帧率/倍速场景建议用 display-resample
      platform.setProperty('video-sync', 'display-resample');

      // 3) 作为兜底，允许丢帧，但可以保留 decoder+vo（如果支持）
      //   如果底层版本支持 'decoder+vo'，可以改成这样；否则保留 'decoder'
      platform.setProperty('framedrop', 'decoder');

      // 4) 降低解码复杂度（你已经用的，可以保留）
      platform.setProperty('vd-lavc-skiploopfilter', 'nonref');

      // 5) 网络场景下可以适当增加缓存（本地播放可酌情调小或去掉）
      platform.setProperty('cache', 'yes');
      platform.setProperty('cache-secs', '30');
      platform.setProperty('demuxer-max-bytes', '200M');
    } catch (e) {
      debugPrint('Failed to set mpv properties: $e');
    }

    /// 配置视频控制器，优化渲染性能
    final controller = VideoController(
      player,
      configuration: const VideoControllerConfiguration(
        /// 启用硬件加速渲染
        enableHardwareAcceleration: true,
      ),
    );

    player.setVolume(config.initialVolume);
    player.setRate(config.initialSpeed);

    return PlayerService._(
      player: player,
      videoController: controller,
      config: config,
    );
  }

  /// 直接暴露底层 Player，供极少数需要读取底层状态的地方使用。
  Player get player => _player;

  @override
  Stream<bool> get playingStream => _player.stream.playing;
  @override
  Stream<bool> get bufferingStream => _player.stream.buffering;
  @override
  Stream<Duration> get positionStream => _player.stream.position;
  @override
  Stream<Duration> get durationStream => _player.stream.duration;
  @override
  Stream<Duration> get bufferStream => _player.stream.buffer;
  @override
  Stream<double> get volumeStream => _player.stream.volume;
  @override
  Stream<double> get speedStream => _player.stream.rate;
  @override
  Stream<bool> get completedStream => _player.stream.completed;
  @override
  Stream<Tracks> get tracksStream => _player.stream.tracks;
  @override
  Stream<Track> get trackStream => _player.stream.track;

  @override
  Future<void> openUrl(
    String url, {
    Map<String, String>? headers,
    Duration? start,
    bool play = true,
  }) async {
    final media = (headers == null || headers.isEmpty)
        ? Media(url)
        : Media(url, httpHeaders: headers);

    final shouldSeek = start != null && start > Duration.zero;
    bool usedNativeStart = false;

    // 优化续播逻辑：尝试使用底层 start 属性直接从指定位置开始播放
    // 避免 "0 -> seek -> 0 -> seek" 的多重跳变问题
    try {
      final platform = _player.platform as dynamic;
      if (shouldSeek) {
        // mpv start 属性支持秒数 (浮点数)
        final startSeconds = start.inMilliseconds / 1000.0;
        await platform.setProperty('start', '$startSeconds');
        usedNativeStart = true;
      } else {
        // 重置 start，避免污染下一个播放
        await platform.setProperty('start', '0');
      }
    } catch (e) {
      _debugLog('设置 start 属性失败: $e');
    }

    if (usedNativeStart) {
      // 如果使用了原生 start 属性，直接 open 即可（mpv 会处理 seek）
      await _player.open(media, play: play);
      return;
    }

    // 回退逻辑：手动 seek
    // - 先暂停打开，避免抢跑播放 0 帧导致 seek 失效或出现“先播放再跳转”。
    // - 等待 duration 就绪后再 seek，并做位置确认与重试。
    await _player.open(media, play: play && !shouldSeek);

    if (shouldSeek) {
      final target = start;

      if (kDebugMode && !_isFlutterTest) {
        final rangeSupport = await _probeHttpRangeSupport(url, headers);
        if (rangeSupport == false) {
          _debugLog('播放源可能不支持 Range 请求，续播可能失败：$url');
        }
      }

      await _waitForDurationReady();

      final ok = await _seekWithRetry(target);
      if (!ok) {
        _debugLog('续播 seek 未确认成功，可能原因：不支持 seek 或时机过早。target=$target');
      }

      final shouldVerifyReset =
          ok && target >= const Duration(seconds: 10) && play;

      if (play) {
        await _player.play();
        if (shouldVerifyReset) {
          await _reseekIfPlaybackResetsToStart(target);
        }
      }
    }
  }

  /// 在“seek 已确认成功”后，兜底处理少量播放源的“位置回跳到开头”。
  ///
  /// 说明：部分播放源在开始播放阶段会触发底层解码管线重建，导致 position 短暂回到 0 并从头播放。
  /// 本方法会在短窗口内监听 position：若曾到达目标位置后又回跳到开头，则自动执行二次 seek。
  Future<void> _reseekIfPlaybackResetsToStart(Duration target) async {
    final resetThreshold = const Duration(seconds: 2);
    final watchWindow = const Duration(seconds: 3);
    final completer = Completer<bool>();
    late final StreamSubscription sub;
    final startedAt = DateTime.now();
    // 是否已经到达过目标位置（避免首次 position=0 误判为回跳）。
    // 说明：openUrl 内部只有在 seek 已确认成功后才会调用本方法，因此这里可以基于当前 state 先做一次判断。
    var reachedTarget = _player.state.position + _seekTolerance >= target;

    sub = _player.stream.position.listen(
      (p) {
        if (!reachedTarget && p + _seekTolerance >= target) {
          reachedTarget = true;
        }

        if (p < resetThreshold) {
          if (reachedTarget) {
            if (!completer.isCompleted) completer.complete(true);
            return;
          }
        }

        if (DateTime.now().difference(startedAt) >= watchWindow) {
          if (!completer.isCompleted) completer.complete(false);
        }
      },
      onError: (_) {
        if (!completer.isCompleted) completer.complete(false);
      },
    );

    bool didReset = false;
    try {
      didReset = await completer.future.timeout(
        watchWindow,
        onTimeout: () => false,
      );
    } finally {
      await sub.cancel();
    }

    if (!didReset) return;
    _debugLog('检测到续播位置回跳到开头，尝试二次 seek。target=$target');
    await _seekWithRetry(target);
  }

  /// 探测 HTTP/HTTPS 资源是否支持 Range 请求。
  ///
  /// 返回值说明：
  /// - true：明确支持（返回 206）
  /// - false：明确不支持（返回 200）
  /// - null：无法判断（非 http(s)、网络错误、被拦截等）
  Future<bool?> _probeHttpRangeSupport(
    String url,
    Map<String, String>? headers,
  ) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return null;
    if (uri.scheme != 'http' && uri.scheme != 'https') return null;

    final client = http.Client();
    try {
      final req = http.Request('GET', uri);
      if (headers != null && headers.isNotEmpty) {
        req.headers.addAll(headers);
      }
      req.headers['Range'] = 'bytes=0-0';

      final res = await client.send(req).timeout(
        const Duration(seconds: 3),
        onTimeout: () {
          throw TimeoutException('range probe timeout');
        },
      );

      // 只取一小段，避免服务端忽略 Range 返回整文件导致大量下载。
      await res.stream.take(1).drain<void>();

      if (res.statusCode == 206) return true;
      if (res.statusCode == 200) return false;
      return null;
    } catch (_) {
      return null;
    } finally {
      client.close();
    }
  }

  /// 等待播放器的 duration 就绪（大于 0）。
  ///
  /// 说明：open 返回后，某些源的 duration 需要一段时间才能获取到。
  Future<void> _waitForDurationReady() async {
    if (_player.state.duration > Duration.zero) return;
    try {
      await _player.stream.duration
          .where((d) => d > Duration.zero)
          .first
          .timeout(_durationReadyTimeout);
    } catch (_) {
      // 超时不视为失败：后续仍会尝试 seek，并做位置确认与重试。
    }
  }

  /// 执行 seek，并通过 positionStream 确认位置是否到达目标。
  Future<bool> _seekAndConfirm(Duration target) async {
    await _player.seek(target);
    try {
      await _player.stream.position
          .where((p) => p + _seekTolerance >= target)
          .first
          .timeout(_seekConfirmTimeout);
      return true;
    } catch (_) {
      return _player.state.position + _seekTolerance >= target;
    }
  }

  /// 续播 seek 的鲁棒策略：seek + 位置确认 + 延迟重试。
  Future<bool> _seekWithRetry(Duration target) async {
    try {
      if (await _seekAndConfirm(target)) return true;
    } catch (_) {
      // 捕获底层异常后继续重试。
    }

    await Future<void>.delayed(const Duration(milliseconds: 250));
    try {
      if (await _seekAndConfirm(target)) return true;
    } catch (_) {
      return false;
    }
    return false;
  }

  /// Debug 日志输出（仅 Debug 模式生效）。
  void _debugLog(String message) {
    if (kDebugMode) {
      debugPrint('[PlayerService] $message');
    }
  }

  @override
  Future<void> play() => _player.play();
  @override
  Future<void> pause() => _player.pause();
  @override
  Future<void> stop() => _player.stop();

  @override
  Future<void> playPause() async {
    if (_player.state.playing) {
      await pause();
    } else {
      await play();
    }
  }

  @override
  Future<void> seek(Duration position) => _player.seek(position);

  @override
  Future<void> seekRelative(Duration delta) async {
    final current = _player.state.position;
    final target = current + delta;
    await seek(target < Duration.zero ? Duration.zero : target);
  }

  @override
  Future<void> setVolume(double volume) => _player.setVolume(volume);
  @override
  @override
  Future<void> setSpeed(double speed) async {
    await MpvSpeedProfile.apply(
      _player.platform as dynamic,
      speed,
      _debugLog,
    );
    await _player.setRate(speed);
  }

  @override
  Future<void> setMute(bool mute) async {
    if (mute) {
      await _player.setVolume(0);
    } else {
      final v = config.initialVolume;
      await _player.setVolume(v);
    }
  }

  @override
  Future<void> setPlaylistMode(PlaylistMode mode) =>
      _player.setPlaylistMode(mode);

  @override
  Future<void> setSubtitleTrack(SubtitleTrack track) =>
      _player.setSubtitleTrack(track);

  @override
  Future<void> setAudioTrack(AudioTrack track) => _player.setAudioTrack(track);

  @override
  Future<void> setVideoTrack(VideoTrack track) => _player.setVideoTrack(track);

  @override
  void dispose() {
    // 强制停止播放，防止 native 侧未及时释放导致声音残留
    _player.stop();
    _player.dispose();
  }
}
