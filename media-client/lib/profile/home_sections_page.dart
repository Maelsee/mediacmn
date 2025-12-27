import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'settings_provider.dart';

class HomeSectionsPage extends ConsumerStatefulWidget {
  const HomeSectionsPage({super.key});

  @override
  ConsumerState<HomeSectionsPage> createState() => _HomeSectionsPageState();
}

class _HomeSectionsPageState extends ConsumerState<HomeSectionsPage> {
  late List<String> _order;
  late Map<String, bool> _vis;

  @override
  void initState() {
    super.initState();
    final s = ref.read(settingsProvider);
    _order = List.of(s.order.isEmpty ? defaultSections : s.order);
    _vis = Map.of(s.visibility.isEmpty
        ? {for (final i in defaultSections) i: true}
        : s.visibility);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('自定义媒体库首页'),
        // backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          TextButton(onPressed: _onSave, child: const Text('保存')),
        ],
      ),
      body: ReorderableListView.builder(
        itemCount: _order.length,
        onReorder: (oldIndex, newIndex) {
          setState(() {
            if (newIndex > oldIndex) newIndex -= 1;
            final item = _order.removeAt(oldIndex);
            _order.insert(newIndex, item);
          });
        },
        itemBuilder: (context, index) {
          final name = _order[index];
          final visible = _vis[name] ?? true;
          return ListTile(
            key: ValueKey(name),
            leading: IconButton(
              icon: Icon(visible
                  ? Icons.remove_circle_outline
                  : Icons.add_circle_outline),
              onPressed: () => setState(() => _vis[name] = !visible),
            ),
            title: Text(name),
            trailing: const Icon(Icons.drag_handle),
          );
        },
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              OutlinedButton(onPressed: _onReset, child: const Text('重置默认')),
              const SizedBox(width: 12),
              Expanded(child: Text('已全部添加至“首页专辑”')),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _onSave() async {
    await ref
        .read(settingsProvider.notifier)
        .setOrderAndVisibility(_order, _vis);
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _onReset() async {
    setState(() {
      _order = List.of(defaultSections);
      _vis = {for (final s in defaultSections) s: true};
    });
  }
}
