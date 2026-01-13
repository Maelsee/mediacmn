import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';
import '../../../../../core/state/playback_state.dart';

class SettingsPanel extends StatelessWidget {
  final PlaybackSettings settings;
  final ValueChanged<PlaybackSettings> onSettingsChanged;
  final BoxFit fit;
  final ValueChanged<BoxFit> onFitChanged;
  final PlaylistMode playlistMode;
  final ValueChanged<PlaylistMode> onPlaylistModeChanged;

  /// 当前画面缩放倍数（用于“画面大小”快捷设置）。
  final double videoScale;

  /// 更新画面缩放倍数回调（建议同步重置 offset）。
  final ValueChanged<double> onVideoScaleChanged;

  const SettingsPanel({
    super.key,
    required this.settings,
    required this.onSettingsChanged,
    required this.fit,
    required this.onFitChanged,
    required this.playlistMode,
    required this.onPlaylistModeChanged,
    required this.videoScale,
    required this.onVideoScaleChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      // 移除固定宽度，由父组件控制
      color: const Color(0xFF1E1E1E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(16.0),
            child: Text(
              '播放设置',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          Expanded(
            child: ListView(
              children: [
                _buildListTile(
                  title: '设置片头片尾',
                  trailing: const Icon(Icons.arrow_forward_ios,
                      size: 16, color: Colors.white70),
                  onTap: () {
                    // TODO: Implement Intro/Outro settings dialog
                  },
                ),
                _buildSectionHeader('播放方式'),
                _buildSegmentedControl(
                  options: ['连续播放', '单集循环', '不循环'],
                  selectedIndex: _getPlaylistModeIndex(),
                  onSelected: (index) {
                    final modes = [
                      PlaylistMode.loop,
                      PlaylistMode.single,
                      PlaylistMode.none
                    ];
                    if (index >= 0 && index < modes.length) {
                      onPlaylistModeChanged(modes[index]);
                    }
                  },
                ),
                _buildSectionHeader('画面比例'),
                _buildSegmentedControl(
                  options: ['自适应', '铺满屏幕', '裁切'],
                  selectedIndex: _getFitIndex(),
                  onSelected: (index) {
                    final fits = [BoxFit.contain, BoxFit.fill, BoxFit.cover];
                    if (index >= 0 && index < fits.length) {
                      onFitChanged(fits[index]);
                    }
                  },
                ),
                _buildSectionHeader('画面大小'),
                _buildSegmentedControl(
                  options: ['50%', '75%', '100%', '125%'],
                  selectedIndex: _getVideoScaleIndex(),
                  onSelected: (index) {
                    final scales = [0.5, 0.75, 1.0, 1.25];
                    if (index >= 0 && index < scales.length) {
                      onVideoScaleChanged(scales[index]);
                    }
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  int _getPlaylistModeIndex() {
    switch (playlistMode) {
      case PlaylistMode.loop:
        return 0;
      case PlaylistMode.single:
        return 1;
      case PlaylistMode.none:
        return 2;
    }
  }

  int _getFitIndex() {
    switch (fit) {
      case BoxFit.contain:
        return 0;
      case BoxFit.fill:
        return 1;
      case BoxFit.cover:
        return 2;
      default:
        return 0;
    }
  }

  int _getVideoScaleIndex() {
    final candidates = [0.5, 0.75, 1.0, 1.25];

    var bestIndex = 2;
    var bestDistance = double.infinity;
    for (var i = 0; i < candidates.length; i++) {
      final d = (videoScale - candidates[i]).abs();
      if (d < bestDistance) {
        bestDistance = d;
        bestIndex = i;
      }
    }
    return bestIndex;
  }

  Widget _buildListTile(
      {required String title,
      required Widget trailing,
      required VoidCallback onTap}) {
    return ListTile(
      title: Text(title, style: const TextStyle(color: Colors.white)),
      trailing: trailing,
      onTap: onTap,
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Text(
        title,
        style: const TextStyle(color: Colors.white70, fontSize: 14),
      ),
    );
  }

  Widget _buildSegmentedControl({
    required List<String> options,
    required int selectedIndex,
    required ValueChanged<int> onSelected,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0),
      child: Row(
        children: List.generate(options.length, (index) {
          final isSelected = index == selectedIndex;
          return Expanded(
            child: GestureDetector(
              onTap: () => onSelected(index),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      color: isSelected
                          ? const Color(0xFFFFD700)
                          : Colors.transparent,
                      width: 2,
                    ),
                  ),
                ),
                alignment: Alignment.center,
                child: Text(
                  options[index],
                  style: TextStyle(
                    color:
                        isSelected ? const Color(0xFFFFD700) : Colors.white70,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}
