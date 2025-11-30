import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../core/config.dart';
import '../../core/api_client.dart';
export '../../core/api_client.dart' show apiClientProvider, authUserProvider;
import 'task_models.dart';

// Providers apiClientProvider 与 authUserProvider 已迁移至 core/api_client.dart

class TasksState {
  final List<ScanTask> running;
  final List<ScanTask> completed;
  final ScanGroup? currentGroup;
  final String? singleSourceId;
  final bool showTray;
  const TasksState({
    this.running = const [],
    this.completed = const [],
    this.currentGroup,
    this.singleSourceId,
    this.showTray = true,
  });
}

class TasksNotifier extends StateNotifier<TasksState> {
  final ApiClient api;
  TasksNotifier(this.api) : super(const TasksState());

  Future<void> triggerGlobalScan({List<String>? sourceIds}) async {
    final group = await api.scanAll(sourceIds: sourceIds);
    state = TasksState(
        running: const [],
        completed: const [],
        currentGroup: group,
        singleSourceId: null,
        showTray: true);
    final base = AppConfig.baseUrl;
    final scheme = base.startsWith('https://') ? 'wss' : 'ws';
    final ws = Uri.parse(
        '${base.replaceFirst(RegExp('^https?'), scheme)}/tasks/stream');
    startWsSubscription(ws);
  }

  Future<void> refreshGroup() async {
    final g = state.currentGroup;
    if (g == null) {
      final sid = state.singleSourceId;
      if (sid == null) return;
      final tasks = await api.getTasksBySource(sid);
      final running = tasks
          .where((t) => t.status == 'running' || t.status == 'queued')
          .toList();
      final done = tasks
          .where((t) =>
              t.status == 'succeeded' ||
              t.status == 'failed' ||
              t.status == 'cancelled')
          .toList();
      state = TasksState(
          running: running,
          completed: done,
          singleSourceId: sid,
          showTray: state.showTray);
      return;
    }
    final tasks = await api.getGroup(g.groupId);
    final running = tasks
        .where((t) => t.status == 'running' || t.status == 'queued')
        .toList();
    final done = tasks
        .where((t) =>
            t.status == 'succeeded' ||
            t.status == 'failed' ||
            t.status == 'cancelled')
        .toList();
    state = TasksState(
        running: running,
        completed: done,
        currentGroup: g,
        showTray: state.showTray);
  }

  void showSingleSourceTask(
      {required String sourceId, required String taskId}) {
    final placeholder =
        ScanTask(id: taskId, sourceId: sourceId, status: 'queued', progress: 0);
    state = TasksState(
        running: [placeholder],
        completed: const [],
        singleSourceId: sourceId,
        showTray: true);
  }

  void startAutoRefresh({Duration interval = const Duration(seconds: 2)}) {
    Future<void> tick() async {
      await refreshGroup();
      Future.delayed(interval, tick);
    }

    Future.delayed(interval, tick);
  }

  WebSocketChannel? _channel;
  void startWsSubscription(Uri wsUri) {
    try {
      _channel?.sink.close();
      final ch = WebSocketChannel.connect(wsUri);
      _channel = ch;
      ch.stream.listen(
          (event) {
            try {
              final map = jsonDecode(event) as Map<String, dynamic>;
              final t = ScanTask.fromJson(map);
              final running = List<ScanTask>.from(state.running);
              final completed = List<ScanTask>.from(state.completed);
              final idx = running.indexWhere((x) => x.id == t.id);
              final doneStatus = t.status == 'succeeded' ||
                  t.status == 'failed' ||
                  t.status == 'cancelled';
              if (doneStatus) {
                if (idx >= 0) running.removeAt(idx);
                final cidx = completed.indexWhere((x) => x.id == t.id);
                if (cidx >= 0) {
                  completed[cidx] = t;
                } else {
                  completed.insert(0, t);
                }
              } else {
                if (idx >= 0) {
                  running[idx] = t;
                } else {
                  running.insert(0, t);
                }
              }
              state = TasksState(
                  running: running,
                  completed: completed,
                  currentGroup: state.currentGroup,
                  singleSourceId: state.singleSourceId);
              state = TasksState(
                  running: running,
                  completed: completed,
                  currentGroup: state.currentGroup,
                  singleSourceId: state.singleSourceId,
                  showTray: state.showTray);
            } catch (_) {}
          },
          onError: (_) {},
          onDone: () {
            _channel = null;
          });
    } catch (_) {}
  }

  void hideTray() {
    state = TasksState(
        running: state.running,
        completed: state.completed,
        currentGroup: state.currentGroup,
        singleSourceId: state.singleSourceId,
        showTray: false);
  }

  void showTray() {
    state = TasksState(
        running: state.running,
        completed: state.completed,
        currentGroup: state.currentGroup,
        singleSourceId: state.singleSourceId,
        showTray: true);
  }
}

final tasksProvider = StateNotifierProvider<TasksNotifier, TasksState>((ref) {
  final api = ref.read(apiClientProvider);
  return TasksNotifier(api);
});
