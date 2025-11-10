import 'package:flutter/material.dart';
import 'package:mediaclient/pages/resource_library/resource_library_page.dart';
import 'package:mediaclient/pages/user/user_profile.dart';
import 'package:mediaclient/pages/media_library/media_home.dart';

class App extends StatefulWidget {
  const App({super.key});

  @override
  State<App> createState() => _AppState();
}

class _AppState extends State<App> {
  int _selectedIndex = 0;
  
  // 页面列表
  final List<Widget> _pages = [
    MediaHomePage(),
    ResourceLibraryPage(),
    UserProfilePage(),
  ];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _selectedIndex,
        children: _pages,
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedIndex,
        onTap: _onItemTapped,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: '媒体库',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.settings),
            label: '资源库',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person),
            label: '我的',
          ),
        ],
        selectedItemColor: Colors.blue,
        unselectedItemColor: Colors.grey,
        showUnselectedLabels: true,
      ),
    );
  }

  
}