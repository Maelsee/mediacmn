import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:media_kit/media_kit.dart';

import 'playback_state.dart';

/// 设置持久化结果。
class SettingsLoadResult {
  final PlaybackSettings? settings;
  final PlaylistMode? playlistMode;
  final BoxFit? fit;
  final double? videoScale;
  final Offset? videoOffset;
  final Duration? introTime;
  final Duration? outroTime;
  final bool? applyToAllEpisodes;

  const SettingsLoadResult({
    this.settings,
    this.playlistMode,
    this.fit,
    this.videoScale,
    this.videoOffset,
    this.introTime,
    this.outroTime,
    this.applyToAllEpisodes,
  });
}

/// 播放设置持久化。
///
/// 封装所有 Hive 读写逻辑，包括全局设置、视频特定设置和播放模式。
class SettingsPersistence {
  static const _boxName = 'player_settings_box';
  static const _settingsKey = 'playback_settings_v1';
  static const _playlistModeKey = 'playlist_mode_v1';

  /// 加载全局设置和播放模式。
  Future<SettingsLoadResult> loadGlobalSettings() async {
    try {
      final box = await Hive.openBox(_boxName);

      PlaybackSettings? settings;
      final raw = box.get(_settingsKey);
      if (raw is Map) {
        final m = raw.cast<String, dynamic>();
        settings = PlaybackSettings(
          skipIntroOutro: (m['skip'] as bool?) ?? false,
          subtitleFontSize: (m['sub_size'] as num?)?.toDouble() ?? 40.0,
          subtitleBottomPadding:
              (m['sub_padding'] as num?)?.toDouble() ?? 24.0,
        );
      }

      PlaylistMode? playlistMode;
      final rawMode = box.get(_playlistModeKey);
      playlistMode = _parsePlaylistMode(rawMode);

      return SettingsLoadResult(
        settings: settings,
        playlistMode: playlistMode,
      );
    } catch (_) {
      return const SettingsLoadResult();
    }
  }

  /// 加载视频/季度特定设置（片头片尾、画面配置）。
  Future<SettingsLoadResult> loadVideoSpecificSettings({
    required int? fileId,
    required int? seasonVersionId,
  }) async {
    if (fileId == null) return const SettingsLoadResult();

    try {
      final box = await Hive.openBox(_boxName);

      // 1. 尝试加载单集配置
      final fileKey = 'video_settings_file_$fileId';
      final fileData = box.get(fileKey);

      if (fileData is Map) {
        final m = fileData.cast<String, dynamic>();
        return SettingsLoadResult(
          introTime: _parseDuration(m['intro_ms']),
          outroTime: _parseDuration(m['outro_ms']),
          applyToAllEpisodes: false,
          fit: _parseBoxFit(m['fit']),
          videoScale: (m['scale'] as num?)?.toDouble() ?? 1.0,
          videoOffset: Offset(
            (m['offset_dx'] as num?)?.toDouble() ?? 0.0,
            (m['offset_dy'] as num?)?.toDouble() ?? 0.0,
          ),
        );
      }

      // 2. 尝试加载季度/系列通用配置
      if (seasonVersionId != null) {
        final seasonKey = 'video_settings_season_$seasonVersionId';
        final seasonData = box.get(seasonKey);

        if (seasonData is Map) {
          final m = seasonData.cast<String, dynamic>();
          return SettingsLoadResult(
            introTime: _parseDuration(m['intro_ms']),
            outroTime: _parseDuration(m['outro_ms']),
            applyToAllEpisodes: true,
            fit: _parseBoxFit(m['fit']),
            videoScale: (m['scale'] as num?)?.toDouble() ?? 1.0,
            videoOffset: Offset(
              (m['offset_dx'] as num?)?.toDouble() ?? 0.0,
              (m['offset_dy'] as num?)?.toDouble() ?? 0.0,
            ),
          );
        }
      }
    } catch (_) {}

    return const SettingsLoadResult();
  }

  /// 保存全局设置。
  Future<void> saveGlobalSettings(PlaybackSettings settings) async {
    try {
      final box = await Hive.openBox(_boxName);
      final globalData = {
        'skip': settings.skipIntroOutro,
        'sub_size': settings.subtitleFontSize,
        'sub_padding': settings.subtitleBottomPadding,
      };
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

  /// 保存视频特定设置。
  Future<void> saveVideoSpecificSettings({
    required int? fileId,
    required int? seasonVersionId,
    required PlaybackSettings settings,
    required BoxFit fit,
    required double videoScale,
    required Offset videoOffset,
    bool applyToAll = false,
  }) async {
    if (fileId == null) {
      assert(() {
        debugPrint('[SettingsPersistence] saveVideoSpecificSettings skipped: fileId is null');
        return true;
      }());
      return;
    }

    try {
      final box = await Hive.openBox(_boxName);
      final data = {
        'intro_ms': settings.introTime == kUnsetDuration ? -1 : settings.introTime.inMilliseconds,
        'outro_ms': settings.outroTime == kUnsetDuration ? -1 : settings.outroTime.inMilliseconds,
        'fit': fit.name,
        'scale': videoScale,
        'offset_dx': videoOffset.dx,
        'offset_dy': videoOffset.dy,
        'updated_at': DateTime.now().millisecondsSinceEpoch,
      };

      final key = applyToAll && seasonVersionId != null
          ? 'video_settings_season_$seasonVersionId'
          : 'video_settings_file_$fileId';
      await box.put(key, data);
      if (applyToAll && seasonVersionId != null) {
        await box.delete('video_settings_file_$fileId');
      }

      assert(() {
        debugPrint('[SettingsPersistence] Saved video settings: '
            'key=$key, intro_ms=${data['intro_ms']}, outro_ms=${data['outro_ms']}');
        return true;
      }());
    } catch (_) {}
  }

  /// 保存播放模式。
  Future<void> savePlaylistMode(PlaylistMode mode) async {
    try {
      final box = await Hive.openBox(_boxName);
      await box.put(_playlistModeKey, mode.name);
    } catch (_) {}
  }

  static PlaylistMode _parsePlaylistMode(Object? raw) {
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

  static BoxFit _parseBoxFit(String? name) {
    if (name == null) return BoxFit.contain;
    return BoxFit.values.firstWhere(
      (e) => e.name == name,
      orElse: () => BoxFit.contain,
    );
  }

  static Duration _parseDuration(Object? raw) {
    final ms = (raw as int?) ?? -1;
    if (ms < 0) return kUnsetDuration;
    return Duration(milliseconds: ms);
  }
}
