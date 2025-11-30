import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'tasks/task_provider.dart';
import 'source_models.dart';

class SourceEditPage extends ConsumerStatefulWidget {
  final String sourceId;
  final String? initialName;
  final String? initialType;
  final String? initialStatus;
  const SourceEditPage(
      {super.key,
      required this.sourceId,
      this.initialName,
      this.initialType,
      this.initialStatus});

  @override
  ConsumerState<SourceEditPage> createState() => _SourceEditPageState();
}

class _SourceEditPageState extends ConsumerState<SourceEditPage> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  bool _busy = false;
  SourceItem? _item;

  @override
  void initState() {
    super.initState();
    if (widget.initialName != null && widget.initialName!.isNotEmpty) {
      _name.text = widget.initialName!;
    }
    _load();
  }

  Future<void> _load() async {
    final api = ref.read(apiClientProvider);
    final it = await api.getSource(widget.sourceId);
    setState(() {
      _item = it;
      _name.text = it.name;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('编辑资源源')),
      body: _item == null
          ? const Center(child: CircularProgressIndicator())
          : Form(
              key: _form,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text('类型：${widget.initialType ?? _item!.type}'),
                  const SizedBox(height: 12),
                  TextFormField(
                      controller: _name,
                      decoration: const InputDecoration(labelText: '名称'),
                      validator: _req),
                  const SizedBox(height: 24),
                  Row(children: [
                    FilledButton(
                        onPressed: _busy ? null : _onSave,
                        child: _busy
                            ? const SizedBox(
                                height: 16,
                                width: 16,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2))
                            : const Text('保存')),
                    const SizedBox(width: 12),
                    OutlinedButton(
                        onPressed: _busy ? null : _onDelete,
                        child: const Text('删除')),
                    const SizedBox(width: 12),
                    OutlinedButton(
                        onPressed: _busy ? null : _onToggle,
                        child: Text(
                            (widget.initialStatus ?? _item!.status) == 'enabled'
                                ? '停用'
                                : '启用')),
                  ]),
                ],
              ),
            ),
    );
  }

  String? _req(String? v) => (v == null || v.isEmpty) ? '必填' : null;

  Future<void> _onSave() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    try {
      final api = ref.read(apiClientProvider);
      await api.updateSource(widget.sourceId, {'name': _name.text});
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('保存成功')));
        if (mounted) context.pop(true);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _onDelete() async {
    setState(() => _busy = true);
    try {
      final api = ref.read(apiClientProvider);
      await api.deleteSource(widget.sourceId);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('已删除')));
        if (mounted) context.pop(true);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _onToggle() async {
    setState(() => _busy = true);
    try {
      final api = ref.read(apiClientProvider);
      final enabled = _item!.status != 'enabled';
      await api.toggleSource(widget.sourceId, enabled: enabled);
      setState(() => _item = SourceItem(
          id: _item!.id,
          type: _item!.type,
          name: _item!.name,
          status: enabled ? 'enabled' : 'disabled',
          lastScan: _item!.lastScan));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
