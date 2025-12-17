import 'package:flutter/material.dart';
import 'dart:async';
import 'package:flutter/services.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'player_core.dart';

class PlayerView extends StatefulWidget {
  final PlayerCore core;
  final String? title;
  const PlayerView({super.key, required this.core, this.title});

  @override
  State<PlayerView> createState() => _PlayerViewState();
}

class _PlayerViewState extends State<PlayerView> {
  bool _showControls = true;
  double _rate = 1.0;
  bool _locked = false;
  bool _muted = false;
  double _volume = 1.0; // 0.0 ~ 1.0
  double _lastVolume = 1.0;
  Timer? _hideTimer;
  String _qualityLabel = '原画';
  String _scaleLabel = '原画';
  AudioTrack? _currentAudio;
  SubtitleTrack? _currentSubtitle;
  bool _fullscreen = false;
  BoxFit _fit = BoxFit.contain;
  // Live state from player streams
  List<AudioTrack> _audioTracks = const [];
  List<SubtitleTrack> _subtitleTracks = const [];
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  bool _playing = false;
  bool _buffering = false; // reserved for buffering indicator (future use)
  StreamSubscription<Duration>? _posSub;
  StreamSubscription<Duration>? _durSub;
  StreamSubscription<bool>? _playSub;
  StreamSubscription<bool>? _bufSub;
  StreamSubscription<Tracks>? _tracksSub;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    // Subscribe to player streams for snappy UI updates
    final p = widget.core.player;
    _position = p.state.position;
    _duration = p.state.duration;
    _playing = p.state.playing;
    _buffering = p.state.buffering;
    _audioTracks = p.state.tracks.audio;
    _subtitleTracks = p.state.tracks.subtitle;
    _posSub = p.stream.position.listen((d) {
      if (!mounted) return;
      setState(() => _position = d);
    });
    _durSub = p.stream.duration.listen((d) {
      if (!mounted) return;
      setState(() => _duration = d);
    });
    _playSub = p.stream.playing.listen((v) {
      if (!mounted) return;
      setState(() => _playing = v);
    });
    _bufSub = p.stream.buffering.listen((v) {
      if (!mounted) return;
      setState(() => _buffering = v);
    });
    _tracksSub = p.stream.tracks.listen((t) {
      if (!mounted) return;
      setState(() {
        _audioTracks = t.audio;
        _subtitleTracks = t.subtitle;
      });
    });
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    _posSub?.cancel();
    _durSub?.cancel();
    _playSub?.cancel();
    _bufSub?.cancel();
    _tracksSub?.cancel();
    WakelockPlus.disable();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.portraitDown,
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    super.dispose();
  }

  void _togglePlay() {
    widget.core.toggle();
    _scheduleAutoHide();
  }

  void _seekRelative(Duration delta) {
    final pos = _position;
    final next = pos + delta;
    widget.core.seek(next);
    setState(() => _position = next);
    _scheduleAutoHide();
  }

  void _scheduleAutoHide() {
    _hideTimer?.cancel();
    _hideTimer = Timer(const Duration(seconds: 4), () {
      if (!mounted) return;
      setState(() => _showControls = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return GestureDetector(
          onTap: () {
            setState(() => _showControls = true);
            _scheduleAutoHide();
          },
          onDoubleTapDown: (d) {
            final x = d.localPosition.dx;
            final w = constraints.maxWidth;
            if (x < w / 2) {
              _seekRelative(const Duration(seconds: -10));
            } else {
              _seekRelative(const Duration(seconds: 10));
            }
          },
          child: Stack(
            children: [
              Positioned.fill(
                child: FittedBox(
                  fit: _fit,
                  clipBehavior: Clip.hardEdge,
                  child: SizedBox(
                    width: constraints.maxWidth,
                    height: constraints.maxHeight,
                    child: Video(
                      controller: widget.core.controller,
                      controls: (state) => const SizedBox.shrink(),
                    ),
                  ),
                ),
              ),
              if (_buffering)
                const Center(
                  child: SizedBox(
                    width: 42,
                    height: 42,
                    child: CircularProgressIndicator(strokeWidth: 3),
                  ),
                ),
              AnimatedOpacity(
                opacity: _showControls ? 1.0 : 0.0,
                duration: const Duration(milliseconds: 200),
                child: IgnorePointer(
                  ignoring: !_showControls,
                  child: _buildControls(context),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildControls(BuildContext context) {
    final pos = _position;
    final dur = _duration;
    final playing = _playing;
    return Positioned.fill(
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 顶部栏：返回与标题
              Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.arrow_back, color: Colors.white),
                    onPressed: () => Navigator.maybePop(context),
                  ),
                  Expanded(
                    child: Text(
                      widget.title ?? '',
                      style: const TextStyle(color: Colors.white),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.settings, color: Colors.white),
                    onPressed: () {},
                  ),
                ],
              ),
              const Spacer(),
              // 中部：居中播放按钮
              Center(
                child: IconButton(
                  iconSize: 44,
                  icon: Icon(
                    playing
                        ? Icons.pause_circle_filled
                        : Icons.play_circle_fill,
                    color: Colors.white,
                  ),
                  onPressed: _togglePlay,
                ),
              ),
              const Spacer(),
              // 底部控制条：进度、倍速、清晰度、缩放、锁、音量、字幕
              Column(
                children: [
                  Row(
                    children: [
                      Text(
                        _fmt(pos),
                        style: const TextStyle(color: Colors.white),
                      ),
                      Expanded(
                        child: Slider(
                          value: (dur.inMilliseconds > 0
                              ? pos.inMilliseconds
                                  .clamp(0, dur.inMilliseconds)
                                  .toDouble()
                              : 0.0),
                          min: 0,
                          max: dur.inMilliseconds > 0
                              ? dur.inMilliseconds.toDouble()
                              : 1.0,
                          onChanged: (v) {
                            if (_duration.inMilliseconds > 0) {
                              final d = Duration(milliseconds: v.toInt());
                              setState(() => _position = d);
                              widget.core.seek(d);
                            }
                            setState(() => _showControls = true);
                            _scheduleAutoHide();
                          },
                        ),
                      ),
                      Text(
                        _fmt(dur),
                        style: const TextStyle(color: Colors.white),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      // 倍速
                      PopupMenuButton<double>(
                        tooltip: '倍速',
                        initialValue: _rate,
                        onSelected: (r) {
                          setState(() => _rate = r);
                          widget.core.setRate(r);
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(value: 0.5, child: Text('0.5x')),
                          PopupMenuItem(value: 0.75, child: Text('0.75x')),
                          PopupMenuItem(value: 1.0, child: Text('1.0x')),
                          PopupMenuItem(value: 1.25, child: Text('1.25x')),
                          PopupMenuItem(value: 1.5, child: Text('1.5x')),
                          PopupMenuItem(value: 2.0, child: Text('2.0x')),
                        ],
                        child: _label('倍速', '${(_rate).toStringAsFixed(2)}x'),
                      ),
                      const SizedBox(width: 12),
                      // 清晰度（HLS 变体占位：后续根据 variants 列举）
                      PopupMenuButton<String>(
                        tooltip: '清晰度',
                        initialValue: _qualityLabel,
                        onSelected: (q) {
                          setState(() => _qualityLabel = q);
                          _scheduleAutoHide();
                        },
                        itemBuilder: (_) => [
                          const PopupMenuItem(value: '原画', child: Text('原画')),
                          const PopupMenuItem(
                              value: '1080p', child: Text('1080p')),
                          const PopupMenuItem(
                              value: '720p', child: Text('720p')),
                        ],
                        child: _label('原画', _qualityLabel),
                      ),
                      const SizedBox(width: 12),
                      // 缩放模式
                      PopupMenuButton<String>(
                        tooltip: '缩放',
                        initialValue: _scaleLabel,
                        onSelected: (s) {
                          setState(() => _scaleLabel = s);
                          switch (s) {
                            case '原画':
                            case '等比':
                              _fit = BoxFit.contain;
                              break;
                            case '充满':
                            case '裁剪':
                              _fit = BoxFit.cover;
                              break;
                          }
                          _scheduleAutoHide();
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(value: '原画', child: Text('原画')),
                          PopupMenuItem(value: '等比', child: Text('等比')),
                          PopupMenuItem(value: '裁剪', child: Text('裁剪')),
                          PopupMenuItem(value: '充满', child: Text('充满')),
                        ],
                        child: _label('缩放', _scaleLabel),
                      ),
                      const Spacer(),
                      // 锁屏
                      IconButton(
                        icon: Icon(_locked ? Icons.lock : Icons.lock_open,
                            color: Colors.white),
                        onPressed: () {
                          setState(() => _locked = !_locked);
                          if (_locked) {
                            SystemChrome.setPreferredOrientations(const [
                              DeviceOrientation.landscapeLeft,
                              DeviceOrientation.landscapeRight,
                            ]);
                          } else {
                            SystemChrome.setPreferredOrientations(const [
                              DeviceOrientation.portraitUp,
                              DeviceOrientation.portraitDown,
                              DeviceOrientation.landscapeLeft,
                              DeviceOrientation.landscapeRight,
                            ]);
                          }
                          _scheduleAutoHide();
                        },
                      ),
                      IconButton(
                        icon: Icon(_muted ? Icons.volume_off : Icons.volume_up,
                            color: Colors.white),
                        onPressed: () {
                          setState(() {
                            _muted = !_muted;
                            if (_muted) {
                              _lastVolume =
                                  _volume > 0.0 ? _volume : _lastVolume;
                              _volume = 0.0;
                            } else {
                              _volume = _lastVolume <= 0.0 ? 1.0 : _lastVolume;
                            }
                          });
                          widget.core.setVolume(_volume);
                          _scheduleAutoHide();
                        },
                      ),
                      // 音量滑块
                      SizedBox(
                        width: 120,
                        child: Slider(
                          value: _volume,
                          min: 0.0,
                          max: 1.0,
                          onChanged: (v) {
                            setState(() {
                              _volume = v;
                              _muted = v <= 0.0;
                            });
                            widget.core.setVolume(_volume);
                            _scheduleAutoHide();
                          },
                        ),
                      ),
                      IconButton(
                        icon: Icon(
                            _fullscreen
                                ? Icons.fullscreen_exit
                                : Icons.fullscreen,
                            color: Colors.white),
                        onPressed: () {
                          setState(() => _fullscreen = !_fullscreen);
                          if (_fullscreen) {
                            SystemChrome.setEnabledSystemUIMode(
                                SystemUiMode.immersiveSticky);
                            SystemChrome.setPreferredOrientations(const [
                              DeviceOrientation.landscapeLeft,
                              DeviceOrientation.landscapeRight,
                            ]);
                          } else {
                            SystemChrome.setEnabledSystemUIMode(
                                SystemUiMode.edgeToEdge);
                            SystemChrome.setPreferredOrientations(const [
                              DeviceOrientation.portraitUp,
                              DeviceOrientation.portraitDown,
                              DeviceOrientation.landscapeLeft,
                              DeviceOrientation.landscapeRight,
                            ]);
                          }
                          _scheduleAutoHide();
                        },
                      ),
                      // 字幕选择
                      PopupMenuButton<SubtitleTrack?>(
                        tooltip: '字幕',
                        initialValue: _currentSubtitle,
                        onSelected: (t) {
                          setState(() => _currentSubtitle = t);
                          if (t == null) {
                            widget.core.setSubtitleNone();
                          } else {
                            widget.core.setSubtitleTrack(t);
                          }
                          _scheduleAutoHide();
                        },
                        itemBuilder: (_) {
                          if (_subtitleTracks.isEmpty) {
                            return [
                              const PopupMenuItem<SubtitleTrack?>(
                                  value: null, child: Text('无字幕'))
                            ];
                          }
                          return [
                            const PopupMenuItem<SubtitleTrack?>(
                                value: null, child: Text('无字幕')),
                            ..._subtitleTracks.map((t) =>
                                PopupMenuItem<SubtitleTrack?>(
                                    value: t,
                                    child:
                                        Text(t.language ?? t.title ?? '字幕'))),
                          ];
                        },
                        child: const Icon(Icons.subtitles, color: Colors.white),
                      ),
                      // 音轨选择
                      PopupMenuButton<AudioTrack?>(
                        tooltip: '音轨',
                        initialValue: _currentAudio,
                        onSelected: (t) {
                          setState(() => _currentAudio = t);
                          if (t == null) {
                            widget.core.setAudioNone();
                          } else {
                            widget.core.setAudioTrack(t);
                          }
                          _scheduleAutoHide();
                        },
                        itemBuilder: (_) {
                          if (_audioTracks.isEmpty) {
                            return [
                              const PopupMenuItem<AudioTrack?>(
                                  value: null, child: Text('默认音轨'))
                            ];
                          }
                          return [
                            const PopupMenuItem<AudioTrack?>(
                                value: null, child: Text('默认音轨')),
                            ..._audioTracks.map((t) =>
                                PopupMenuItem<AudioTrack?>(
                                    value: t,
                                    child:
                                        Text(t.language ?? t.title ?? '音轨'))),
                          ];
                        },
                        child:
                            const Icon(Icons.audiotrack, color: Colors.white),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _label(String title, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.white.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, style: const TextStyle(color: Colors.white)),
          const SizedBox(width: 6),
          Text(value, style: const TextStyle(color: Colors.white)),
        ],
      ),
    );
  }

  String _fmt(Duration d) {
    if (d.inMilliseconds <= 0) return '00:00';
    final h = d.inHours;
    final m = d.inMinutes % 60;
    final s = d.inSeconds % 60;
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }
}
