import 'package:flutter/material.dart';
import 'package:mediaclient/pages/user/login_code.dart';
import 'package:mediaclient/state/auth_scope.dart';

/// 手机号输入页
/// 逻辑说明：
/// - 输入框仅数字，长度 11；
/// - 勾选协议后方可点击“登录”；
/// - 点击“登录”后调用 AuthController.sendCode 并跳转到验证码页。
class LoginPhonePage extends StatefulWidget {
  const LoginPhonePage({super.key});

  @override
  State<LoginPhonePage> createState() => _LoginPhonePageState();
}

class _LoginPhonePageState extends State<LoginPhonePage> {
  final _phoneController = TextEditingController();
  bool _agreed = false;

  @override
  void dispose() {
    _phoneController.dispose();
    super.dispose();
  }

  bool get _isValidPhone => _phoneController.text.length == 11;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('网易爆米花'),
        centerTitle: true,
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 24),
          // Logo + 标题
          Column(
            children: const [
              Icon(Icons.local_movies, size: 64, color: Colors.orange),
              SizedBox(height: 8),
              Text('网易爆米花', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 32),
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              hintText: '请输入手机号',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 48,
            child: ElevatedButton(
              onPressed: (_agreed && _isValidPhone)
                  ? () {
                      final auth = AuthScope.of(context);
                      auth.sendCode(_phoneController.text);
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const LoginCodePage()),
                      );
                    }
                  : null,
              style: ButtonStyle(
                backgroundColor: MaterialStateProperty.resolveWith<Color?>((states) {
                  if (states.contains(MaterialState.disabled)) {
                    return Colors.grey.shade300; // 未启用为灰色
                  }
                  return Colors.black; // 启用为黑色
                }),
                foregroundColor: MaterialStateProperty.resolveWith<Color?>((states) {
                  return Colors.white;
                }),
              ),
              child: const Text('登录'),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Checkbox(value: _agreed, onChanged: (v) => setState(() => _agreed = v ?? false)),
              const Expanded(
                child: Text(
                  '我已阅读并同意《用户协议》《隐私政策》《儿童个人信息保护规则及监护人须知》和《第三方共享个人信息清单》',
                  style: TextStyle(fontSize: 12),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}