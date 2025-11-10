import 'package:flutter/material.dart';

class MediaHomePage extends StatefulWidget {
  const MediaHomePage({super.key});

  @override
  State<MediaHomePage> createState() => _MediaHomePageState();
}

class _MediaHomePageState extends State<MediaHomePage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('无敌影视')),
      body: Center(
        child: Text(
          '媒体库页面',
          style: TextStyle(color: const Color.fromARGB(255, 85, 19, 19)),
        ),
      ),
    );
  }
}
