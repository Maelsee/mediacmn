/// MPV 倍速播放属性配置策略。
///
/// 根据不同速度区间自动调整 mpv 解码、缓存、丢帧等参数，
/// 在画质与流畅度之间取得平衡。
class MpvSpeedProfile {
  const MpvSpeedProfile._();

  /// 根据 [speed] 应用对应的 mpv 属性集。
  ///
  /// - [platform]：底层 mpv player.platform（dynamic 调用 setProperty）。
  /// - [speed]：目标倍速。
  /// - [debugLog]：可选的日志回调。
  static Future<void> apply(
    dynamic platform,
    double speed,
    void Function(String) debugLog,
  ) async {
    if (speed > 1.0) {
      await _applyHighSpeed(platform, speed, debugLog);
    } else {
      await _applyNormalSpeed(platform, debugLog);
    }
  }

  /// 高速播放（>1.0x）：性能优先，适当牺牲画质。
  static Future<void> _applyHighSpeed(
    dynamic platform,
    double speed,
    void Function(String) debugLog,
  ) async {
    debugLog('高速播放(${speed}x)，启用性能优先模式');

    // 同步策略：以显示器刷新率为基准重采样音频，高速时比 audio 模式更平滑
    await platform.setProperty('video-sync', 'display-resample');
    // 音调修正：必须开启，否则倍速声音像花栗鼠
    await platform.setProperty('audio-pitch-correction', 'yes');
    // 保持缓存开启，高速下需要更大的数据吞吐量
    await platform.setProperty('cache', 'yes');
    await platform.setProperty('cache-pause', 'no');

    if (speed >= 2.0) {
      debugLog('2倍速+：激进解码优化');

      // 解码器层丢帧：跟不上就直接丢，保证音频时间轴不卡
      await platform.setProperty('framedrop', 'decoder');
      // 跳过非参考帧的滤波，保留大部分画质同时降低 CPU/GPU 负载
      await platform.setProperty('vd-lavc-skiploopfilter', 'nonref');
      // 允许解码器进行非标准的快速优化
      await platform.setProperty('vd-lavc-fast', 'yes');
      // 针对特定 GPU 驱动的延迟优化
      await platform.setProperty('video-latency-hacks', 'yes');
      // 增大缓冲区：2x 速度下消费数据翻倍，需要足够缓冲应对读取抖动
      await platform.setProperty('demuxer-max-bytes', '250M');
      await platform.setProperty('demuxer-max-back-bytes', '50M');
    } else {
      // 1.0x ~ 2.0x 温和加速
      await platform.setProperty('framedrop', 'decoder');
      await platform.setProperty('vd-lavc-skiploopfilter', 'nonref');
      await platform.setProperty('vd-lavc-fast', 'no');
    }
  }

  /// 正常速度（<=1.0x）：恢复高画质体验。
  static Future<void> _applyNormalSpeed(
    dynamic platform,
    void Function(String) debugLog,
  ) async {
    debugLog('恢复正常速度模式');

    await platform.setProperty('video-sync', 'display-resample');
    await platform.setProperty('audio-pitch-correction', 'yes');
    await platform.setProperty('framedrop', 'decoder');
    await platform.setProperty('vd-lavc-skiploopfilter', 'default');
    await platform.setProperty('vd-lavc-fast', 'no');
    await platform.setProperty('video-latency-hacks', 'no');
    await platform.setProperty('cache', 'auto');
    await platform.setProperty('demuxer-max-bytes', '200M');
  }
}
