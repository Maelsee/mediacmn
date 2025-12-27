import 'package:flutter/material.dart';
import '../components/side_panel.dart';

class SettingsPanel extends StatelessWidget {
  final bool autoSkip;
  final bool enableHardwareAcceleration;
  final ValueChanged<bool> onAutoSkipChanged;
  final ValueChanged<bool> onHardwareAccelerationChanged;
  final VoidCallback onClose;

  const SettingsPanel({
    super.key,
    required this.autoSkip,
    required this.enableHardwareAcceleration,
    required this.onAutoSkipChanged,
    required this.onHardwareAccelerationChanged,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return SidePanel(
      title: '播放设置',
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 自动跳过开关
          _buildSwitchTile(
            title: '自动跳过电视剧片头片尾',
            subtitle: '开启后，所有电视剧均将自动跳过片头片尾',
            value: autoSkip,
            onChanged: onAutoSkipChanged,
          ),

          const SizedBox(height: 12),

          // 硬件加速开关
          _buildSwitchTile(
            title: '启用硬件加速',
            subtitle: '解决部分模拟器无画面问题，切换后可能需要重新播放',
            value: enableHardwareAcceleration,
            onChanged: onHardwareAccelerationChanged,
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
      decoration: BoxDecoration(
        color: Colors.white10,
        borderRadius: BorderRadius.circular(8),
      ),
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(color: Colors.white, fontSize: 16)),
                const SizedBox(height: 4),
                Text(subtitle,
                    style:
                        const TextStyle(color: Colors.white54, fontSize: 12)),
              ],
            ),
          ),
          Switch(
            value: value,
            onChanged: onChanged,
            activeThumbColor: Colors.blue,
          ),
        ],
      ),
    );
  }
}
