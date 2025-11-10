import 'dart:async';
import 'package:flutter/material.dart';

/// 简易认证控制器，模拟短信验证码登录
/// - 发送验证码：sendCode
/// - 校验验证码：verifyCode（示例中 123456 视为正确）
/// - 退出登录：logout
/// - 倒计时：resendSeconds（重新获取按钮显示）
class AuthController extends ChangeNotifier {
  String? _phone; // 登录成功后的手机号
  String? _candidatePhone; // 正在登录流程中的手机号
  int _resendSeconds = 0;
  Timer? _timer;

  bool get isLoggedIn => _phone != null;
  String get phone => _phone ?? _candidatePhone ?? '';
  int get resendSeconds => _resendSeconds;

  /// 将手机号遮掩显示（例如 156******04）
  String get maskedPhone {
    final p = _phone ?? '';
    if (p.length == 11) {
      return '${p.substring(0, 3)}******${p.substring(9)}';
    }
    return p;
  }

  /// 发送验证码（模拟）
  void sendCode(String phone) {
    _candidatePhone = phone;
    _startCountdown(60);
    // 这里可接入后端短信发送接口
    notifyListeners();
  }

  /// 重新发送验证码（模拟）
  void resendCode() {
    if (_candidatePhone != null) {
      _startCountdown(60);
      notifyListeners();
    }
  }

  /// 校验验证码（模拟：输入 123456 视为正确）
  Future<bool> verifyCode(String code) async {
    await Future.delayed(const Duration(milliseconds: 300));
    if (code == '123456' && _candidatePhone != null) {
      _phone = _candidatePhone;
      _candidatePhone = null;
      _stopCountdown();
      notifyListeners();
      return true;
    }
    return false;
  }

  void logout() {
    _phone = null;
    _candidatePhone = null;
    _stopCountdown();
    notifyListeners();
  }

  void _startCountdown(int seconds) {
    _resendSeconds = seconds;
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (_resendSeconds > 0) {
        _resendSeconds--;
        notifyListeners();
      } else {
        t.cancel();
      }
    });
  }

  void _stopCountdown() {
    _resendSeconds = 0;
    _timer?.cancel();
    _timer = null;
  }
}

/// 提供认证状态的 InheritedNotifier 包装，便于在全局访问
class AuthScope extends InheritedNotifier<AuthController> {
  AuthScope({super.key, required Widget child})
      : super(notifier: AuthController(), child: child);

  static AuthController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AuthScope>();
    assert(scope != null, 'AuthScope 未在 Widget 树中提供');
    return scope!.notifier!;
  }

  @override
  bool updateShouldNotify(covariant InheritedNotifier<AuthController> oldWidget) {
    return true;
  }
}