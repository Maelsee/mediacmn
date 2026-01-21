import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_client/profile/settings_provider.dart';

class UserSettingsPage extends ConsumerWidget {
  const UserSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);
    final notifier = ref.read(settingsProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('设置'),
      ),
      body: ListView(
        children: [
          ListTile(
            leading: const Icon(Icons.language),
            title: const Text('语言'),
            subtitle: Text(_getLocaleName(settings.locale)),
            onTap: () =>
                _showLanguageDialog(context, notifier, settings.locale),
          ),
          ListTile(
            leading: const Icon(Icons.brightness_6),
            title: const Text('主题'),
            subtitle: Text(_getThemeModeName(settings.themeMode)),
            onTap: () =>
                _showThemeDialog(context, notifier, settings.themeMode),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('关于'),
            subtitle: const Text('Media Client v0.1.0'),
            onTap: () {
              // Show about dialog or navigate
            },
          ),
        ],
      ),
    );
  }

  String _getLocaleName(Locale? locale) {
    if (locale == null) return '跟随系统';
    if (locale.languageCode == 'zh') return '简体中文';
    if (locale.languageCode == 'en') return 'English';
    return locale.toString();
  }

  String _getThemeModeName(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.system:
        return '跟随系统';
      case ThemeMode.light:
        return '浅色模式';
      case ThemeMode.dark:
        return '深色模式';
    }
  }

  void _showLanguageDialog(
      BuildContext context, SettingsNotifier notifier, Locale? current) {
    showDialog(
      context: context,
      builder: (context) {
        return SimpleDialog(
          title: const Text('选择语言'),
          children: [
            SimpleDialogOption(
              onPressed: () {
                notifier.setLocale(null);
                Navigator.pop(context);
              },
              child: _buildOption('跟随系统', current == null),
            ),
            SimpleDialogOption(
              onPressed: () {
                notifier.setLocale(const Locale('zh'));
                Navigator.pop(context);
              },
              child: _buildOption('简体中文', current?.languageCode == 'zh'),
            ),
            SimpleDialogOption(
              onPressed: () {
                notifier.setLocale(const Locale('en'));
                Navigator.pop(context);
              },
              child: _buildOption('English', current?.languageCode == 'en'),
            ),
          ],
        );
      },
    );
  }

  void _showThemeDialog(
      BuildContext context, SettingsNotifier notifier, ThemeMode current) {
    showDialog(
      context: context,
      builder: (context) {
        return SimpleDialog(
          title: const Text('选择主题'),
          children: [
            SimpleDialogOption(
              onPressed: () {
                notifier.setThemeMode(ThemeMode.system);
                Navigator.pop(context);
              },
              child: _buildOption('跟随系统', current == ThemeMode.system),
            ),
            SimpleDialogOption(
              onPressed: () {
                notifier.setThemeMode(ThemeMode.light);
                Navigator.pop(context);
              },
              child: _buildOption('浅色模式', current == ThemeMode.light),
            ),
            SimpleDialogOption(
              onPressed: () {
                notifier.setThemeMode(ThemeMode.dark);
                Navigator.pop(context);
              },
              child: _buildOption('深色模式', current == ThemeMode.dark),
            ),
          ],
        );
      },
    );
  }

  Widget _buildOption(String text, bool selected) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(text),
        if (selected) const Icon(Icons.check, color: Colors.blue),
      ],
    );
  }
}
