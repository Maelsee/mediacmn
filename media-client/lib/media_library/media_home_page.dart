import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../router.dart';
import '../profile/settings_provider.dart';
import 'media_provider.dart';
import '../source_library/sources_provider.dart';
import 'home_sections/section_factory.dart';
import 'recent_provider.dart';

class MediaLibraryHomePage extends ConsumerStatefulWidget {
  const MediaLibraryHomePage({super.key});

  @override
  ConsumerState<MediaLibraryHomePage> createState() =>
      _MediaLibraryHomePageState();
}

class _MediaLibraryHomePageState extends ConsumerState<MediaLibraryHomePage>
    with RouteAware {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(recentProvider.notifier).load(limit: 5);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // 监听路由变化，用于返回首页时刷新
    final route = ModalRoute.of(context);
    if (route is PageRoute) {
      routeObserver.subscribe(this, route);
    }
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    super.dispose();
  }

  @override
  void didPopNext() {
    // 当从其他页面（如播放页、详情页、列表页）返回到此页面时触发
    ref.read(recentProvider.notifier).load(limit: 5);
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(settingsProvider);
    final m = ref.watch(mediaHomeProvider);
    final ready = ref.watch(libraryReadyProvider);

    if (!s.ready || m.loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (!ready) {
      return _emptyState(context);
    }

    final order = s.order;
    final vis = s.visibility;

    return RefreshIndicator(
      onRefresh: () async {
        await ref.read(mediaHomeProvider.notifier).load();
        await ref.read(recentProvider.notifier).load(limit: 5);
      },
      child: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          for (final name in order)
            if (vis[name] ?? true) SectionFactory.createSection(name, m),
        ],
      ),
    );
  }

  Widget _emptyState(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: const [
            Icon(Icons.movie_filter_outlined, size: 72),
            SizedBox(height: 16),
            Text(
              '欢迎来到个人影视库！',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: 8),
            Text('添加视频资源后即可打造私人影视库，随时随地观看', textAlign: TextAlign.center),
            SizedBox(height: 16),
            Text('请点击底部“资源库”进入添加资源', textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
