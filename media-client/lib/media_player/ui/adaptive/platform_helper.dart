import 'package:flutter/foundation.dart';

bool isWebPlatform() => kIsWeb;

bool isDesktopPlatform(TargetPlatform platform) {
  switch (platform) {
    case TargetPlatform.windows:
    case TargetPlatform.macOS:
    case TargetPlatform.linux:
      return true;
    default:
      return false;
  }
}

bool isMobilePlatform(TargetPlatform platform) {
  switch (platform) {
    case TargetPlatform.android:
    case TargetPlatform.iOS:
      return true;
    default:
      return false;
  }
}
