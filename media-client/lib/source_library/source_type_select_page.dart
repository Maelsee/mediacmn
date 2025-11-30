import 'package:flutter/material.dart';
// import 'source_webdav_form_page.dart';
import 'package:go_router/go_router.dart';

class SourceTypeSelectPage extends StatelessWidget {
  const SourceTypeSelectPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('添加新文件源')),
      body: ListView(padding: const EdgeInsets.all(12), children: [
        Card(
            child: Column(children: [
          const ListTile(title: Text('本地存储')),
          const Divider(height: 0),
          ListTile(
              leading: const Icon(Icons.folder),
              title: const Text('本地目录'),
              onTap: () {}),
        ])),
        const SizedBox(height: 12),
        Card(
            child: Column(children: [
          const ListTile(title: Text('网络存储')),
          const Divider(height: 0),
          ListTile(
              leading: const Icon(Icons.dns),
              title: const Text('WebDAV'),
              onTap: () {
                GoRouter.of(context).push('/sources/add?type=webdav');
              }),
          ListTile(
              leading: const Icon(Icons.lan),
              title: const Text('SMB'),
              onTap: () {}),
        ])),
        const SizedBox(height: 12),
        Card(
            child: Column(children: [
          const ListTile(title: Text('云盘存储')),
          const Divider(height: 0),
          ListTile(
              leading: const Icon(Icons.cloud),
              title: const Text('阿里云盘'),
              onTap: () {}),
          // const Divider(height: 0),
          ListTile(
              leading: const Icon(Icons.cloud),
              title: const Text('百度网盘'),
              onTap: () {}),
          ListTile(
              leading: const Icon(Icons.cloud),
              title: const Text('115网盘'),
              onTap: () {}),
          ListTile(
              leading: const Icon(Icons.cloud),
              title: const Text('天翼云盘'),
              onTap: () {}),
        ])),
        const SizedBox(height: 12),
        Card(
            child: Column(children: [
          const ListTile(title: Text('媒体服务器')),
          const Divider(height: 0),
          ListTile(
              leading: const Icon(Icons.home_max),
              title: const Text('Emby'),
              onTap: () {}),
        ])),
      ]),
    );
  }
}
