import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'media_provider.dart';
import 'media_models.dart';
import 'package:go_router/go_router.dart';

class GenresPage extends ConsumerWidget {
  const GenresPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final m = ref.watch(mediaHomeProvider);
    final cats = m.data?.genres ?? const <HomeCardGenre>[];
    return Scaffold(
      appBar: AppBar(
        title: const Text('类型'),
        // backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: GridView.builder(
        padding: const EdgeInsets.all(12),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 2.8,
        ),
        itemCount: cats.length,
        itemBuilder: (ctx, i) {
          final c = cats[i];
          return GestureDetector(
            onTap: () {
              GoRouter.of(context).push(
                '/media/cards?title=${Uri.encodeComponent(c.name)}&genres=${Uri.encodeComponent(c.name)}',
              );
            },
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                gradient: LinearGradient(
                  colors: [
                    Colors.primaries[i % Colors.primaries.length].shade300,
                    Colors
                        .primaries[(i + 2) % Colors.primaries.length].shade200,
                  ],
                ),
              ),
              padding: const EdgeInsets.all(16),
              alignment: Alignment.centerLeft,
              child: Text(
                c.name,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
          );
        },
      ),
    );
  }
}
