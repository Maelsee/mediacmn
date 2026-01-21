import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';

/// 移动端字幕面板。
///
/// 字幕数据来自播放器的 `tracksStream`。
class SubtitlePanel extends StatefulWidget {
  final bool showSubtitles;
  final ValueChanged<bool> onToggleShowSubtitles;
  final List<SubtitleTrack> subtitles;
  final SubtitleTrack selectedSubtitle;
  final ValueChanged<SubtitleTrack> onSubtitleSelected;
  final double fontSize;
  final double bottomPadding;
  final ValueChanged<double> onFontSizeChanged;
  final ValueChanged<double> onBottomPaddingChanged;

  const SubtitlePanel({
    super.key,
    required this.showSubtitles,
    required this.onToggleShowSubtitles,
    required this.subtitles,
    required this.selectedSubtitle,
    required this.onSubtitleSelected,
    required this.fontSize,
    required this.bottomPadding,
    required this.onFontSizeChanged,
    required this.onBottomPaddingChanged,
  });

  @override
  State<SubtitlePanel> createState() => _SubtitlePanelState();
}

class _SubtitlePanelState extends State<SubtitlePanel> {
  final ScrollController _scrollController = ScrollController();
  late List<SubtitleTrack> _visibleSubtitles;

  bool _showSettings = false;

  @override
  void didUpdateWidget(SubtitlePanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.subtitles != oldWidget.subtitles) {
      _visibleSubtitles = widget.subtitles
          .where((track) => track.id != 'no')
          .toList(growable: false);
    }
  }

  @override
  void initState() {
    super.initState();
    _visibleSubtitles = widget.subtitles
        .where((track) => track.id != 'no')
        .toList(growable: false);

    // 初始滚动到选中项
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.showSubtitles) {
        final index = _visibleSubtitles.indexWhere(
          (t) => t.id == widget.selectedSubtitle.id,
        );
        if (index != -1 && _scrollController.hasClients) {
          const itemHeight = 56.0;
          final offset = index * itemHeight;
          final maxScroll = _scrollController.position.maxScrollExtent;
          _scrollController.jumpTo(offset > maxScroll ? maxScroll : offset);
        }
      }
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _buildHeader(),
        Expanded(
          child: _showSettings ? _buildStyleSettings() : _buildTrackSelection(),
        ),
      ],
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          const Text(
            '显示字幕',
            style: TextStyle(color: Colors.white, fontSize: 16),
          ),
          const SizedBox(width: 12),
          Switch(
            value: widget.showSubtitles,
            onChanged: widget.onToggleShowSubtitles,
            activeTrackColor: const Color(0xFFFFE796),
            thumbColor: WidgetStateProperty.resolveWith<Color>((states) {
              if (states.contains(WidgetState.selected)) {
                return Colors.white;
              }
              return Colors.white;
            }),
          ),
          const Spacer(),
          GestureDetector(
            onTap: () {
              setState(() {
                _showSettings = !_showSettings;
              });
            },
            behavior: HitTestBehavior.opaque,
            child: Row(
              children: [
                Icon(
                  Icons.settings,
                  size: 18,
                  color:
                      _showSettings ? const Color(0xFFFFE796) : Colors.white70,
                ),
                const SizedBox(width: 4),
                Text(
                  '字幕设置',
                  style: TextStyle(
                    color: _showSettings
                        ? const Color(0xFFFFE796)
                        : Colors.white70,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTrackSelection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.showSubtitles) ...[
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Text(
              '内嵌字幕',
              style: TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ),
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: _visibleSubtitles.length,
              itemBuilder: (context, index) {
                return _buildSubtitleOption(_visibleSubtitles[index]);
              },
            ),
          ),
        ],
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: Row(
            children: [
              const Text(
                '外挂字幕',
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
              const Spacer(),
              const Icon(Icons.input, size: 16, color: Colors.white70),
              const SizedBox(width: 4),
              GestureDetector(
                onTap: () {
                  // TODO: Import subtitle
                },
                child: const Text(
                  '导入',
                  style: TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildStyleSettings() {
    if (!widget.showSubtitles) {
      return const Center(
        child: Text(
          '请先开启字幕显示',
          style: TextStyle(color: Colors.white54),
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16.0),
      children: [
        _buildSlider(
          label: '字号大小',
          value: widget.fontSize,
          min: 20.0,
          max: 80.0,
          onChanged: widget.onFontSizeChanged,
          displayFormat: (v) => v.toInt().toString(),
        ),
        const SizedBox(height: 16),
        _buildSlider(
          label: '垂直位置',
          value: widget.bottomPadding,
          min: 0.0,
          max: 200.0,
          onChanged: widget.onBottomPaddingChanged,
          displayFormat: (v) => v.toInt().toString(),
        ),
      ],
    );
  }

  Widget _buildSlider({
    required String label,
    required double value,
    required double min,
    required double max,
    required ValueChanged<double> onChanged,
    required String Function(double) displayFormat,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF666666).withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                label,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
              Text(
                displayFormat(value),
                style: const TextStyle(color: Colors.white70, fontSize: 14),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SliderTheme(
            data: SliderThemeData(
              activeTrackColor: const Color(0xFFFFE796),
              inactiveTrackColor: Colors.white24,
              thumbColor: Colors.white,
              overlayColor: const Color(0xFFFFE796).withValues(alpha: 0.2),
              trackHeight: 4.0,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 8.0),
            ),
            child: Slider(
              value: value,
              min: min,
              max: max,
              onChanged: onChanged,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSubtitleOption(SubtitleTrack track) {
    final isSelected = track.id == widget.selectedSubtitle.id;
    return GestureDetector(
      onTap: () => widget.onSubtitleSelected(track),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        decoration: BoxDecoration(
          color: isSelected
              ? const Color(0xFF666666).withValues(alpha: 0.3)
              : const Color(0xFF666666).withValues(alpha: 0.3),
          borderRadius: BorderRadius.circular(8),
          border: isSelected
              ? Border.all(
                  color: const Color(0xFFFFE796).withValues(alpha: 0.5),
                  width: 1)
              : null,
        ),
        alignment: Alignment.center,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            // Center text trick: Spacer + Text + Spacer
            const Spacer(),
            Text(
              _getTrackName(track),
              style: TextStyle(
                color: isSelected ? const Color(0xFFFFE796) : Colors.white70,
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w500 : FontWeight.normal,
              ),
            ),
            const Spacer(),
            if (isSelected)
              const Icon(Icons.check, size: 16, color: Color(0xFFFFE796)),
          ],
        ),
      ),
    );
  }

  String _getTrackName(SubtitleTrack track) {
    if (track.id == 'auto') return '自动';
    if (track.title != null && track.title!.isNotEmpty) {
      return track.title!;
    }
    if (track.language != null && track.language!.isNotEmpty) {
      const map = {
        'chi': '中文',
        'zho': '中文',
        'eng': 'English',
        'jpn': '日本語',
        'kor': '한국어',
        'fre': 'Français',
        'ger': 'Deutsch',
        'spa': 'Español',
        'ita': 'Italiano',
        'rus': 'Русский',
      };
      return map[track.language!] ?? track.language!;
    }
    return track.id;
  }
}
