import 'package:flutter/material.dart';

/// 面板列表项的统一样式组件。
///
/// 用于倍速、画质、音轨、字幕等面板中，统一背景色、圆角和选中高亮样式。
class PanelListItem extends StatelessWidget {
  final bool isSelected;
  final VoidCallback? onTap;
  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry margin;

  const PanelListItem({
    super.key,
    required this.isSelected,
    required this.child,
    this.onTap,
    this.padding = const EdgeInsets.symmetric(vertical: 14),
    this.margin = const EdgeInsets.symmetric(vertical: 4, horizontal: 16),
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: margin,
        padding: padding,
        decoration: BoxDecoration(
          color: const Color(0xFF666666).withValues(alpha: 0.3),
          borderRadius: BorderRadius.circular(12),
          border: isSelected
              ? Border.all(color: const Color(0xFFFFE796), width: 1)
              : null,
        ),
        alignment: Alignment.center,
        child: child,
      ),
    );
  }
}
