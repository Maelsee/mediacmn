import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// import 'source_type_select_page.dart';
import 'package:go_router/go_router.dart';
import 'sources_provider.dart';
import 'source_models.dart';
import '../core/api_client.dart';

class SourcesHomePage extends ConsumerWidget {
  const SourcesHomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(sourcesProvider);
    final ready = ref.watch(libraryReadyProvider);
    return Scaffold(
      appBar: !ready
          ? null
          : AppBar(
              title: const Text('资源库'),
              actions: [
                IconButton(
                  onPressed: () => ref.read(sourcesProvider.notifier).load(),
                  icon: const Icon(Icons.refresh),
                ),
                IconButton(
                  onPressed: () {
                    GoRouter.of(context).push('/sources/add');
                  },
                  icon: const Icon(Icons.add),
                ),
              ],
            ),
      body: s.loading
          ? const Center(child: CircularProgressIndicator())
          : (!ready
              ? _emptyState(context)
              : ListView(
                  padding: const EdgeInsets.all(12),
                  children: [
                    if (s.items.any((it) => it.type == 'local')) ...[
                      const ListTile(title: Text('本地')),
                      ...s.items
                          .where((it) => it.type == 'local')
                          .map((it) => _SourceCard(item: it, ref: ref)),
                      const SizedBox(height: 8),
                    ],
                    if (s.items.any((it) => it.type == 'webdav')) ...[
                      const ListTile(title: Text('WebDAV')),
                      ...s.items
                          .where((it) => it.type == 'webdav')
                          .map((it) => _SourceCard(item: it, ref: ref)),
                      const SizedBox(height: 8),
                    ],
                    if (s.items.any((it) => it.type == 'smb')) ...[
                      const ListTile(title: Text('SMB')),
                      ...s.items
                          .where((it) => it.type == 'smb')
                          .map((it) => _SourceCard(item: it, ref: ref)),
                      const SizedBox(height: 8),
                    ],
                    if (s.items.any((it) => it.type == 'cloud')) ...[
                      const ListTile(title: Text('云盘')),
                      ...s.items
                          .where((it) => it.type == 'cloud')
                          .map((it) => _SourceCard(item: it, ref: ref)),
                    ],
                  ],
                )),
    );
  }

  Widget _emptyState(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.play_circle_outline,
              size: 72,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 16),
            const Text(
              '还没有资源哦',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            const Text('添加视频资源后即可打造私人影视库，随时随地观看', textAlign: TextAlign.center),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: () {
                GoRouter.of(context).push('/sources/add');
              },
              child: const Text('添加资源'),
            ),
          ],
        ),
      ),
    );
  }
}

class _SourceCard extends StatelessWidget {
  final SourceItem item;
  final WidgetRef ref;
  const _SourceCard({required this.item, required this.ref});

  IconData _iconForType(String t) {
    switch (t) {
      case 'webdav':
        return Icons.dns;
      case 'local':
        return Icons.folder;
      case 'smb':
        return Icons.lan;
      case 'cloud':
        return Icons.cloud;
      default:
        return Icons.storage;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: Icon(_iconForType(item.type)),
        title: Row(
          children: [
            Expanded(child: Text(item.name)),
            Builder(
              builder: (context) {
                final st = item.status.toLowerCase();
                final connected = st == 'connected';
                return connected
                    ? const Icon(Icons.link, color: Colors.green)
                    : const Icon(Icons.link_off, color: Colors.orange);
              },
            ),
          ],
        ),
        onTap: () {
          final id = int.tryParse(item.id) ?? 0;
          GoRouter.of(
            context,
          ).push('/sources/browse/$id?title=${Uri.encodeComponent(item.name)}');
        },
        trailing: IconButton(
          icon: const Icon(Icons.more_vert),
          onPressed: () => _showBottomSheet(context),
        ),
      ),
    );
  }

  void _showBottomSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => _buildBottomSheetMenu(context),
    );
  }

  Widget _buildBottomSheetMenu(BuildContext context) {
    final id = int.tryParse(item.id) ?? 0;
    return Container(
      height: MediaQuery.of(context).size.height / 3,
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Column(
        children: [
          Expanded(
            child: ListView(
              children: [
                ListTile(
                  leading: const Icon(Icons.refresh),
                  title: const Text('手动扫描'),
                  onTap: () async {
                    Navigator.pop(context);
                    final api = ref.read(apiClientProvider);
                    final messenger = ScaffoldMessenger.of(context);
                    try {
                      await api.startScan(storageId: id);
                      messenger.showSnackBar(
                        const SnackBar(content: Text('扫描任务已开始')),
                      );
                    } catch (e) {
                      messenger.showSnackBar(
                        SnackBar(content: Text('扫描失败: $e')),
                      );
                    }
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.edit),
                  title: const Text('编辑'),
                  onTap: () async {
                    Navigator.pop(context);
                    final router = GoRouter.of(context);
                    if (item.type == 'webdav') {
                      Map<String, dynamic> detail = {'name': item.name};
                      try {
                        detail = await ref
                            .read(sourcesProvider.notifier)
                            .getDetail(item.id);
                      } catch (_) {}
                      final Map<String, String> params = {
                        'type': 'webdav',
                        'name': (detail['name'] as String?) ?? item.name,
                        if ((detail['hostname'] as String?)?.isNotEmpty == true)
                          'hostname': detail['hostname'] as String,
                        if ((detail['login'] as String?)?.isNotEmpty == true)
                          'login': detail['login'] as String,
                        if ((detail['root_path'] as String?)?.isNotEmpty ==
                            true)
                          'root_path': detail['root_path'] as String,
                      };
                      final uri = Uri(
                        path: '/sources/${item.id}/edit',
                        queryParameters: params,
                      );
                      final changed = await router.push(uri.toString());
                      if (changed == true) {
                        await ref.read(sourcesProvider.notifier).load();
                      }
                    } else {
                      final changed = await router.push(
                        '/sources/${item.id}/edit',
                      );
                      if (changed == true) {
                        await ref.read(sourcesProvider.notifier).load();
                      }
                    }
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.power_settings_new),
                  title: const Text('停用/启用'),
                  onTap: () async {
                    Navigator.pop(context);
                    showDialog(
                      context: context,
                      builder: (ctx) => SimpleDialog(
                        title: const Text('选择操作'),
                        children: [
                          SimpleDialogOption(
                            child: const Text('启用'),
                            onPressed: () async {
                              Navigator.pop(ctx);
                              await ref
                                  .read(apiClientProvider)
                                  .enableStorage(id);
                              ref.read(sourcesProvider.notifier).load();
                            },
                          ),
                          SimpleDialogOption(
                            child: const Text('停用'),
                            onPressed: () async {
                              Navigator.pop(ctx);
                              await ref
                                  .read(apiClientProvider)
                                  .disableStorage(id);
                              ref.read(sourcesProvider.notifier).load();
                            },
                          ),
                        ],
                      ),
                    );
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.delete, color: Colors.red),
                  title: const Text('删除', style: TextStyle(color: Colors.red)),
                  onTap: () async {
                    Navigator.pop(context);
                    await ref.read(apiClientProvider).deleteSource(item.id);
                    await ref.read(sourcesProvider.notifier).load();
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.link),
                  title: const Text('测试连接'),
                  onTap: () async {
                    Navigator.pop(context);
                    final ok =
                        await ref.read(apiClientProvider).testConnection(id);
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text(ok ? '连接正常' : '连接失败')),
                      );
                    }
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
