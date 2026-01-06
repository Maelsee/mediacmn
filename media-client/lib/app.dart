import 'package:flutter/material.dart';
import 'router.dart';

class MediaClientApp extends StatelessWidget {
  const MediaClientApp({super.key});

  /// AppBar 的统一高度（用于减少垂直空间占用）。
  static const double _appBarHeight = 48;

  /// 底部导航栏的统一高度（用于减少垂直空间占用）。
  static const double _bottomNavigationBarHeight = 64;

  @override
  Widget build(BuildContext context) {
    final light = ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorSchemeSeed: const Color(0xFF1F7AE0),
      appBarTheme: const AppBarTheme(
        toolbarHeight: _appBarHeight,
        scrolledUnderElevation: 0,
      ),
      navigationBarTheme: const NavigationBarThemeData(
        height: _bottomNavigationBarHeight,
      ),
      textTheme: const TextTheme(
        titleLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
        titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        titleSmall: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        bodyMedium: TextStyle(fontSize: 14),
        bodySmall: TextStyle(fontSize: 12),
      ),
    );
    final dark = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorSchemeSeed: const Color(0xFF1F7AE0),
      appBarTheme: const AppBarTheme(
        toolbarHeight: _appBarHeight,
        scrolledUnderElevation: 0,
      ),
      navigationBarTheme: const NavigationBarThemeData(
        height: _bottomNavigationBarHeight,
      ),
      textTheme: const TextTheme(
        titleLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
        titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        titleSmall: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        bodyMedium: TextStyle(fontSize: 14),
        bodySmall: TextStyle(fontSize: 12),
      ),
    );
    return MaterialApp.router(
      title: 'Media Client',
      theme: light,
      darkTheme: dark,
      debugShowCheckedModeBanner: false,
      routerConfig: appRouter,
    );
  }
}
