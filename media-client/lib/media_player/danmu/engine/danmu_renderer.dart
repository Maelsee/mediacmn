import 'dart:collection';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'danmu_item.dart';

class DanmuRenderer extends CustomPainter {
  final List<DanmuItem> items;
  final double elapsed; // 当前播放时间（秒）
  final double viewWidth;
  final double viewHeight;
  final double fontSize;

  // LRU Paragraph 缓存，上限 2000 条，超出时淘汰最久未使用的
  static final LinkedHashMap<int, ui.Paragraph> _paragraphCache =
      LinkedHashMap<int, ui.Paragraph>();
  static const int _maxCacheSize = 2000;
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

    // 预淘汰：只保留当前活跃项的缓存，清理不再使用的条目
    _evictStale();

    for (final item in items) {
      if (!item.alive) continue;
      final sx = item.screenX(elapsed);
      // 屏幕外的弹幕跳过绘制（左边界和右边界各留 50px 余量）
      if (sx + item.width < -50 || sx > viewWidth + 50) continue;

      final color = Color(item.comment.color).withAlpha(255);

      // 使用 Paragraph API（比 TextPainter 更轻量）
      final paragraph = _getParagraph(item, color);
      canvas.drawParagraph(paragraph, Offset(sx, item.y));
    }
  }

  /// 淘汰不在活跃列表中的缓存条目，控制内存上限
  void _evictStale() {
    if (_paragraphCache.length <= _maxCacheSize) return;
    // 构建当前活跃 cid 集合
    final activeCids = <int>{};
    for (final item in items) {
      activeCids.add(item.comment.cid);
    }
    // 移除不在活跃列表中的条目（从头部开始，最久未访问的在前面）
    final toRemove = <int>[];
    for (final key in _paragraphCache.keys) {
      if (!activeCids.contains(key)) {
        toRemove.add(key);
      }
      if (_paragraphCache.length - toRemove.length <= _maxCacheSize * 0.8) {
        break; // 清理到 80% 即可，避免每次清理太多
      }
    }
    for (final key in toRemove) {
      _paragraphCache.remove(key);
    }
  }

  ui.Paragraph _getParagraph(DanmuItem item, Color color) {
    final cid = item.comment.cid;
    // 访问时移到末尾（LRU 语义）
    final cached = _paragraphCache.remove(cid);
    if (cached != null) {
      _paragraphCache[cid] = cached;
      return cached;
    }

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
    _paragraphCache[cid] = paragraph;
    return paragraph;
  }

  @override
  bool shouldRepaint(covariant DanmuRenderer old) {
    // elapsed 变化时必须重绘（弹幕位置依赖 elapsed 计算）
    return elapsed != old.elapsed ||
        !identical(items, old.items) ||
        items.length != old.items.length ||
        fontSize != old.fontSize;
  }

  static void clearCache() {
    _paragraphCache.clear();
  }
}
