import 'package:flutter/material.dart';

class LoadingOverlay extends StatelessWidget {
  final double? progress;

  const LoadingOverlay({super.key, this.progress});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black54,
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.black87,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    value: progress != null && progress! > 0 ? progress : null,
                  )),
              const SizedBox(width: 12),
              Text(
                progress != null && progress! > 0
                    ? '加载中 ${(progress! * 100).toInt()}%'
                    : '加载中…',
                style: const TextStyle(color: Colors.white),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
