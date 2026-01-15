#!/bin/bash

# 定义源目录和目标目录
SOURCE_DIR="/home/meal/mediacmn/media-client"
TARGET_DIR="/mnt/d/FlutterApp/test"

# 确保目标目录存在
mkdir -p "$TARGET_DIR"

echo "开始同步文件到 Windows..."

# 同步 lib 目录
# -a: 归档模式，保留权限和时间戳
# -v: 详细输出
# -z: 压缩传输
# --delete: 删除目标目录中源目录不存在的文件
rsync -avz --delete "$SOURCE_DIR/lib/" "$TARGET_DIR/lib/"
# rsync -avz --delete "$SOURCE_DIR/windows/" "$TARGET_DIR/windows/"

# 同步 pubspec.yaml
# rsync -avz "$SOURCE_DIR/pubspec.yaml" "$TARGET_DIR/pubspec.yaml"

echo "同步完成！"
