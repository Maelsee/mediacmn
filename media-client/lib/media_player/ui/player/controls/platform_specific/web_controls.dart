import 'package:flutter/material.dart';

import '../../../../core/state/playback_state.dart';

class WebPlayerControls extends StatefulWidget {
  final PlaybackState state;
  final Widget common;

  const WebPlayerControls({
    super.key,
    required this.state,
    required this.common,
  });

  @override
  State<WebPlayerControls> createState() => _WebPlayerControlsState();
}

class _WebPlayerControlsState extends State<WebPlayerControls> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final show = _hover;
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: Stack(
        children: [
          if (show)
            Positioned(
              right: 12,
              top: 12,
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).maybePop(),
                    icon: const Icon(Icons.close, color: Colors.white),
                  ),
                ],
              ),
            ),
          if (show)
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: widget.common,
            ),
        ],
      ),
    );
  }
}
