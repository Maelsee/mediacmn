import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../../core/state/playback_state.dart';

class SpeedPanel extends ConsumerWidget {
  final double currentSpeed;
  final ValueChanged<double> onSpeedChanged;

  /// 是否在选择倍速后自动关闭面板。
  final bool closeOnSelect;

  const SpeedPanel({
    super.key,
    required this.currentSpeed,
    required this.onSpeedChanged,
    this.closeOnSelect = true,
  });

  /// 根据视频特性动态调整可用的倍速选项
  List<double> _getAvailableSpeeds(BuildContext context, WidgetRef ref) {
    return [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final availableSpeeds = _getAvailableSpeeds(context, ref);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: Row(
            children: [
              const Text(
                '倍速播放',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Spacer(),

              /// 显示性能提示
              Consumer(
                builder: (context, ref, _) {
                  final state = ref.watch(playbackProvider);
                  final isHighResolution =
                      state.selectedVideoTrack?.w != null &&
                          state.selectedVideoTrack?.h != null &&
                          (state.selectedVideoTrack!.w! >= 3840 ||
                              state.selectedVideoTrack!.h! >= 2160);

                  if (isHighResolution) {
                    return const Tooltip(
                      message: '4K视频高倍速播放将自动优化同步',
                      child: Icon(
                        Icons.speed,
                        color: Colors.blue,
                        size: 16,
                      ),
                    );
                  }
                  return const SizedBox.shrink();
                },
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: availableSpeeds.length,
            itemBuilder: (context, index) {
              final speed = availableSpeeds[index];
              final isSelected = (speed - currentSpeed).abs() < 0.01;
              return GestureDetector(
                onTap: () {
                  onSpeedChanged(speed);
                  if (closeOnSelect) {
                    Navigator.of(context).maybePop();
                  }
                },
                child: Container(
                  margin:
                      const EdgeInsets.symmetric(vertical: 4, horizontal: 16),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  decoration: BoxDecoration(
                    color: const Color(0xFF666666).withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(12),
                    border: isSelected
                        ? Border.all(color: const Color(0xFFFFE796), width: 1)
                        : null,
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    '${speed}x',
                    style: TextStyle(
                      color:
                          isSelected ? const Color(0xFFFFE796) : Colors.white,
                      fontSize: 14,
                      fontWeight:
                          isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}
