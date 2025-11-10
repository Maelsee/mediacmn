import 'package:flutter/material.dart';
import 'package:mediaclient/pages/user/login_phone.dart';
import 'package:mediaclient/state/auth_scope.dart';

/// 用户页面（“我的”）
/// 根据登录状态显示：
/// - 未登录：展示登录提示卡片 + 功能入口列表
/// - 已登录：展示头像和遮掩后的手机号 + 功能入口列表 + 退出登录
class UserProfilePage extends StatefulWidget {
  const UserProfilePage({super.key});

  @override
  State<UserProfilePage> createState() => _UserProfilePageState();
}

class _UserProfilePageState extends State<UserProfilePage> {
  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('我的'),
      ),
      body: auth.isLoggedIn ? _buildLoggedIn(context) : _buildLoggedOut(context),
    );
  }

  /// 未登录页：顶部卡片提示 + 登录按钮
  Widget _buildLoggedOut(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          elevation: 0,
          color: Colors.grey.withOpacity(0.08),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    // 简洁头像占位
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.15),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.person, color: Colors.blue, size: 32),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Text(
                        '跨设备同步影片和播放记录\n畅享 Android TV、Apple TV、Mac 大屏播放',
                        style: TextStyle(fontSize: 14, color: Colors.black87),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () {
                      // 跳转到手机号输入页
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const LoginPhonePage()),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.black,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text('登录'),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        ..._commonItems(context),
      ],
    );
  }

  /// 已登录页：显示遮掩后的手机号与功能入口
  Widget _buildLoggedIn(BuildContext context) {
    final auth = AuthScope.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Column(
          children: [
            // 头像圆形背景
            Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [Colors.blue.shade300, Colors.purple.shade300],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.emoji_emotions, color: Colors.white, size: 48),
            ),
            const SizedBox(height: 12),
            Text(
              auth.maskedPhone,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        const SizedBox(height: 24),
        ..._commonItems(context),
        const SizedBox(height: 12),
        ListTile(
          leading: const Icon(Icons.power_settings_new, color: Colors.red),
          title: const Text('退出登录'),
          trailing: const Icon(Icons.arrow_forward_ios, size: 16),
          onTap: () {
            final auth = AuthScope.of(context);
            auth.logout();
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('已退出登录')),
            );
          },
        ),
      ],
    );
  }

  /// 公共功能入口列表
  List<Widget> _commonItems(BuildContext context) {
    return [
      ListTile(
        leading: const Icon(Icons.card_giftcard),
        title: const Text('网盘联合福利'),
        trailing: const Icon(Icons.arrow_forward_ios, size: 16),
        onTap: () {},
      ),
      ListTile(
        leading: const Icon(Icons.settings),
        title: const Text('设置'),
        trailing: const Icon(Icons.arrow_forward_ios, size: 16),
        onTap: () {},
      ),
      ListTile(
        leading: const Icon(Icons.help_outline),
        title: const Text('帮助与反馈'),
        trailing: const Icon(Icons.arrow_forward_ios, size: 16),
        onTap: () {},
      ),
      ListTile(
        leading: const Icon(Icons.chat_bubble_outline),
        title: const Text('联系方式'),
        trailing: const Icon(Icons.arrow_forward_ios, size: 16),
        onTap: () {},
      ),
      ListTile(
        leading: const Icon(Icons.info_outline),
        title: const Text('关于'),
        trailing: const Icon(Icons.arrow_forward_ios, size: 16),
        onTap: () {},
      ),
    ];
  }
}
