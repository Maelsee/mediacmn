import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

class SettingsState {
  final List<String> order;
  final Map<String, bool> visibility;
  final bool ready;
  const SettingsState({
    this.order = const [],
    this.visibility = const {},
    this.ready = false,
  });
}

const defaultSections = [
  '类型',
  '最近观看',
  '本地影片',
  '电影',
  '电视剧',
  '动漫',
  '综艺',
  '纪录片',
  '其他',
];

class SettingsNotifier extends StateNotifier<SettingsState> {
  static const boxName = 'settings_box';
  static const orderKey = 'home_sections_order';
  static const visKey = 'home_sections_visibility';

  Box? _box;
  SettingsNotifier() : super(const SettingsState());

  Future<void> load() async {
    _box ??= await Hive.openBox(boxName);
    final order =
        (_box!.get(orderKey) as List?)?.cast<String>() ?? defaultSections;
    final visRaw = (_box!.get(visKey) as Map?)?.cast<String, bool>() ??
        {for (final s in defaultSections) s: true};
    state = SettingsState(order: order, visibility: visRaw, ready: true);
  }

  Future<void> setOrder(List<String> order) async {
    if (_box == null) await load();
    await _box!.put(orderKey, order);
    state = SettingsState(
      order: order,
      visibility: state.visibility,
      ready: true,
    );
  }

  Future<void> setVisibility(Map<String, bool> vis) async {
    if (_box == null) await load();
    await _box!.put(visKey, vis);
    state = SettingsState(order: state.order, visibility: vis, ready: true);
  }

  Future<void> setOrderAndVisibility(
    List<String> order,
    Map<String, bool> vis,
  ) async {
    if (_box == null) await load();
    await _box!.put(orderKey, order);
    await _box!.put(visKey, vis);
    state = SettingsState(order: order, visibility: vis, ready: true);
  }

  Future<void> resetDefaults() async {
    if (_box == null) await load();
    final vis = {for (final s in defaultSections) s: true};
    await _box!.put(orderKey, defaultSections);
    await _box!.put(visKey, vis);
    state = const SettingsState(
      order: defaultSections,
      visibility: {
        '类型': true,
        '最近观看': true,
        '本地影片': true,
        '电影': true,
        '电视剧': true,
        '动漫': true,
        '综艺': true,
        '纪录片': true,
        '其他': true,
      },
      ready: true,
    );
  }
}

final settingsProvider = StateNotifierProvider<SettingsNotifier, SettingsState>(
  (ref) {
    final notifier = SettingsNotifier();
    notifier.load();
    return notifier;
  },
);
