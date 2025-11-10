import 'package:flutter/material.dart';
import 'webdav_config_page.dart';

class AddResourcePage extends StatelessWidget {
  const AddResourcePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('添加新文件源')),
      body: ListView(
        children: [
          _buildSectionHeader('本地存储'),
          _buildResourceTypeItem(
            context,
            icon: Icons.folder,
            title: '本地目录',
            subtitle: '添加本地文件夹',
            onTap: () {
              _addLocalDirectory(context);
            },
          ),

          _buildSectionHeader('网络存储'),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud,
            title: 'WebDAV',
            subtitle: 'DAV',
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const WebDAVConfigPage(),
                ),
              );
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.storage,
            title: 'SMB',
            subtitle: 'SMB',
            onTap: () {
              _addSMBResource(context);
            },
          ),

          _buildSectionHeader('云盘存储'),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '阿里云盘',
            onTap: () {
              _addAliyunResource(context);
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '百度网盘',
            onTap: () {
              _addBaiduResource(context);
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '115网盘',
            onTap: () {
              _add115Resource(context);
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '天翼云盘',
            onTap: () {
              _addTianyiResource(context);
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '中国移动云盘',
            onTap: () {
              _addMobileResource(context);
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '联通云盘',
            trailing: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.red,
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Text(
                'New',
                style: TextStyle(color: Colors.white, fontSize: 10),
              ),
            ),
            onTap: () {
              _addUnicomResource(context);
            },
          ),
          _buildResourceTypeItem(
            context,
            icon: Icons.cloud_queue,
            title: '123云盘',
            onTap: () {
              _add123Resource(context);
            },
          ),

          _buildSectionHeader('媒体服务器'),
          _buildResourceTypeItem(
            context,
            icon: Icons.ondemand_video,
            title: 'Emby',
            onTap: () {
              _addEmbyResource(context);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.bold,
          color: Colors.grey,
        ),
      ),
    );
  }

  Widget _buildResourceTypeItem(
    BuildContext context, {
    required IconData icon,
    required String title,
    String? subtitle,
    Widget? trailing,
    required VoidCallback onTap,
  }) {
    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: Colors.blue.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(icon, color: Colors.blue),
      ),
      title: Text(title),
      subtitle: subtitle != null ? Text(subtitle) : null,
      trailing: trailing ?? const Icon(Icons.arrow_forward_ios, size: 16),
      onTap: onTap,
    );
  }

  // 各种资源添加方法
  void _addLocalDirectory(BuildContext context) {
    // 实现本地目录添加逻辑
    _showNotImplementedSnackbar(context, '本地目录');
  }

  void _addSMBResource(BuildContext context) {
    _showNotImplementedSnackbar(context, 'SMB');
  }

  void _addAliyunResource(BuildContext context) {
    _showNotImplementedSnackbar(context, '阿里云盘');
  }

  void _addBaiduResource(BuildContext context) {
    _showNotImplementedSnackbar(context, '百度网盘');
  }

  void _add115Resource(BuildContext context) {
    _showNotImplementedSnackbar(context, '115网盘');
  }

  void _addTianyiResource(BuildContext context) {
    _showNotImplementedSnackbar(context, '天翼云盘');
  }

  void _addMobileResource(BuildContext context) {
    _showNotImplementedSnackbar(context, '中国移动云盘');
  }

  void _addUnicomResource(BuildContext context) {
    _showNotImplementedSnackbar(context, '联通云盘');
  }

  void _add123Resource(BuildContext context) {
    _showNotImplementedSnackbar(context, '123云盘');
  }

  void _addEmbyResource(BuildContext context) {
    _showNotImplementedSnackbar(context, 'Emby');
  }

  void _showNotImplementedSnackbar(BuildContext context, String feature) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text('$feature 功能开发中...')));
  }
}
