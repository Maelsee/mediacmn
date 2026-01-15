import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/config.dart';
import '../media_models.dart';

class MediaCard extends StatelessWidget {
  final HomeCardItem item;
  final VoidCallback? onTap;
  final bool showRating;
  final double width;
  final double height;
  final EdgeInsetsGeometry margin;
  const MediaCard({
    super.key,
    required this.item,
    this.onTap,
    this.showRating = true,
    this.width = 120,
    this.height = 205,
    this.margin = const EdgeInsets.symmetric(horizontal: 0),
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap ??
          () => GoRouter.of(
                context,
              ).push('/media/detail/${item.id}', extra: item),
      child: Container(
        width: width,
        height: height,
        margin: margin,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: SizedBox(
                height: height - 28,
                child: AspectRatio(
                  aspectRatio: 0.68,
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: Builder(
                          builder: (ctx) {
                            final p = item.coverUrl;
                            if (p == null || p.isEmpty) {
                              return Container(color: Colors.grey.shade300);
                            }
                            final url = (p.startsWith('http://') ||
                                    p.startsWith('https://'))
                                ? p
                                : '${AppConfig.baseUrl}$p';
                            return Image.network(url, fit: BoxFit.cover);
                          },
                        ),
                      ),
                      if (showRating && item.rating != null)
                        Positioned(
                          right: 6,
                          top: 6,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.black87,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              item.rating!.toStringAsFixed(1),
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 12,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(item.name, maxLines: 1, overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}
