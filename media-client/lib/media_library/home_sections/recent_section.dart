import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../recent_provider.dart';
import '../widgets/recent_media_card.dart';
import 'base_section_header.dart';

class RecentWatchSection extends ConsumerStatefulWidget {
  const RecentWatchSection({super.key});

  @override
  ConsumerState<RecentWatchSection> createState() => _RecentWatchSectionState();
}

class _RecentWatchSectionState extends ConsumerState<RecentWatchSection> {
  /// 初始化时触发最近观看列表加载（限制为5条，作为首页区块展示）
  final String title = '最近观看';
  // final String kind = 'recent';

  @override
  void initState() {
    super.initState();
    // 仅在初始化时加载一次
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(recentProvider.notifier).load(limit: 5);
    });
  }

  @override
  Widget build(BuildContext context) {
    /// 监听最近观看 Provider 状态变化，不在 build 中触发加载以避免重入
    final recentState = ref.watch(recentProvider);

    /// 若无数据则隐藏此区块（避免空白占位）
    if (recentState.items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Padding(
        //   padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        //   child: Row(
        //     mainAxisAlignment: MainAxisAlignment.spaceBetween,
        //     children: [
        //       Text(
        //         '最近观看',
        //         style: Theme.of(context).textTheme.titleLarge?.copyWith(
        //               fontWeight: FontWeight.bold,
        //             ),
        //       ),
        //       IconButton(
        //         icon: const Icon(Icons.arrow_forward),
        //         onPressed: () {
        //           GoRouter.of(context).push('/media/recent');
        //         },
        //       ),
        //     ],
        //   ),
        // ),
        BaseSectionHeader(
          title: title,
          onMoreTap: () {
            GoRouter.of(context).push('/media/recent');
          },
        ),
        SizedBox(
          height: 165,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: recentState.items.length,
            separatorBuilder: (context, index) =>
                const SizedBox(width: 12), // 显式间距
            itemBuilder: (context, index) {
              final item = recentState.items[index];
              return RecentMediaCard(
                item: item,
                onPlayReturn: () {
                  ref.read(recentProvider.notifier).load(limit: 5);
                },
              );
            },
          ),
        ),
      ],
    );
  }
}
