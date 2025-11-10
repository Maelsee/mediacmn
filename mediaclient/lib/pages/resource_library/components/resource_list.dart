import 'package:flutter/material.dart';
import '../models/resource_model.dart';
import 'storage_stats.dart';

class ResourceList extends StatelessWidget {
  final List<ResourceItem> resources;
  final StorageStats storageStats;
  final VoidCallback onAddResource;
  final Function(String) onDeleteResource;

  const ResourceList({
    super.key,
    required this.resources,
    required this.storageStats,
    required this.onAddResource,
    required this.onDeleteResource,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 存储统计信息（第1张图顶部）
        // StorageStatsWidget(stats: storageStats),

        // 资源列表
        Expanded(
          child: ListView.builder(
            itemCount: resources.length,
            itemBuilder: (context, index) {
              return _buildResourceItem(context, resources[index]);
            },
          ),
        ),

        ],
    );
  }

  Widget _buildResourceItem(BuildContext context, ResourceItem resource) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: ListTile(
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: resource.color.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(resource.icon, color: resource.color),
        ),
        title: Text(
          resource.name,
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 4),
            _buildTypeTag(resource.type),
            const SizedBox(height: 2),
            Text(
              resource.size,
              style: TextStyle(color: Colors.grey[600], fontSize: 12),
            ),
          ],
        ),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: Colors.blue[50],
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: Colors.blue[100]!),
          ),
          child: Text(
            resource.status,
            style: TextStyle(
              color: Colors.blue[700],
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        onLongPress: () {
          _showResourceOptions(context, resource);
        },
      ),
    );
  }

  Widget _buildTypeTag(ResourceType type) {
    String typeText;
    Color color;

    switch (type) {
      case ResourceType.webdav:
        typeText = 'WebDAV';
        color = Colors.orange;
        break;
      case ResourceType.local:
        typeText = '本地';
        color = Colors.blue;
        break;
      default:
        typeText = '其他';
        color = Colors.grey;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        typeText,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  void _showResourceOptions(BuildContext context, ResourceItem resource) {
    showModalBottomSheet(
      context: context,
      builder: (BuildContext context) {
        return SafeArea(
          child: Wrap(
            children: [
              ListTile(
                leading: const Icon(Icons.edit),
                title: const Text('编辑'),
                onTap: () {
                  Navigator.pop(context);
                  // 编辑资源
                },
              ),
              ListTile(
                leading: const Icon(Icons.delete, color: Colors.red),
                title: const Text('删除', style: TextStyle(color: Colors.red)),
                onTap: () {
                  Navigator.pop(context);
                  _showDeleteConfirmation(context, resource);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _showDeleteConfirmation(BuildContext context, ResourceItem resource) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('确认删除'),
          content: Text('确定要删除资源 "${resource.name}" 吗？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                onDeleteResource(resource.id);
              },
              child: const Text('删除', style: TextStyle(color: Colors.red)),
            ),
          ],
        );
      },
    );
  }
}
