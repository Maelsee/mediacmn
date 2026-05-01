import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../../../../../../media_player/core/state/playback_state.dart';
import '../../../../../utils/player_utils.dart';

/// 片头片尾设置面板。
class IntroOutroSettingsPanel extends StatefulWidget {
  final PlaybackSettings settings;
  final ValueChanged<PlaybackSettings> onChanged;
  final VoidCallback? onSave;

  const IntroOutroSettingsPanel({
    super.key,
    required this.settings,
    required this.onChanged,
    this.onSave,
  });

  @override
  State<IntroOutroSettingsPanel> createState() =>
      _IntroOutroSettingsPanelState();
}

class _IntroOutroSettingsPanelState extends State<IntroOutroSettingsPanel> {
  late PlaybackSettings _s;

  @override
  void initState() {
    super.initState();
    _s = widget.settings;
  }

  @override
  void didUpdateWidget(covariant IntroOutroSettingsPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.settings != oldWidget.settings) {
      _s = widget.settings;
    }
  }

  void _updateSettings(PlaybackSettings newSettings) {
    setState(() {
      _s = newSettings;
    });
    // 实时通知父组件更新状态（但不一定立即持久化，点击保存时才持久化）
    // 但根据需求，这里应该是编辑态，最后点保存才生效？
    // 或者设计为实时生效？参考截图有“保存设置”按钮，说明是确认式。
    // 这里暂不调用 widget.onChanged，等到点击保存时再统一调用。
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF1E1E1E),
      child: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16.0, vertical: 24.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '播放设置',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _buildSwitchTile(
                    title: '自动跳过电视剧片头片尾',
                    subtitle: '开启后，所有电视剧均将自动跳过片头片尾',
                    value: _s.skipIntroOutro,
                    onChanged: (v) =>
                        _updateSettings(_s.copyWith(skipIntroOutro: v)),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    '当前视频片头片尾设置',
                    style: TextStyle(color: Colors.white54, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    decoration: BoxDecoration(
                      color: const Color(0xFF2C2C2C), // 深灰色背景
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        _buildTimeTile(
                          label: '片头时间',
                          time: _s.introTime,
                          onTap: () => _showTimePicker(
                            context,
                            '片头时间',
                            _s.introTime,
                            (d) => _updateSettings(_s.copyWith(introTime: d)),
                          ),
                        ),
                        const Divider(height: 1, color: Colors.black12),
                        _buildTimeTile(
                          label: '片尾时间',
                          time: _s.outroTime,
                          onTap: () => _showTimePicker(
                            context,
                            '片尾时间',
                            _s.outroTime,
                            (d) => _updateSettings(_s.copyWith(outroTime: d)),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  GestureDetector(
                    onTap: () {
                      _updateSettings(
                        _s.copyWith(applyToAllEpisodes: !_s.applyToAllEpisodes),
                      );
                    },
                    behavior: HitTestBehavior.opaque,
                    child: Row(
                      children: [
                        Icon(
                          _s.applyToAllEpisodes
                              ? Icons.check_box
                              : Icons.check_box_outline_blank,
                          color: _s.applyToAllEpisodes
                              ? Colors.blue
                              : Colors.white70,
                          size: 20,
                        ),
                        const SizedBox(width: 8),
                        const Text(
                          '同步应用到电视剧当前季的所有剧集',
                          style: TextStyle(color: Colors.white70, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 32),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton(
                      onPressed: () {
                        widget.onChanged(_s);
                        widget.onSave?.call();
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF333333),
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: const Text('保存设置', style: TextStyle(fontSize: 15)),
                    ),
                  ),
                  SizedBox(height: 16 + MediaQuery.of(context).padding.bottom),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSwitchTile({
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF2C2C2C),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(color: Colors.white, fontSize: 15),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ],
            ),
          ),
          Switch.adaptive(
            value: value,
            onChanged: onChanged,
            activeTrackColor: Colors.blue,
            inactiveTrackColor: Colors.grey.withValues(alpha: 0.3),
          ),
        ],
      ),
    );
  }

  Widget _buildTimeTile({
    required String label,
    required Duration time,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: const TextStyle(color: Colors.white, fontSize: 16),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                formatDuration(time),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }


  void _showTimePicker(
    BuildContext context,
    String title,
    Duration initial,
    ValueChanged<Duration> onConfirm,
  ) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF2C2C2C),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return _TimePickerSheet(
          title: title,
          initialDuration: initial,
          onConfirm: onConfirm,
        );
      },
    );
  }
}

class _TimePickerSheet extends StatefulWidget {
  final String title;
  final Duration initialDuration;
  final ValueChanged<Duration> onConfirm;

  const _TimePickerSheet({
    required this.title,
    required this.initialDuration,
    required this.onConfirm,
  });

  @override
  State<_TimePickerSheet> createState() => _TimePickerSheetState();
}

class _TimePickerSheetState extends State<_TimePickerSheet> {
  late Duration _current;

  @override
  void initState() {
    super.initState();
    _current = widget.initialDuration;
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 300,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  widget.title,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
                GestureDetector(
                  onTap: () {
                    widget.onConfirm(_current);
                    Navigator.of(context).pop();
                  },
                  child: const Text(
                    '确定',
                    style: TextStyle(color: Colors.blue, fontSize: 16),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: CupertinoTheme(
              data: const CupertinoThemeData(
                brightness: Brightness.dark,
                textTheme: CupertinoTextThemeData(
                  dateTimePickerTextStyle: TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                  ),
                ),
              ),
              child: CupertinoTimerPicker(
                mode: CupertinoTimerPickerMode.hms,
                initialTimerDuration: _current,
                onTimerDurationChanged: (d) => _current = d,
                backgroundColor: Colors.transparent,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
