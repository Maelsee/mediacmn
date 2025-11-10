// 资源类型枚举
import 'package:flutter/material.dart';

enum ResourceType {
  local,      // 本地存储
  webdav,     // WebDAV
  smb,        // SMB
  aliyun,     // 阿里云盘
  baidu,      // 百度网盘
  _115,       // 115网盘
  tianyi,     // 天翼云盘
  mobile,     // 中国移动云盘
  unicom,     // 联通云盘
  _123,       // 123云盘
  emby,       // Emby媒体服务器
}

// 资源项模型
class ResourceItem {
  final String id;
  final String name;
  final ResourceType type;
  final IconData icon;
  final Color color;
  final String size;
  final String status;
  final DateTime addedTime;

  ResourceItem({
    required this.id,
    required this.name,
    required this.type,
    required this.icon,
    required this.color,
    required this.size,
    required this.status,
    DateTime? addedTime,
  }) : addedTime = addedTime ?? DateTime.now();
}

// 存储统计模型
class StorageStats {
  final double total; // GB
  final double used;  // GB
  final double free;  // GB

  StorageStats({
    required this.total,
    required this.used,
    required this.free,
  });

  double get usedPercentage => (used / total) * 100;
}