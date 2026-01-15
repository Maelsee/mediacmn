import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
// apiClientProvider 已从 core/api_client.dart 导出，无需任务模块
import 'source_models.dart';

class SourcesState {
  final List<SourceItem> items;
  final bool loading;
  final String? error;
  final Map<String, Map<String, dynamic>> details;
  const SourcesState({
    this.items = const [],
    this.loading = false,
    this.error,
    this.details = const {},
  });
}

class SourcesNotifier extends StateNotifier<SourcesState> {
  final ApiClient api;
  SourcesNotifier(this.api) : super(const SourcesState());
  DateTime? _lastConnRefresh;

  Future<void> load() async {
    state = SourcesState(loading: true, details: state.details);
    try {
      final items = await api.getSources();
      state = SourcesState(items: items, details: state.details);
      await _refreshConnectionsThrottled();
    } catch (e) {
      state = SourcesState(error: '$e', details: state.details);
    }
  }

  Future<void> scan(String sourceId) async {
    try {
      final id = int.tryParse(sourceId);
      if (id != null) {
        await api.startScan(storageId: id);
      }
      // 兼容旧任务模型，后续由任务模块展示托盘
    } catch (_) {}
  }

  void setStatus(String sourceId, String status) {
    final updated = state.items
        .map(
          (it) => it.id == sourceId
              ? SourceItem(
                  id: it.id,
                  type: it.type,
                  name: it.name,
                  status: status,
                  lastScan: it.lastScan,
                )
              : it,
        )
        .toList();
    state = SourcesState(
      items: updated,
      loading: state.loading,
      error: state.error,
      details: state.details,
    );
  }

  void updateName(String sourceId, String name) {
    final updated = state.items
        .map(
          (it) => it.id == sourceId
              ? SourceItem(
                  id: it.id,
                  type: it.type,
                  name: name,
                  status: it.status,
                  lastScan: it.lastScan,
                )
              : it,
        )
        .toList();
    final newDetails = Map<String, Map<String, dynamic>>.from(state.details);
    final d = newDetails[sourceId];
    if (d != null) {
      newDetails[sourceId] = {...d, 'name': name};
    }
    state = SourcesState(
      items: updated,
      loading: state.loading,
      error: state.error,
      details: newDetails,
    );
  }

  void cacheDetail(String sourceId, Map<String, dynamic> detail) {
    final newDetails = Map<String, Map<String, dynamic>>.from(state.details);
    newDetails[sourceId] = {...(newDetails[sourceId] ?? {}), ...detail};
    state = SourcesState(
      items: state.items,
      loading: state.loading,
      error: state.error,
      details: newDetails,
    );
  }

  Future<Map<String, dynamic>> getDetail(String sourceId) async {
    final cached = state.details[sourceId];
    if (cached != null) return cached;
    final detail = await api.getStorageDetail(sourceId);
    cacheDetail(sourceId, detail);
    return detail;
  }

  Future<void> _refreshConnectionsThrottled() async {
    final now = DateTime.now();
    if (_lastConnRefresh != null &&
        now.difference(_lastConnRefresh!).inSeconds < 2) {
      return;
    }
    _lastConnRefresh = now;
    await refreshConnections();
  }

  Future<void> refreshConnections({int concurrency = 4}) async {
    final items = List<SourceItem>.from(state.items);
    if (items.isEmpty) return;
    Future<void> testOne(SourceItem it) async {
      try {
        final ok = await api.testStorageConnection(it.id);
        setStatus(it.id, ok ? 'connected' : 'disconnected');
      } catch (_) {
        setStatus(it.id, 'disconnected');
      }
    }

    final batch = <Future<void>>[];
    for (final it in items) {
      batch.add(testOne(it));
      if (batch.length >= concurrency) {
        await Future.wait(batch);
        batch.clear();
      }
    }
    if (batch.isNotEmpty) {
      await Future.wait(batch);
    }
  }
}

final sourcesProvider = StateNotifierProvider<SourcesNotifier, SourcesState>((
  ref,
) {
  final api = ref.watch(apiClientProvider);
  final n = SourcesNotifier(api);
  n.load();
  return n;
});

final libraryReadyProvider = Provider<bool>((ref) {
  final api = ref.watch(apiClientProvider);
  final s = ref.watch(sourcesProvider);
  return api.isLoggedIn && s.error == null && s.items.isNotEmpty;
});
