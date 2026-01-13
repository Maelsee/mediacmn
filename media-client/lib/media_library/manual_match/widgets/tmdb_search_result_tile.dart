import 'package:flutter/material.dart';
import '../manual_match_models.dart';

/// TMDB 搜索结果条目
///
/// 展示海报、标题、日期、地区与简介。
class TmdbSearchResultTile extends StatelessWidget {
  final TmdbSearchItem item;
  final bool isSelected;
  final VoidCallback onTap;

  const TmdbSearchResultTile({
    super.key,
    required this.item,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    // 构建图片 URL，假设后端返回的是 TMDB path，需拼接
    // 如果后端直接返回完整 URL，这里需要调整
    // TMDB 默认图片前缀
    const tmdbImageBase = 'https://image.tmdb.org/t/p/w200';
    String? imageUrl;
    if (item.posterPath != null) {
      if (item.posterPath!.startsWith('http')) {
        imageUrl = item.posterPath;
      } else {
        imageUrl = '$tmdbImageBase${item.posterPath}';
      }
    }

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          color: isSelected
              ? Theme.of(context)
                  .colorScheme
                  .primaryContainer
                  .withValues(alpha: 0.2)
              : Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(8),
          border: isSelected
              ? Border.all(color: Theme.of(context).colorScheme.primary)
              : null,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 海报
            ClipRRect(
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(8),
                bottomLeft: Radius.circular(8),
              ),
              child: SizedBox(
                width: 80,
                height: 120,
                child: imageUrl != null
                    ? Image.network(
                        imageUrl,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Container(
                          color: Colors.grey.shade800,
                          child: const Icon(Icons.movie, color: Colors.white54),
                        ),
                      )
                    : Container(
                        color: Colors.grey.shade800,
                        child: const Icon(Icons.movie, color: Colors.white54),
                      ),
              ),
            ),
            // 信息
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 类型标签
                    if (item.type.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 4, vertical: 2),
                        margin: const EdgeInsets.only(bottom: 4),
                        decoration: BoxDecoration(
                          color: item.type == 'movie'
                              ? Colors.blue.shade900
                              : Colors.orange.shade900,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          item.type == 'movie' ? '电影' : '剧集',
                          style: const TextStyle(
                              fontSize: 10, color: Colors.white),
                        ),
                      ),
                    // 标题
                    Text(
                      item.title,
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.bold),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    // 日期 | 地区
                    Text(
                      '${item.releaseDate ?? '日期未知'} | ${item.originCountry.join('/')}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.grey,
                          ),
                    ),
                    const SizedBox(height: 8),
                    // 简介
                    Text(
                      item.overview ?? '暂无简介',
                      style: Theme.of(context).textTheme.bodySmall,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
