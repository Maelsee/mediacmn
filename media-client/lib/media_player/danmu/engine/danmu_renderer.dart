import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'danmu_item.dart';

class DanmuRenderer extends CustomPainter {
  final List<DanmuItem> items;
  final double elapsed;       // 当前播放时间（秒）
  final double viewWidth;
  final double viewHeight;
  final double fontSize;

  // 文本画笔缓存（避免每帧重建）
  static final Map<int, TextPainter> _painterCache = {};
  static final Map<int, ui.Paragraph> _paragraphCache = {};
  static double _cachedFontSize = 0;

  DanmuRenderer({
    required this.items,
    required this.elapsed,
    required this.viewWidth,
    required this.viewHeight,
    required this.fontSize,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // 字体大小变化时清空缓存，强制重建所有 Paragraph
    if (fontSize != _cachedFontSize) {
      _cachedFontSize = fontSize;
      _paragraphCache.clear();
    }

    for (final item in items) {
      if (!item.alive) continue;
      final sx = item.screenX(elapsed);
      if (!item.isVisible(elapsed, viewWidth)) continue;

      final color = Color(item.comment.color).withAlpha(255);

      // 使用 Paragraph API（比 TextPainter 更轻量）
      final paragraph = _getParagraph(item, color);
      canvas.drawParagraph(paragraph, Offset(sx, item.y));
    }
  }

  ui.Paragraph _getParagraph(DanmuItem item, Color color) {
    // 用 cid 作为缓存 key（同一条弹幕只构建一次 Paragraph）
    final cached = _paragraphCache[item.comment.cid];
    if (cached != null) return cached;

    final builder = ui.ParagraphBuilder(
      ui.ParagraphStyle(fontSize: fontSize, textAlign: TextAlign.left),
    )
      ..pushStyle(ui.TextStyle(
        color: color,
        fontSize: fontSize,
        shadows: const [
          Shadow(blurRadius: 2, color: Colors.black54),
          Shadow(blurRadius: 4, color: Colors.black38),
        ],
      ))
      ..addText(item.comment.content);

    final paragraph = builder.build()
      ..layout(const ui.ParagraphConstraints(width: double.infinity));

    item.width = paragraph.longestLine;
    item.height = paragraph.height;
    _paragraphCache[item.comment.cid] = paragraph;
    return paragraph;
  }

  @override
  bool shouldRepaint(covariant DanmuRenderer old) => true;

  static void clearCache() {
    _painterCache.clear();
    _paragraphCache.clear();
  }
}
