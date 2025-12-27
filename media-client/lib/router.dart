import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:media_client/profile/profile_home_page.dart';
import 'app_shell.dart';
// import 'media_library/media_home_page.dart';
import 'media_library/search_page.dart';
import 'media_library/detail_page.dart';
import 'media_player/media_player_page.dart';
import 'media_library/media_models.dart';
import 'package:media_client/source_library/sources_home_page.dart';
import 'package:media_client/source_library/source_type_select_page.dart';
import 'package:media_client/source_library/source_edit_page.dart';
import 'package:media_client/source_library/source_webdav_form_page.dart';
import 'package:media_client/source_library/storage_browser_page.dart';
// import 'profile/home_page.dart';
import 'profile/login_page.dart';
import 'profile/home_sections_page.dart';
import 'media_library/media_kind_page.dart';
import 'media_library/genres_page.dart';
import 'media_library/recent_list_page.dart';

final routeObserver = RouteObserver<ModalRoute<void>>();

final appRouter = GoRouter(
  observers: [routeObserver],
  initialLocation: '/media',
  routes: [
    GoRoute(
      path: '/player/:id',
      builder: (context, state) {
        final coreId = state.pathParameters['id']!;
        final extra = state.extra;
        return MediaPlayerPage(coreId: coreId, extra: extra);
      },
    ),
    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) =>
          AppShell(navigationShell: navigationShell),
      branches: [
        StatefulShellBranch(routes: [
          GoRoute(
            path: '/media',
            builder: (context, state) => const MediaLibraryPage(),
            routes: [
              GoRoute(
                path: 'search',
                builder: (context, state) {
                  final kind = state.uri.queryParameters['kind'];
                  return SearchPage(initialKind: kind);
                },
              ),
              GoRoute(
                path: 'cards',
                builder: (context, state) {
                  final title = state.uri.queryParameters['title'];
                  final kind = state.uri.queryParameters['kind'];
                  final genresParam = state.uri.queryParameters['genres'];
                  final genres = genresParam
                      ?.split(',')
                      .where((e) => e.isNotEmpty)
                      .toList();
                  return MediaKindPage(
                      title: title, kind: kind, genres: genres);
                },
              ),
              GoRoute(
                path: 'genres',
                builder: (context, state) => const GenresPage(),
              ),
              GoRoute(
                path: 'recent',
                builder: (context, state) => const RecentListPage(),
              ),
              GoRoute(
                path: 'detail/:id',
                builder: (context, state) {
                  final idStr = state.pathParameters['id']!;
                  // Try parsing as int, otherwise treat as 0 or error?
                  // Since we are moving to int IDs, we expect numeric ID here.
                  final id = int.tryParse(idStr) ?? 0;
                  final extraItem = state.extra as HomeCardItem?;
                  return MediaDetailPage(mediaId: id, previewItem: extraItem);
                },
              ),
              // 移除旧的分类列表页，统一使用卡片页
            ],
          ),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(
            path: '/sources',
            builder: (context, state) => const SourcesHomePage(),
            routes: [
              GoRoute(
                path: 'add',
                builder: (context, state) {
                  final t = state.uri.queryParameters['type'];
                  if (t == 'webdav') {
                    return const SourceWebDavFormPage();
                  }
                  return const SourceTypeSelectPage();
                },
              ),
              GoRoute(
                path: 'browse/:id',
                builder: (context, state) {
                  final idStr = state.pathParameters['id']!;
                  final id = int.tryParse(idStr) ?? 0;
                  final path = state.uri.queryParameters['path'] ?? '/';
                  final title = state.uri.queryParameters['title'];
                  return StorageBrowserPage(
                      storageId: id, path: path, title: title);
                },
              ),
              GoRoute(
                path: ':id/edit',
                builder: (context, state) {
                  final id = state.pathParameters['id']!;
                  final t = state.uri.queryParameters['type'];
                  final name = state.uri.queryParameters['name'];
                  final hostname = state.uri.queryParameters['hostname'];
                  final login = state.uri.queryParameters['login'];
                  final rootPath = state.uri.queryParameters['root_path'];
                  final detail = {
                    if (name != null) 'name': name,
                    if (hostname != null) 'hostname': hostname,
                    if (login != null) 'login': login,
                    if (rootPath != null) 'root_path': rootPath,
                  };
                  if (t == 'webdav') {
                    return SourceWebDavFormPage(
                        sourceId: id,
                        initialDetail: detail.isEmpty ? null : detail);
                  }
                  final status = state.uri.queryParameters['status'];
                  return SourceEditPage(
                      sourceId: id,
                      initialName: name,
                      initialType: t,
                      initialStatus: status);
                },
              ),
            ],
          ),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(
            path: '/profile',
            builder: (context, state) => const ProfileHomePage(),
            routes: [
              GoRoute(
                path: 'login',
                builder: (context, state) => const LoginPage(),
              ),
              GoRoute(
                path: 'settings',
                builder: (context, state) => const HomeSectionsPage(),
              ),
            ],
          ),
        ]),
      ],
    ),
  ],
);
