import 'package:flutter/material.dart';

class BaseSectionHeader extends StatelessWidget {
  final String title;
  final VoidCallback? onMoreTap;

  const BaseSectionHeader({super.key, required this.title, this.onMoreTap});

  @override

  /// 构建区块标题头部
  /// - 左侧显示标题
  /// - 右侧可选“更多”按钮（由 `onMoreTap` 控制显示与点击行为）
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          if (onMoreTap != null)
            IconButton(
              icon: const Icon(Icons.arrow_forward),
              onPressed: onMoreTap,
            ),
        ],
      ),
    );
  }
}
