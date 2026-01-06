import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../media_library/media_provider.dart';
import 'player_source.dart';
import 'logic/player_notifier.dart';
import 'ui/common/player_layout.dart';

class MediaPlayerPage extends ConsumerStatefulWidget {
  final String coreId;
  final Object? extra;

  const MediaPlayerPage({super.key, required this.coreId, this.extra});

  @override
  ConsumerState<MediaPlayerPage> createState() => _MediaPlayerPageState();
}

class _MediaPlayerPageState extends ConsumerState<MediaPlayerPage> {
  _PlaybackReporter? _reporter;

  // 播放列表相关
  final List<Map<String, dynamic>> _episodes = [];
  int _currentEpisodeIndex = -1;
  Map<String, dynamic>? _detailMap;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _reporter?.stop();
    Future.microtask(() {
      try {
        if (mounted) {
          ref.read(mediaHomeProvider.notifier).load();
        }
      } catch (_) {}
    });
    super.dispose();
  }

  Future<void> _init({int? specificFileId}) async {
    try {
      final api = ApiClient();
      final extraMap = widget.extra as Map<String, dynamic>? ?? {};

      // 1. 获取详情
      if (_detailMap == null) {
        dynamic detail = extraMap['detail'];
        if (detail == null) {
          final cid = int.tryParse(widget.coreId);
          if (cid != null && cid > 0) {
            try {
              detail = await api.getMediaDetail(cid);
            } catch (_) {}
          }
        }

        if (detail != null) {
          if (detail is Map<String, dynamic>) {
            _detailMap = detail;
          } else {
            try {
              _detailMap = (detail as dynamic).toJson();
            } catch (_) {}
          }
        }
      }

      // 2. 确定当前播放的文件ID
      int? fileId = specificFileId;
      if (fileId == null) {
        // 统一从入口参数中解析 fileId，兼容多种类型与字段命名
        dynamic rawFileId;
        if (extraMap.containsKey('fileId')) {
          rawFileId = extraMap['fileId'];
        } else if (extraMap.containsKey('file_id')) {
          rawFileId = extraMap['file_id'];
        }

        if (rawFileId is int) {
          fileId = rawFileId;
        } else if (rawFileId is String) {
          fileId = int.tryParse(rawFileId);
        } else if (rawFileId is num) {
          fileId = rawFileId.toInt();
        }

        // 如果没有指定fileId，尝试从当前剧集获取
        if (fileId == null && _episodes.isNotEmpty) {
          // 默认播放第一集
          fileId = _episodes[0]['fileId'];
          _currentEpisodeIndex = 0;
        } else if (fileId == null && _detailMap != null) {
          // 如果没有现成的剧集列表，则尝试从详情中提取一个默认文件ID
          final fallbackEpisodes = _parseEpisodesFromDetail(_detailMap!);
          if (fallbackEpisodes.isNotEmpty) {
            fileId = fallbackEpisodes[0]['fileId'] as int?;
          }
        }
      }

      // 3. 根据文件ID拉取选集列表（优先使用后端API）
      List<Map<String, dynamic>> newEpisodes = [];
      if (fileId != null) {
        try {
          final episodeList = await api.getEpisodes(fileId);
          newEpisodes = _buildEpisodesFromApi(episodeList);
        } catch (_) {
          // 获取选集失败时不影响播放，后续使用本地详情结构兜底
        }
      }

      // 如果后端选集列表为空，则回退到详情中的季/集结构
      if (newEpisodes.isEmpty && _detailMap != null) {
        newEpisodes = _parseEpisodesFromDetail(_detailMap!);
      }

      // 4. 计算当前集数索引
      int currentIndex = _currentEpisodeIndex;
      if (fileId != null && newEpisodes.isNotEmpty) {
        final index = newEpisodes.indexWhere((e) => e['fileId'] == fileId);
        if (index != -1) {
          currentIndex = index;
        } else {
          currentIndex = 0;
          fileId = newEpisodes[0]['fileId'] as int?;
        }
      }

      final input = <String, dynamic>{
        ...extraMap,
        'detail': _detailMap,
        'fileId': fileId,
      };

      // 3. 解析源
      final adapter = DefaultSourceAdapter();
      final source = await adapter.resolve(input, api);

      // 4. 打开播放（确保点击选集后自动播放）
      final notifier = ref.read(playerProvider.notifier);
      await notifier.open(source, autoPlay: true);
      await notifier.play();

      // 5. 启动上报
      _reporter?.stop();
      if (source.fileId != null) {
        _reporter = _PlaybackReporter(
          ref: ref,
          fileId: source.fileId!,
          detail: _detailMap,
        );
        _reporter!.start();
      }

      // 6. 更新页面中的选集状态
      if (mounted) {
        setState(() {
          _episodes
            ..clear()
            ..addAll(newEpisodes);
          _currentEpisodeIndex = currentIndex;
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('播放失败: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  /// 从详情结构中解析本地选集列表（用于兜底）
  List<Map<String, dynamic>> _parseEpisodesFromDetail(
      Map<String, dynamic> detail) {
    final result = <Map<String, dynamic>>[];

    // 电视剧逻辑：Seasons -> Episodes
    final seasons = detail['seasons'];
    if (seasons is List) {
      for (final s in seasons) {
        if (s is Map) {
          final episodes = s['episodes'];
          if (episodes is List) {
            for (final e in episodes) {
              if (e is Map) {
                // 提取视频文件ID
                final assets = e['assets'];
                int? fid;
                if (assets is List) {
                  for (final a in assets) {
                    if (a is Map &&
                        (a['type'] == 'video' || a['type'] == null)) {
                      fid = a['fileId'] ?? a['file_id'];
                      break;
                    }
                  }
                }

                if (fid != null) {
                  result.add({
                    'name': '第 ${e['episode_number']} 集 ${e['name'] ?? ''}',
                    'fileId': fid,
                    'episode_number': e['episode_number'],
                  });
                }
              }
            }
          }
        }
      }
    }

    // 电影逻辑
    if (result.isEmpty) {
      // 检查是否有versions
      final versions = detail['versions'];
      if (versions is List && versions.isNotEmpty) {
        // ...
      }
    }

    return result;
  }

  /// 将后端返回的选集列表转换为前端使用的简单结构
  List<Map<String, dynamic>> _buildEpisodesFromApi(
      List<Map<String, dynamic>> episodeList) {
    final result = <Map<String, dynamic>>[];
    for (final Map<String, dynamic> e in episodeList) {
      final assets = e['assets'];
      int? fid;
      if (assets is List) {
        for (final a in assets) {
          if (a is Map) {
            final id = a['file_id'] ?? a['fileId'];
            if (id is int) {
              fid = id;
              break;
            }
          }
        }
      }

      if (fid != null) {
        final episodeNumber = e['episode_number'];
        final title = e['title'] ?? e['name'] ?? '';
        result.add({
          'name': '第 $episodeNumber 集 $title',
          'fileId': fid,
          'episode_number': episodeNumber,
        });
      }
    }
    return result;
  }

  void _playEpisode(int index) {
    if (index < 0 || index >= _episodes.length) return;
    final fileId = _episodes[index]['fileId'] as int;
    setState(() {
      _currentEpisodeIndex = index;
    });
    _init(specificFileId: fileId);
  }

  void _onNext() {
    if (_episodes.isNotEmpty && _currentEpisodeIndex < _episodes.length - 1) {
      _playEpisode(_currentEpisodeIndex + 1);
    }
  }

  void _onPrev() {
    if (_episodes.isNotEmpty && _currentEpisodeIndex > 0) {
      _playEpisode(_currentEpisodeIndex - 1);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PlayerLayout(
      title: _detailMap?['title'],
      episodes: _episodes,
      currentEpisodeIndex: _currentEpisodeIndex,
      onEpisodeSelected: (index) {
        _playEpisode(index);
      },
      onNext: _onNext,
      onPrev: _onPrev,
    );
  }
}

class _PlaybackReporter {
  final ApiClient _api = ApiClient();
  final WidgetRef ref;
  final int fileId;
  final Map<String, dynamic>? detail;
  final Duration interval = const Duration(seconds: 10);

  Timer? _timer;
  bool _isDisposed = false;

  _PlaybackReporter({
    required this.ref,
    required this.fileId,
    this.detail,
  });

  void start() {
    if (_isDisposed) return;
    _report('playing');
    _timer = Timer.periodic(interval, (_) {
      if (!_isDisposed) _report('playing');
    });
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    if (!_isDisposed) {
      _report('stopped');
      _isDisposed = true;
    }
  }

  Future<void> _report(String status) async {
    try {
      final state = ref.read(playerProvider);
      final pos = state.position;
      final dur = state.duration;

      String? mediaType;
      int? coreId;

      if (detail != null) {
        mediaType =
            (detail!['media_type'] as String?) ?? (detail!['kind'] as String?);
        coreId = detail!['id'] as int?;
      }

      await _api.reportPlaybackProgress(
        fileId: fileId,
        coreId: coreId,
        positionMs: pos.inMilliseconds,
        durationMs: dur.inMilliseconds,
        status: status,
        platform: 'web',
        mediaType: mediaType,
      );
    } catch (_) {}
  }
}
