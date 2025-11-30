import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../media_models.dart';
import 'base_section_header.dart';

class GenreSection extends StatelessWidget {
  final List<HomeCardGenre> genres;

  const GenreSection({super.key, required this.genres});

  @override

  /// 构建“类型”区块
  /// - 当分类为空时隐藏区块
  /// - 渲染水平滚动的分类卡片，点击跳转到分类筛选页
  Widget build(BuildContext context) {
    if (genres.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BaseSectionHeader(
          title: '类型',
          onMoreTap: () {
            GoRouter.of(context).push('/media/genres');
          },
        ),
        SizedBox(
          height: 84,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: genres.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final genre = genres[index];
              return _GenreCard(genre: genre);
            },
          ),
        ),
      ],
    );
  }
}

class _GenreCard extends StatelessWidget {
  final HomeCardGenre genre;

  const _GenreCard({required this.genre});

  @override

  /// 构建单个分类卡片
  /// - 展示分类名称
  /// - 点击跳转到媒体卡片列表页并带上分类筛选参数
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primaryContainer;
    return GestureDetector(
      onTap: () {
        GoRouter.of(context).push(
          '/media/cards?title=${genre.name}&genres=${genre.name}',
        );
      },
      child: Container(
        width: 120,
        height: 72,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(12),
        ),
        alignment: Alignment.bottomLeft,
        padding: const EdgeInsets.all(12),
        child: Text(
          genre.name,
          style: Theme.of(context).textTheme.titleSmall,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }
}
