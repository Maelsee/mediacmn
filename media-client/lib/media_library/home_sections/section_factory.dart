import 'package:flutter/material.dart';
import '../media_provider.dart';
import 'recent_section.dart';
import 'genre_section.dart';
import 'media_list_section.dart';

class SectionFactory {
  /// 根据区块名称创建首页的不同展示区块
  /// - `最近观看`: 展示最近播放的条目（水平滚动）
  /// - `类型`: 展示流派分类卡片
  /// - `电影`/`电视剧`: 展示对应类型的卡片列表
  static Widget createSection(String sectionName, MediaHomeState state) {
    switch (sectionName) {
      case '最近观看':
        return const RecentWatchSection();
      case '类型':
        return GenreSection(genres: state.data?.genres ?? []);
      case '电影':
        return MediaListSection(
          title: '电影',
          kind: 'movie',
          items: state.data?.movie ?? [],
        );
      case '电视剧':
        return MediaListSection(
          title: '电视剧',
          kind: 'tv',
          items: state.data?.tv ?? [],
        );
      case '动漫':
        return MediaListSection(
          title: '动漫',
          kind: 'animation',
          items: state.data?.animation ?? [],
        );
      default:
        return const SizedBox.shrink();
    }
  }
}
