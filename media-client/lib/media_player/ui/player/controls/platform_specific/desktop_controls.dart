import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/state/playback_state.dart';

class DesktopPlayerControls extends StatelessWidget {
  final PlaybackState state;
  final Widget common;
  final VoidCallback onPlayPause;
  final VoidCallback onSeekBackward;
  final VoidCallback onSeekForward;

  const DesktopPlayerControls({
    super.key,
    required this.state,
    required this.common,
    required this.onPlayPause,
    required this.onSeekBackward,
    required this.onSeekForward,
  });

  @override
  Widget build(BuildContext context) {
    return DesktopShortcutListener(
      onPlayPause: onPlayPause,
      onSeekBackward: onSeekBackward,
      onSeekForward: onSeekForward,
      child: Stack(
        children: [
          Positioned(
            left: 12,
            right: 12,
            top: 12,
            child: Row(
              children: [
                Text(
                  state.title ?? '',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                IconButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  icon: const Icon(Icons.close, color: Colors.white),
                ),
              ],
            ),
          ),
          Positioned(left: 0, right: 0, bottom: 0, child: common),
        ],
      ),
    );
  }
}

class DesktopShortcutListener extends StatelessWidget {
  final Widget child;
  final VoidCallback onPlayPause;
  final VoidCallback onSeekBackward;
  final VoidCallback onSeekForward;

  const DesktopShortcutListener({
    super.key,
    required this.child,
    required this.onPlayPause,
    required this.onSeekBackward,
    required this.onSeekForward,
  });

  @override
  Widget build(BuildContext context) {
    return Shortcuts(
      shortcuts: {
        LogicalKeySet(LogicalKeyboardKey.space): const ActivateIntent(),
        LogicalKeySet(LogicalKeyboardKey.arrowLeft): const _SeekIntent(
          backward: true,
        ),
        LogicalKeySet(LogicalKeyboardKey.arrowRight): const _SeekIntent(
          backward: false,
        ),
      },
      child: Actions(
        actions: {
          ActivateIntent: CallbackAction<ActivateIntent>(
            onInvoke: (_) {
              onPlayPause();
              return null;
            },
          ),
          _SeekIntent: CallbackAction<_SeekIntent>(
            onInvoke: (intent) {
              if (intent.backward) {
                onSeekBackward();
              } else {
                onSeekForward();
              }
              return null;
            },
          ),
        },
        child: Focus(autofocus: true, child: child),
      ),
    );
  }
}

class _SeekIntent extends Intent {
  final bool backward;
  const _SeekIntent({required this.backward});
}
