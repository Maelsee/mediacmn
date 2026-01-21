import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

const defaultSections = ['最近观看', '类型', '电影', '电视剧', '动漫', '综艺'];

class SettingsState {
  final ThemeMode themeMode;
  final Locale? locale; // null means system default
  final List<String> order;
  final Map<String, bool> visibility;
  final bool ready;

  const SettingsState({
    this.themeMode = ThemeMode.system,
    this.locale,
    this.order = const [],
    this.visibility = const {},
    this.ready = true,
  });

  SettingsState copyWith({
    ThemeMode? themeMode,
    Locale? locale,
    bool forceLocaleNull = false,
    List<String>? order,
    Map<String, bool>? visibility,
    bool? ready,
  }) {
    return SettingsState(
      themeMode: themeMode ?? this.themeMode,
      locale: forceLocaleNull ? null : (locale ?? this.locale),
      order: order ?? this.order,
      visibility: visibility ?? this.visibility,
      ready: ready ?? this.ready,
    );
  }
}

class SettingsNotifier extends Notifier<SettingsState> {
  late Box _box;

  @override
  SettingsState build() {
    _box = Hive.box('settings');
    return _loadFromBox();
  }

  SettingsState _loadFromBox() {
    final themeModeIndex =
        _box.get('themeMode', defaultValue: ThemeMode.system.index);
    final localeTag = _box.get('locale'); // String like "en", "zh_CN" or null

    final orderRaw = _box.get('home_order');
    final List<String> order = orderRaw != null
        ? List<String>.from(orderRaw)
        : List.of(defaultSections);

    final visRaw = _box.get('home_visibility');
    final Map<String, bool> visibility = visRaw != null
        ? Map<String, bool>.from(visRaw)
        : {for (final s in defaultSections) s: true};

    return SettingsState(
      themeMode: ThemeMode.values[themeModeIndex],
      locale: localeTag != null ? _parseLocale(localeTag) : null,
      order: order,
      visibility: visibility,
      ready: true,
    );
  }

  Locale _parseLocale(String tag) {
    final parts = tag.split('_');
    if (parts.length == 2) {
      return Locale(parts[0], parts[1]);
    }
    return Locale(parts[0]);
  }

  String? _localeToString(Locale? locale) {
    if (locale == null) return null;
    if (locale.countryCode != null) {
      return '${locale.languageCode}_${locale.countryCode}';
    }
    return locale.languageCode;
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    state = state.copyWith(themeMode: mode);
    await _box.put('themeMode', mode.index);
  }

  Future<void> setLocale(Locale? locale) async {
    state = state.copyWith(locale: locale, forceLocaleNull: locale == null);
    await _box.put('locale', _localeToString(locale));
  }

  Future<void> setOrderAndVisibility(
      List<String> order, Map<String, bool> visibility) async {
    state = state.copyWith(order: order, visibility: visibility);
    await _box.put('home_order', order);
    await _box.put('home_visibility', visibility);
  }
}

final settingsProvider =
    NotifierProvider<SettingsNotifier, SettingsState>(SettingsNotifier.new);
