import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'tasks/task_provider.dart';
import 'sources_provider.dart';

class SourceWebDavFormPage extends ConsumerStatefulWidget {
  final String? sourceId;
  final Map<String, dynamic>? initialDetail;
  const SourceWebDavFormPage({super.key, this.sourceId, this.initialDetail});

  @override
  ConsumerState<SourceWebDavFormPage> createState() =>
      _SourceWebDavFormPageState();
}

class _SourceWebDavFormPageState extends ConsumerState<SourceWebDavFormPage> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _endpoint = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _basePath = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.initialDetail != null) {
      _applyPrefill(widget.initialDetail!);
    } else if (widget.sourceId != null && widget.sourceId!.isNotEmpty) {
      _prefill();
    }
  }

  Future<void> _prefill() async {
    try {
      final detail =
          await ref.read(apiClientProvider).getStorageDetail(widget.sourceId!);
      _applyPrefill(detail);
    } catch (_) {}
  }

  void _applyPrefill(Map<String, dynamic> detail) {
    _name.text = (detail['name'] as String?) ?? _name.text;
    final d = (detail['detail'] as Map<String, dynamic>?) ?? const {};
    final hostname = (detail['hostname'] as String?) ??
        (d['hostname'] as String?) ??
        _endpoint.text;
    final login = (detail['login'] as String?) ??
        (d['login'] as String?) ??
        _username.text;
    final rootPath = (detail['root_path'] as String?) ??
        (d['root_path'] as String?) ??
        _basePath.text;
    _endpoint.text = hostname;
    _username.text = login;
    _basePath.text = rootPath;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.sourceId == null ? '添加 WebDAV' : '编辑 WebDAV')),
      body: Form(
        key: _form,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(children: [
                    TextFormField(
                        controller: _name,
                        decoration: const InputDecoration(labelText: '名称'),
                        validator: _req),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: 'HTTP',
                      items: const [
                        DropdownMenuItem(value: 'HTTP', child: Text('HTTP')),
                        DropdownMenuItem(value: 'HTTPS', child: Text('HTTPS'))
                      ],
                      onChanged: (_) {},
                      decoration: const InputDecoration(labelText: '协议'),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                        controller: _endpoint,
                        decoration: const InputDecoration(
                            labelText: '地址*', hintText: '请输入IP或域名'),
                        validator: _req),
                    const SizedBox(height: 12),
                    TextFormField(
                        controller: _basePath,
                        decoration: const InputDecoration(
                            labelText: '路径', hintText: '例如：/dav')),
                    const SizedBox(height: 12),
                    TextFormField(
                        controller: _username,
                        decoration:
                            const InputDecoration(labelText: '用户名(选填)')),
                    const SizedBox(height: 12),
                    TextFormField(
                        controller: _password,
                        decoration: const InputDecoration(labelText: '密码(选填)'),
                        obscureText: true),
                  ]))),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: _busy ? null : _onSave,
              child: _busy
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(widget.sourceId == null ? '添加' : '保存')),
        ]),
      ),
    );
  }

  String? _req(String? v) => (v == null || v.isEmpty) ? '必填' : null;

  Future<void> _onSave() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    try {
      if (widget.sourceId != null && widget.sourceId!.isNotEmpty) {
        final api = ref.read(apiClientProvider);
        final payload = {
          'name': _name.text,
          'config': {
            'hostname': _endpoint.text,
            'login': _username.text,
            'root_path': _basePath.text,
            if (_password.text.isNotEmpty) 'password': _password.text,
          }
        };
        await api.updateSource(widget.sourceId!, payload);
        ref
            .read(sourcesProvider.notifier)
            .updateName(widget.sourceId!, _name.text);
        ref.read(sourcesProvider.notifier).cacheDetail(widget.sourceId!, {
          'name': _name.text,
          'hostname': _endpoint.text,
          'login': _username.text,
          'root_path': _basePath.text,
        });
        if (mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(const SnackBar(content: Text('保存成功')));
          if (mounted) context.pop(true);
        }
      } else {
        final res = await ref.read(apiClientProvider).createSource({
          'name': _name.text,
          'storage_type': 'webdav',
          'config': {
            'hostname': _endpoint.text,
            'login': _username.text,
            'password': _password.text,
            'root_path': _basePath.text,
            'verify_ssl': true
          }
        });
        ref.read(sourcesProvider.notifier).cacheDetail(res.id, {
          'name': _name.text,
          'storage_type': 'webdav',
          'hostname': _endpoint.text,
          'login': _username.text,
          'root_path': _basePath.text,
          'verify_ssl': true,
        });
        if (mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text('保存成功：${res.id}')));
          await ref.read(sourcesProvider.notifier).load();
          if (res.taskId != null) {
            ref
                .read(tasksProvider.notifier)
                .showSingleSourceTask(sourceId: res.id, taskId: res.taskId!);
            ref.read(tasksProvider.notifier).showTray();
          }
          await ref.read(tasksProvider.notifier).refreshGroup();
          if (mounted) {
            // context.pop();
            context.go('/sources');
          }
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('保存失败：$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
