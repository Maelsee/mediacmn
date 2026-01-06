import 'package:flutter/material.dart';

class SpeedPanel extends StatelessWidget {
  final double currentSpeed;
  final ValueChanged<double> onSpeedChanged;

  const SpeedPanel({
    super.key,
    required this.currentSpeed,
    required this.onSpeedChanged,
  });

  static const List<double> speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];

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
              '倍速播放',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: speeds.length,
              itemBuilder: (context, index) {
                final speed = speeds[index];
                final isSelected = (speed - currentSpeed).abs() < 0.01;
                return ListTile(
                  title: Text(
                    '${speed}x',
                    style: TextStyle(
                      color:
                          isSelected ? const Color(0xFFFFD700) : Colors.white,
                      fontWeight:
                          isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                  trailing: isSelected
                      ? const Icon(Icons.check, color: Color(0xFFFFD700))
                      : null,
                  onTap: () => onSpeedChanged(speed),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
