import 'package:flutter/material.dart';
import 'package:mediaclient/state/auth_scope.dart';

/// 验证码输入页
/// - 展示 6 个等宽验证码框
/// - 显示“重新获取(XXs)”倒计时，结束后可点击重新发送
/// - 输入满 6 位后自动校验；错误则提示
class LoginCodePage extends StatefulWidget {
  const LoginCodePage({super.key});

  @override
  State<LoginCodePage> createState() => _LoginCodePageState();
}

class _LoginCodePageState extends State<LoginCodePage> {
  final _codeController = TextEditingController();
  final _focusNode = FocusNode();

  @override
  void dispose() {
    _codeController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('输入验证码'),
        centerTitle: false,
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('验证码已发送至手机 ${auth.phone}', style: const TextStyle(color: Colors.black54)),
          const SizedBox(height: 16),
          // 手势区域：点击后聚焦隐藏输入框
          GestureDetector(
            onTap: () => _focusNode.requestFocus(),
            child: Column(
              children: [
                _buildCodeBoxes(context),
                // 隐藏的真实输入框
                Opacity(
                  opacity: 0.0,
                  child: TextField(
                    focusNode: _focusNode,
                    controller: _codeController,
                    keyboardType: TextInputType.number,
                    maxLength: 6,
                    autofocus: true,
                    onChanged: (value) async {
                      setState(() {}); // 刷新展示框内容
                      if (value.length == 6) {
                        final ok = await AuthScope.of(context).verifyCode(value);
                        if (mounted) {
                          if (ok) {
                            Navigator.popUntil(context, (route) => route.isFirst);
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('登录成功')),
                            );
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('验证码错误，请重试')),
                            );
                          }
                        }
                      }
                    },
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Center(
            child: TextButton(
              onPressed: auth.resendSeconds == 0
                  ? () {
                      auth.resendCode();
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('已重新发送验证码')),
                      );
                    }
                  : null,
              child: Text(
                auth.resendSeconds == 0 ? '重新获取' : '重新获取 (${auth.resendSeconds}s)',
                style: TextStyle(color: auth.resendSeconds == 0 ? Colors.blue : Colors.grey),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 构建 6 位验证码展示框（从 _codeController.text 读取内容逐格显示）
  Widget _buildCodeBoxes(BuildContext context) {
    final text = _codeController.text.padRight(6);
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: List.generate(6, (i) {
        final char = text.substring(i, i + 1);
        return Container(
          width: 44,
          height: 56,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.grey.shade400),
          ),
          child: Text(
            char.trim().isEmpty ? '' : char,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
        );
      }),
    );
  }
}