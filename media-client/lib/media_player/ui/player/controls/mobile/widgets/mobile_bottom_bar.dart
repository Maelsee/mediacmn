import 'package:flutter/material.dart';

class MobileBottomBar extends StatefulWidget {
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final Duration buffered;
  final VoidCallback onPlayPause;
  final ValueChanged<Duration> onSeek;
  final VoidCallback onEpisodes;
  final VoidCallback onSpeed;
  final VoidCallback onQuality;
  final VoidCallback onSubtitles;
  final VoidCallback onAudios;
  final VoidCallback onDanmu;
  final String speedText;
  final String qualityText;

  const MobileBottomBar({
    super.key,
    required this.isPlaying,
    required this.position,
    required this.duration,
    required this.buffered,
    required this.onPlayPause,
    required this.onSeek,
    required this.onEpisodes,
    required this.onSpeed,
    required this.onQuality,
    required this.onSubtitles,
    required this.onAudios,
    required this.onDanmu,
    required this.speedText,
    required this.qualityText,
  });

  @override
  State<MobileBottomBar> createState() => _MobileBottomBarState();
}

class _MobileBottomBarState extends State<MobileBottomBar> {
  /// 是否正在拖动进度条。
  bool _isDragging = false;

  /// 进度条拖动中的临时值（毫秒）。
  double _dragValue = 0.0;

  String _formatDuration(Duration duration) {
    String twoDigits(int n) => n.toString().padLeft(2, '0');
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    return hours > 0
        ? '$hours:${twoDigits(minutes)}:${twoDigits(seconds)}'
        : '${twoDigits(minutes)}:${twoDigits(seconds)}';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [Colors.black.withValues(alpha: 0.9), Colors.transparent],
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildProgressBar(context),
          const SizedBox(height: 8),
          Row(
            children: [
              IconButton(
                icon: Icon(
                  widget.isPlaying ? Icons.pause : Icons.play_arrow,
                  color: Colors.white,
                  size: 32,
                ),
                onPressed: widget.onPlayPause,
              ),
              const Spacer(),
              _buildTextButton('字幕', widget.onSubtitles),
              const SizedBox(width: 16),
              _buildTextButton('弹幕', widget.onDanmu),
              const SizedBox(width: 16),
              _buildTextButton('音轨', widget.onAudios),
              const SizedBox(width: 16),
              _buildTextButton('选集', widget.onEpisodes),
              const SizedBox(width: 16),
              _buildTextButton(
                widget.speedText,
                widget.onSpeed,
                subtitle: '倍速',
              ),
              const SizedBox(width: 16),
              _buildTextButton(
                widget.qualityText,
                widget.onQuality,
                subtitle: '画质',
                isHighlight: true,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildProgressBar(BuildContext context) {
    final max = widget.duration.inMilliseconds.toDouble();
    final value =
        _isDragging ? _dragValue : widget.position.inMilliseconds.toDouble();
    final displayTime = _isDragging
        ? Duration(milliseconds: _dragValue.toInt())
        : widget.position;

    return Row(
      children: [
        Text(
          _formatDuration(displayTime),
          style: const TextStyle(color: Colors.white, fontSize: 12),
        ),
        Expanded(
          child: SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: const Color(0xFFFFE796),
              inactiveTrackColor: Colors.white24,
              thumbColor: Colors.white,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
              trackHeight: 2,
              overlayShape: const RoundSliderOverlayShape(overlayRadius: 12),
            ),
            child: Slider(
              value: value.clamp(0.0, max),
              min: 0,
              max: max,
              onChangeStart: (v) {
                setState(() {
                  _isDragging = true;
                  _dragValue = v;
                });
              },
              onChanged: (v) {
                setState(() {
                  _dragValue = v;
                });
              },
              onChangeEnd: (v) {
                setState(() {
                  _isDragging = false;
                });
                widget.onSeek(Duration(milliseconds: v.toInt()));
              },
            ),
          ),
        ),
        Text(
          _formatDuration(widget.duration),
          style: const TextStyle(color: Colors.white, fontSize: 12),
        ),
      ],
    );
  }

  Widget _buildTextButton(
    String text,
    VoidCallback onTap, {
    String? subtitle,
    bool isHighlight = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            text,
            style: TextStyle(
              color: isHighlight ? const Color(0xFFFFE796) : Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(
              subtitle,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 10,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
