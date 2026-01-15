import 'package:flutter/material.dart';

import 'desktop_player_window_page.dart';

class DesktopPlayerWindowApp extends StatelessWidget {
  final Map<String, dynamic> initialPayload;

  const DesktopPlayerWindowApp({
    super.key,
    required this.initialPayload,
  });

  @override
  Widget build(BuildContext context) {
    final dark = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorSchemeSeed: const Color(0xFF1F7AE0),
    );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: dark,
      home: DesktopPlayerWindowPage(initialPayload: initialPayload),
    );
  }
}
