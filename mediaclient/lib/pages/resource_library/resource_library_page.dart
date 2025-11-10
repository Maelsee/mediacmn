import 'package:flutter/material.dart';
import 'package:mediaclient/pages/resource_library/add_resource/add_resource_page.dart';
import 'components/empty_state.dart';
import 'components/resource_list.dart';
import 'models/resource_model.dart';

class ResourceLibraryPage extends StatefulWidget {
  const ResourceLibraryPage({super.key});

  @override
  State<ResourceLibraryPage> createState() => _ResourceLibraryPageState();
}

class _ResourceLibraryPageState extends State<ResourceLibraryPage> {
  // 模拟数据 - 实际应该从数据库或API获取
  List<ResourceItem> _resources = [];
  bool get _hasResources => _resources.isNotEmpty;

  // 存储统计
  final StorageStats _storageStats = StorageStats(
    total: 18.95, // GB
    used: 13.95, // GB
    free: 5.0, // GB
  );

  @override
  void initState() {
    super.initState();
    _loadResources();
  }

  void _loadResources() {
    // 模拟加载资源数据
    // 实际应该从数据库或网络加载
    setState(() {
      _resources = [
        ResourceItem(
          id: '1',
          name: '本地下载',
          type: ResourceType.local,
          icon: Icons.download,
          color: Colors.blue,
          size: '18.95G',
          status: '5G',
          addedTime: DateTime.now().subtract(const Duration(days: 2)),
        ),
        ResourceItem(
          id: '2',
          name: 'quark302',
          type: ResourceType.webdav,
          icon: Icons.cloud,
          color: Colors.orange,
          size: 'WebDAV',
          status: 'DAV',
          addedTime: DateTime.now().subtract(const Duration(days: 1)),
        ),
      ];
    });
  }

  void _addResource() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => const AddResourcePage()),
    ).then((newResource) {
      if (newResource != null) {
        // 添加新资源后刷新列表
        _loadResources();
      }
    });
  }

  void _deleteResource(String resourceId) {
    setState(() {
      _resources.removeWhere((resource) => resource.id == resourceId);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('资源库'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          // 只在有资源时显示下载图标
          if (_hasResources) ...[
            IconButton(
              icon: const Icon(Icons.download, color: Colors.blue),
              onPressed: () {
                // 下载功能
              },
            ),
          ],
          IconButton(
            icon: const Icon(Icons.add, color: Colors.blue),
            onPressed: _addResource,
          ),
        ],
      ),
      body: _hasResources
          ? ResourceList(
              resources: _resources,
              storageStats: _storageStats,
              onAddResource: _addResource,
              onDeleteResource: _deleteResource,
            )
          : EmptyResourceState(onAddResource: _addResource),
    );
  }
}
