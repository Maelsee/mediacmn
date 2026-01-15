import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../source_library/tasks/task_provider.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('登录')),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 24),
            Center(
              child: Icon(
                Icons.local_movies_outlined,
                size: 64,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Text(
                '个人影视库',
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
              onPressed: _busy ? null : _onLogin,
              child: _busy
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('登录'),
            ),
            const SizedBox(height: 12),
            TextButton(
              onPressed: () {
                GoRouter.of(context).push('/profile/register');
              },
              child: const Text('没有账号？去注册'),
            ),
            const SizedBox(height: 12),
            Opacity(
              opacity: 0.7,
              child: Text('登录表示同意《用户协议》《隐私政策》', textAlign: TextAlign.center),
            ),
          ],
        ),
      ),
    );
  }

  String? _req(String? v) => (v == null || v.isEmpty) ? '必填' : null;

  Future<void> _onLogin() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    try {
      final api = ref.read(apiClientProvider);
      await api.loginWithEmail(_email.text, _password.text);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('登录成功')));
        Navigator.of(context).pop();
        ref.invalidate(apiClientProvider);
        ref.invalidate(authUserProvider);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('登录失败：$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
