import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';
import '../../../../../core/state/playback_state.dart';
import 'intro_outro_settings_panel.dart';

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
                  trailing: const Icon(
                    Icons.arrow_forward_ios,
                    size: 16,
                    color: Colors.white70,
                  ),
                  onTap: () {
                    // 打开片头片尾设置面板
                    final isLandscape = MediaQuery.of(context).orientation ==
                        Orientation.landscape;

                    if (isLandscape) {
                      // 横屏时：在侧边栏内推入新页面（不全屏，保留侧边栏宽度）
                      // 由于 SettingsPanel 本身是在 Drawer/EndDrawer 或 SidePanel 中，
                      // 直接 Navigator.push 会覆盖整个屏幕（如果 Context 是根路由的）。
                      // 但这里需要在当前侧边栏容器内切换内容。
                      // 简单方案：使用 Navigator 嵌套或简单的状态切换。
                      // 考虑到代码结构，这里我们使用 Navigator.push，但配合自定义 Route
                      // 或者更简单的：弹出一个新的 Right Side Dialog。
                      // 修正：直接使用 showGeneralDialog 弹出一个覆盖在右侧的面板，
                      // 类似于多级菜单，宽度与 SettingsPanel 一致。
                      showGeneralDialog(
                        context: context,
                        barrierDismissible: true,
                        barrierLabel: 'Dismiss',
                        pageBuilder: (ctx, anim1, anim2) {
                          return Align(
                            alignment: Alignment.centerRight,
                            child: Material(
                              color: const Color(0xFF1E1E1E),
                              child: SizedBox(
                                width: 300, // 与侧边栏宽度一致
                                height: double.infinity,
                                child: Scaffold(
                                  backgroundColor: Colors.transparent,
                                  appBar: AppBar(
                                    backgroundColor: Colors.transparent,
                                    elevation: 0,
                                    leading: IconButton(
                                      icon: const Icon(Icons.arrow_back,
                                          color: Colors.white),
                                      onPressed: () => Navigator.of(ctx).pop(),
                                    ),
                                    title: const Text(
                                      '片头片尾设置',
                                      style: TextStyle(
                                          color: Colors.white, fontSize: 16),
                                    ),
                                  ),
                                  body: IntroOutroSettingsPanel(
                                    settings: settings,
                                    onChanged: onSettingsChanged,
                                    onSave: () => Navigator.of(ctx).pop(),
                                  ),
                                ),
                              ),
                            ),
                          );
                        },
                        transitionBuilder: (ctx, anim1, anim2, child) {
                          return SlideTransition(
                            position: Tween(
                              begin: const Offset(1, 0),
                              end: Offset.zero,
                            ).animate(anim1),
                            child: child,
                          );
                        },
                      );
                    } else {
                      // 竖屏时弹出底部抽屉
                      showModalBottomSheet(
                        context: context,
                        backgroundColor: const Color(0xFF1E1E1E),
                        isScrollControlled: true,
                        shape: const RoundedRectangleBorder(
                          borderRadius:
                              BorderRadius.vertical(top: Radius.circular(16)),
                        ),
                        builder: (ctx) => SizedBox(
                          height: MediaQuery.of(context).size.height * 0.6,
                          child: Column(
                            children: [
                              AppBar(
                                backgroundColor: Colors.transparent,
                                elevation: 0,
                                title: const Text(
                                  '片头片尾设置',
                                  style: TextStyle(color: Colors.white),
                                ),
                                automaticallyImplyLeading: false,
                                actions: [
                                  IconButton(
                                    icon: const Icon(Icons.close,
                                        color: Colors.white),
                                    onPressed: () => Navigator.of(ctx).pop(),
                                  ),
                                ],
                              ),
                              Expanded(
                                child: IntroOutroSettingsPanel(
                                  settings: settings,
                                  onChanged: onSettingsChanged,
                                  onSave: () => Navigator.of(ctx).pop(),
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    }
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
                      PlaylistMode.none,
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

  Widget _buildListTile({
    required String title,
    required Widget trailing,
    required VoidCallback onTap,
  }) {
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
