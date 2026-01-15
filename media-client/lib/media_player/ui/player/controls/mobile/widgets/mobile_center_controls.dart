import 'package:flutter/material.dart';

class MobileCenterControls extends StatelessWidget {
  final bool isLocked;
  final VoidCallback onLockToggle;
  final VoidCallback onOrientationToggle;

  const MobileCenterControls({
    super.key,
    required this.isLocked,
    required this.onLockToggle,
    required this.onOrientationToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: Padding(
            padding: const EdgeInsets.only(left: 32),
            child: IconButton(
              icon: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    isLocked ? Icons.lock : Icons.lock_open,
                    color: Colors.white,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    isLocked ? '锁定' : '锁屏',
                    style: const TextStyle(color: Colors.white, fontSize: 10),
                  ),
                ],
              ),
              onPressed: onLockToggle,
            ),
          ),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.only(right: 32),
            child: IconButton(
              icon: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.screen_rotation, color: Colors.white),
                  const SizedBox(height: 4),
                  const Text(
                    '旋转',
                    style: TextStyle(color: Colors.white, fontSize: 10),
                  ),
                ],
              ),
              onPressed: onOrientationToggle,
            ),
          ),
        ),
      ],
    );
  }
}
