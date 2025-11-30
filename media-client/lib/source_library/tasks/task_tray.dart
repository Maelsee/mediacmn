import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'task_provider.dart';
import 'package:go_router/go_router.dart';
import '../../media_library/media_provider.dart';

class TaskTray extends ConsumerStatefulWidget {
  const TaskTray({super.key});

  @override
  ConsumerState<TaskTray> createState() => _TaskTrayState();
}

class _TaskTrayState extends ConsumerState<TaskTray> {
  String? _observedGroupId;
  bool _didNotify = false;
  bool _listening = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_listening) return;
    _listening = true;
    ref.listen(tasksProvider, (previous, next) {
      final gid = next.currentGroup?.groupId;
      if (gid != _observedGroupId) {
        _observedGroupId = gid;
        _didNotify = false;
      }
      final hasGroup = gid != null;
      final runningEmpty = next.running.isEmpty;
      final hasCompleted = next.completed.isNotEmpty;
      if (hasGroup && runningEmpty && hasCompleted && !_didNotify) {
        _didNotify = true;
        ref.read(mediaHomeProvider.notifier).load();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(tasksProvider);
    if (!s.showTray || (s.currentGroup == null && s.singleSourceId == null)) {
      return const SizedBox.shrink();
    }
    final running = s.running.length;
    final completed = s.completed.length;
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(top: BorderSide(color: Theme.of(context).dividerColor)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          const Icon(Icons.sync, size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text('扫描中 $running 项，已完成 $completed 项')),
          TextButton(
            onPressed: () {
              GoRouter.of(context).push('/sources');
            },
            child: const Text('查看详情'),
          ),
          IconButton(
              onPressed: () => ref.read(tasksProvider.notifier).hideTray(),
              icon: const Icon(Icons.close))
        ],
      ),
    );
  }
}
