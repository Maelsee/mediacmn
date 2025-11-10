import 'package:flutter/material.dart';

class WebDAVConfigPage extends StatefulWidget {
  const WebDAVConfigPage({super.key});

  @override
  State<WebDAVConfigPage> createState() => _WebDAVConfigPageState();
}

class _WebDAVConfigPageState extends State<WebDAVConfigPage> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController(text: '我的 WebDAV');
  final _addressController = TextEditingController();
  final _portController = TextEditingController(text: '80');
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _pathController = TextEditingController();
  
  String _selectedProtocol = 'HTTP';
  bool _isPasswordVisible = false;

  @override
  void dispose() {
    _nameController.dispose();
    _addressController.dispose();
    _portController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    _pathController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('添加 WebDAV'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: '名称',
                hintText: '请输入名称',
                border: OutlineInputBorder(),
              ),
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return '请输入名称';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              value: _selectedProtocol,
              decoration: const InputDecoration(
                labelText: '协议',
                border: OutlineInputBorder(),
              ),
              items: ['HTTP', 'HTTPS']
                  .map((protocol) => DropdownMenuItem(
                        value: protocol,
                        child: Text(protocol),
                      ))
                  .toList(),
              onChanged: (value) {
                setState(() {
                  _selectedProtocol = value!;
                });
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _addressController,
              decoration: const InputDecoration(
                labelText: '地址*',
                hintText: '请输入 IP 或域名',
                border: OutlineInputBorder(),
              ),
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return '请输入地址';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _portController,
              decoration: const InputDecoration(
                labelText: '端口',
                hintText: '端口',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _usernameController,
              decoration: const InputDecoration(
                labelText: '用户名',
                hintText: '选填',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _passwordController,
              decoration: InputDecoration(
                labelText: '密码',
                hintText: '选填',
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: Icon(
                    _isPasswordVisible ? Icons.visibility : Icons.visibility_off,
                  ),
                  onPressed: () {
                    setState(() {
                      _isPasswordVisible = !_isPasswordVisible;
                    });
                  },
                ),
              ),
              obscureText: !_isPasswordVisible,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _pathController,
              decoration: const InputDecoration(
                labelText: '路径',
                hintText: '选填，例如：/dav',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 32),
            ElevatedButton(
              onPressed: _saveConfig,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blue,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
              child: const Text('添加'),
            ),
          ],
        ),
      ),
    );
  }

  void _saveConfig() {
    if (_formKey.currentState!.validate()) {
      // 保存配置逻辑
      final config = {
        'name': _nameController.text,
        'protocol': _selectedProtocol,
        'address': _addressController.text,
        'port': _portController.text,
        'username': _usernameController.text,
        'password': _passwordController.text,
        'path': _pathController.text,
      };
      
      // 这里应该保存配置到数据库或状态管理
      print('保存WebDAV配置: $config');
      
      // 显示成功消息并返回
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('WebDAV配置已保存')),
      );
      
      Navigator.pop(context, config);
    }
  }
}