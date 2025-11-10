import 'package:flutter/material.dart';
import 'package:mediaclient/app.dart';
import 'package:mediaclient/state/auth_scope.dart';


void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  // This widget is the root of your application.
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
      ),
      // 提供全局认证状态
      home: AuthScope(child: App()),
      
    );
  }
}
