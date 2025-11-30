import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'task_provider.dart';

class TaskCenterPage extends ConsumerWidget {
  const TaskCenterPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(tasksProvider);
    ref.read(tasksProvider.notifier).startAutoRefresh();
    return Scaffold(
      appBar: AppBar(title: const Text('任务中心'), actions: [
        IconButton(
            onPressed: () => ref.read(tasksProvider.notifier).refreshGroup(),
            icon: const Icon(Icons.refresh)),
      ]),
      body: ListView(
        children: [
          if (s.running.isNotEmpty) ...[
            const ListTile(title: Text('进行中')),
            ...s.running.map((t) => ListTile(
                  leading: const Icon(Icons.sync),
                  title: Text('源 ${t.sourceId}'),
                  subtitle: Text('进度 ${t.progress}% · 状态 ${t.status}'),
                )),
          ],
          if (s.completed.isNotEmpty) ...[
            const Divider(),
            const ListTile(title: Text('已完成')),
            ...s.completed.map((t) => ListTile(
                  leading: Icon(t.status == 'succeeded'
                      ? Icons.check_circle_outline
                      : Icons.error_outline),
                  title: Text('源 ${t.sourceId}'),
                  subtitle: Text(
                      '状态 ${t.status}${t.error != null ? ' · 错误 ${t.error}' : ''}'),
                )),
          ],
          if (s.running.isEmpty && s.completed.isEmpty)
            const Center(
                child: Padding(
              padding: EdgeInsets.all(24),
              child: Text('暂无任务'),
            )),
        ],
      ),
    );
  }
}
