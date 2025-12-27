import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../logic/player_notifier.dart';

class LoadingLayer extends ConsumerWidget {
  const LoadingLayer({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final buffering = ref.watch(playerProvider.select((s) => s.buffering));

    if (!buffering) return const SizedBox.shrink();

    return const Center(
      child: CircularProgressIndicator(
        color: Colors.white,
      ),
    );
  }
}
