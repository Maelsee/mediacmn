import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../source_library/tasks/task_provider.dart';

class RegisterPage extends ConsumerStatefulWidget {
  const RegisterPage({super.key});

  @override
  ConsumerState<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends ConsumerState<RegisterPage> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('注册')),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 24),
            Center(
              child: Icon(
                Icons.person_add_outlined,
                size: 64,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Text(
                '注册新账号',
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
            const SizedBox(height: 24),
            TextFormField(
              controller: _email,
              decoration: const InputDecoration(labelText: '邮箱'),
              validator: _req,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _password,
              decoration: const InputDecoration(labelText: '密码'),
              obscureText: true,
              validator: _req,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _busy ? null : _onRegister,
              child: _busy
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('注册'),
            ),
            const SizedBox(height: 12),
            TextButton(
              onPressed: () {
                context.pop();
              },
              child: const Text('已有账号？去登录'),
            ),
            const SizedBox(height: 12),
            Opacity(
              opacity: 0.7,
              child: Text('注册表示同意《用户协议》《隐私政策》', textAlign: TextAlign.center),
            ),
          ],
        ),
      ),
    );
  }

  String? _req(String? v) => (v == null || v.isEmpty) ? '必填' : null;

  Future<void> _onRegister() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    try {
      final api = ref.read(apiClientProvider);
      await api.register(_email.text, _password.text);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('注册成功，请登录')));
        context.pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('注册失败：$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
