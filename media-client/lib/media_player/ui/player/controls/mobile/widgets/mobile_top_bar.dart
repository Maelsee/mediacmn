import 'package:flutter/material.dart';

class MobileTopBar extends StatelessWidget {
  final String title;
  final VoidCallback onBack;
  final VoidCallback onSettings;
  final VoidCallback onPip;
  final VoidCallback? onDanmuSearch;

  const MobileTopBar({
    super.key,
    required this.title,
    required this.onBack,
    required this.onSettings,
    required this.onPip,
    this.onDanmuSearch,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.black.withValues(alpha: 0.8), Colors.transparent],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Row(
          children: [
            IconButton(
              icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
              onPressed: onBack,
            ),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            IconButton(
              icon: const Icon(
                Icons.picture_in_picture_alt,
                color: Colors.white,
              ),
              onPressed: onPip,
              tooltip: '小窗播放',
            ),
            if (onDanmuSearch != null)
              IconButton(
                icon: const Icon(Icons.search, color: Colors.white),
                onPressed: onDanmuSearch,
                tooltip: '搜索弹幕',
              ),
            IconButton(
              icon: const Icon(Icons.settings_outlined, color: Colors.white),
              onPressed: onSettings,
              tooltip: '设置',
            ),
          ],
        ),
      ),
    );
  }
}
