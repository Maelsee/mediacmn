import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../media_models.dart';
import 'base_section_header.dart';
import '../widgets/media_card.dart';

class MediaListSection extends StatelessWidget {
  final String title;
  final String kind;
  final List<HomeCardItem> items;
  final VoidCallback? onMoreTap;

  const MediaListSection({
    super.key,
    required this.title,
    required this.kind,
    required this.items,
    this.onMoreTap,
  });

  @override

  /// 构建“电影/电视剧”列表区块
  /// - 当列表为空时隐藏区块
  /// - 渲染水平滚动的 `MediaCard` 列表，点击查看更多进入筛选页
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BaseSectionHeader(
          title: title,
          onMoreTap: onMoreTap ??
              () {
                GoRouter.of(
                  context,
                ).push('/media/cards?title=$title&kind=$kind');
              },
        ),
        SizedBox(
          height: 215,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              return MediaCard(item: items[index], width: 120);
            },
          ),
        ),
      ],
    );
  }
}
