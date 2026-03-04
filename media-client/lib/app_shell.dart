// AppShell 是应用的主 Shell，包含了导航栏和多个页面。
// 导航栏包含了三个选项卡：媒体库、资源库和我的。
// 每个选项卡对应一个页面，分别是 MediaLibraryPage、SourceLibraryPage 和 ProfilePage。

import 'package:flutter/material.dart';
import 'package:media_client/profile/profile_home_page.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'media_library/media_home_page.dart';
import 'source_library/sources_provider.dart';

class AppShell extends StatefulWidget {
  final StatefulNavigationShell navigationShell;
  const AppShell({super.key, required this.navigationShell});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  /// 底部导航栏高度（用于减少垂直空间占用）。
  static const double _bottomNavigationBarHeight = 64;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: widget.navigationShell,
      bottomNavigationBar: NavigationBar(
        height: _bottomNavigationBarHeight,
        selectedIndex: widget.navigationShell.currentIndex,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.video_library_outlined),
            label: '媒体库',
          ),
          NavigationDestination(
            icon: Icon(Icons.folder_outlined),
            label: '资源库',
          ),
          NavigationDestination(icon: Icon(Icons.person_outline), label: '我的'),
        ],
        onDestinationSelected: (i) =>
            widget.navigationShell.goBranch(i, initialLocation: true),
      ),
    );
  }
}

class MediaLibraryPage extends ConsumerStatefulWidget {
  const MediaLibraryPage({super.key});

  @override
  ConsumerState<MediaLibraryPage> createState() => _MediaLibraryPageState();
}

class _MediaLibraryPageState extends ConsumerState<MediaLibraryPage> {
  @override
  Widget build(BuildContext context) {
    final ready = ref.watch(libraryReadyProvider);
    return Scaffold(
      appBar: !ready
          ? null
          : AppBar(
              title: const Text('媒体库'),
              actions: [
                IconButton(
                  onPressed: () {
                    GoRouter.of(context).push('/media/search');
                  },
                  icon: const Icon(Icons.search),
                ),
                IconButton(
                  onPressed: () {
                    GoRouter.of(context).push('/media/home-sections');
                  },
                  icon: const Icon(Icons.tune),
                ),
                IconButton(
                  onPressed: () {},
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
      body: Column(
        children: [
          const Expanded(child: MediaLibraryHomePage()),
        ],
      ),
    );
  }
}

//
class ProfilePage extends ConsumerWidget {
  const ProfilePage({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('我的')),
      body: ProfileHomePage(),
    );
  }
}
