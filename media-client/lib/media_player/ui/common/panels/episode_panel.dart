import 'package:flutter/material.dart';
import '../components/side_panel.dart';

class EpisodePanel extends StatelessWidget {
  final List<Map<String, dynamic>> episodes;
  final int currentEpisodeIndex;
  final Function(int) onEpisodeSelected;
  final VoidCallback onClose;

  const EpisodePanel({
    super.key,
    required this.episodes,
    required this.currentEpisodeIndex,
    required this.onEpisodeSelected,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return SidePanel(
      title: '选集',
      child: episodes.isEmpty
          ? const Center(
              child: Text('暂无剧集信息', style: TextStyle(color: Colors.white70)))
          : ListView.builder(
              padding: const EdgeInsets.all(8),
              itemCount: episodes.length,
              itemBuilder: (context, index) {
                final ep = episodes[index];
                final isCurrent = index == currentEpisodeIndex;
                final title =
                    ep['name'] ?? '第 ${ep['episode_number'] ?? index + 1} 集';

                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    color: isCurrent ? Colors.white24 : Colors.transparent,
                    border: Border.all(
                        color: isCurrent ? Colors.white : Colors.white24),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: ListTile(
                    leading: isCurrent
                        ? const Icon(Icons.play_arrow,
                            color: Colors.white, size: 16)
                        : null,
                    title: Text(title,
                        style: const TextStyle(color: Colors.white)),
                    onTap: () {
                      onEpisodeSelected(index);
                      onClose();
                    },
                  ),
                );
              },
            ),
    );
  }
}
