import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_client/core/api_client.dart';
import 'package:media_client/core/playback_history/providers.dart';
import 'package:media_client/media_library/recent_provider.dart';

class ProfileHomePage extends ConsumerWidget {
  const ProfileHomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(backgroundColor: Colors.transparent, elevation: 0),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Consumer(
            builder: (context, ref, _) {
              final auth = ref.watch(authUserProvider);
              return auth.when(
                loading: () => Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: const [
                        CircleAvatar(
                          radius: 28,
                          child: Icon(Icons.person_outline),
                        ),
                        SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('加载中…'),
                              SizedBox(height: 4),
                              Text('正在获取用户信息', style: TextStyle(fontSize: 12)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                error: (_, __) => Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        const CircleAvatar(
                          radius: 28,
                          child: Icon(Icons.person_outline),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('未登录'),
                              SizedBox(height: 4),
                              Text(
                                '登录后可同步进度与偏好',
                                style: TextStyle(fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: () =>
                              GoRouter.of(context).push('/profile/login'),
                          child: const Text('登录'),
                        ),
                      ],
                    ),
                  ),
                ),
                data: (user) {
                  if (user == null) {
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          children: [
                            const CircleAvatar(
                              radius: 28,
                              child: Icon(Icons.person_outline),
                            ),
                            const SizedBox(width: 12),
                            const Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('未登录'),
                                  SizedBox(height: 4),
                                  Text(
                                    '登录后可同步进度与偏好',
                                    style: TextStyle(fontSize: 12),
                                  ),
                                ],
                              ),
                            ),
                            TextButton(
                              onPressed: () =>
                                  GoRouter.of(context).push('/profile/login'),
                              child: const Text('登录'),
                            ),
                          ],
                        ),
                      ),
                    );
                  }
                  final email = user['email'] as String?;
                  final masked = _maskAccount(email);
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Column(
                        children: [
                          const SizedBox(height: 24),

                          const CircleAvatar(
                            radius: 36,
                            child: Icon(Icons.person_outline, size: 28),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            masked ?? '已登录',
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          const SizedBox(height: 4),
                          // const Text('欢迎回来', style: TextStyle(fontSize: 12)),
                          // const SizedBox(height: 12),
                        ],
                      ),
                    ),
                  );
                },
              );
            },
          ),
          const SizedBox(height: 12),
          Card(
            child: Column(
              children: [
                // const ListTile(leading: Icon(Icons.card_giftcard_outlined), title: Text('网盘联合福利'), trailing: Icon(Icons.chevron_right)),
                // const Divider(height: 0),
                ListTile(
                  leading: const Icon(Icons.settings_outlined),
                  title: const Text('设置'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    GoRouter.of(context).push('/profile/settings');
                  },
                ),
                const Divider(height: 0),
                const ListTile(
                  leading: Icon(Icons.chat_bubble_outline),
                  title: Text('帮助与反馈'),
                  trailing: Icon(Icons.chevron_right),
                ),
                const Divider(height: 0),
                const ListTile(
                  leading: Icon(Icons.info_outline),
                  title: Text('关于'),
                  trailing: Icon(Icons.chevron_right),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Consumer(
            builder: (context, ref, _) {
              final auth = ref.watch(authUserProvider);
              final api = ref.watch(apiClientProvider);
              return auth.when(
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
                data: (user) {
                  if (user == null) return const SizedBox.shrink();
                  return Card(
                    child: ListTile(
                      leading: const Icon(Icons.logout),
                      title: const Text('退出登录'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () async {
                        await api.logout();
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(
                          context,
                        ).showSnackBar(const SnackBar(content: Text('已退出登录')));
                        ref.invalidate(apiClientProvider);
                        ref.invalidate(authUserProvider);
                        ref.invalidate(localPlaybackStoreProvider);
                        ref.invalidate(playbackProgressRepositoryProvider);
                        ref.invalidate(recentRepositoryProvider);
                        ref.invalidate(recentProvider);
                      },
                    ),
                  );
                },
              );
            },
          ),
        ],
      ),
    );
  }

  String? _maskAccount(String? email) {
    if (email == null || email.isEmpty) return null;
    final parts = email.split('@');
    final name = parts.first;
    if (RegExp(r'^\d{11}$').hasMatch(name)) {
      return '${name.substring(0, 3)}******${name.substring(9)}';
    }
    if (name.length <= 3) {
      return '${name[0]}***${name.substring(name.length - 1)}';
    }
    return '${name.substring(0, 3)}***${name.substring(name.length - 1)}';
  }
}
