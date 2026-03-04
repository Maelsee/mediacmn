import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../core/api_client.dart';

class StorageBrowserPage extends ConsumerStatefulWidget {
  final int storageId;
  final String path;
  final String? title;

  const StorageBrowserPage({
    super.key,
    required this.storageId,
    this.path = '/',
    this.title,
  });

  @override
  ConsumerState<StorageBrowserPage> createState() => _StorageBrowserPageState();
}

class _StorageBrowserPageState extends ConsumerState<StorageBrowserPage> {
  List<Map<String, dynamic>> _entries = [];
  bool _loading = true;
  String? _error;
  final Set<String> _selectedPaths = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final list = await api.listOnlyDirectory(widget.storageId, widget.path);
      setState(() {
        _entries = list;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _scanSelected() async {
    if (_selectedPaths.isEmpty) return;

    try {
      final api = ref.read(apiClientProvider);

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('扫描任务提交中...')));

      await api.startScan(
        storageId: widget.storageId,
        scanPath: _selectedPaths.toList(),
      );

      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('扫描任务已提交')));
        setState(() {
          _selectedPaths.clear();
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('扫描失败: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title ?? '浏览文件夹')),
      body: _buildBody(),
      floatingActionButton: _selectedPaths.isNotEmpty
          ? FloatingActionButton.extended(
              onPressed: _scanSelected,
              label: Text('扫描选定 (${_selectedPaths.length})'),
              icon: const Icon(Icons.search),
            )
          : null,
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('加载失败: $_error'),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _load, child: const Text('重试')),
          ],
        ),
      );
    }

    if (_entries.isEmpty) {
      return const Center(child: Text('此文件夹为空'));
    }

    return ListView.builder(
      itemCount: _entries.length,
      itemBuilder: (context, index) {
        final item = _entries[index];
        final name = item['name'] as String;
        final fullPath = item['path'] as String;
        final isDir = item['is_dir'] as bool? ?? false;

        final isSelected = _selectedPaths.contains(fullPath);

        return ListTile(
          leading: isDir
              ? const Icon(Icons.folder, color: Colors.amber)
              : const Icon(Icons.insert_drive_file),
          title: Text(name),
          subtitle: Text(fullPath),
          trailing: Checkbox(
            value: isSelected,
            onChanged: (val) {
              setState(() {
                if (val == true) {
                  _selectedPaths.add(fullPath);
                } else {
                  _selectedPaths.remove(fullPath);
                }
              });
            },
          ),
          onTap: () {
            context.push(
              Uri(
                path: '/sources/browse/${widget.storageId}',
                queryParameters: {'path': fullPath, 'title': name},
              ).toString(),
            );
          },
        );
      },
    );
  }
}
