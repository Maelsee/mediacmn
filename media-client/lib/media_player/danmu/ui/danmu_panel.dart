import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../provider/danmu_provider.dart';
import '../models/danmu_models.dart';
import 'danmu_search_page.dart';
import 'danmu_settings_panel.dart';

class DanmuPanel extends ConsumerWidget {
  final String fileId;

  const DanmuPanel({super.key, required this.fileId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(danmuProvider(fileId));
    final notifier = ref.read(danmuProvider(fileId).notifier);

    return Container(
      color: const Color(0xFF1E1E1E),
      child: Column(
        children: [
          // ---- 开关 + 设置按钮 ----
          _buildToggleRow(context, state, notifier),

          const Divider(color: Colors.white12),

          // ---- 匹配来源列表 ----
          if (state.loading)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else if (state.sources.isNotEmpty || state.manualSource != null)
            Expanded(child: _buildSourceList(state, notifier))
          else
            const Expanded(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('未找到匹配弹幕', style: TextStyle(color: Colors.white54)),
              ),
            ),

          // ---- 状态信息 ----
          if (state.danmuData != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text(
                '已加载 ${state.totalDanmuCount} 条弹幕',
                style: const TextStyle(color: Colors.white54, fontSize: 12),
              ),
            ),

          // ---- 手动搜索按钮 ----
          ListTile(
            leading: const Icon(Icons.search, color: Colors.white70),
            title: const Text('手动搜索', style: TextStyle(color: Colors.white70)),
            onTap: () => _openSearchPage(context),
          ),
        ],
      ),
    );
  }

  Widget _buildToggleRow(
      BuildContext context, DanmuState state, DanmuNotifier notifier) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          const Text('显示弹幕',
              style: TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          Switch(
            value: state.enabled,
            activeThumbColor: const Color(0xFFFFE796),
            onChanged: (_) => notifier.toggle(),
          ),
          const SizedBox(width: 4),
          IconButton(
            icon: const Icon(Icons.settings, color: Colors.white54, size: 20),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
            onPressed: () => _openSettingsPanel(context),
          ),
        ],
      ),
    );
  }

  Widget _buildSourceList(DanmuState state, DanmuNotifier notifier) {
    // 合并自动匹配源 + 手动源
    final allSources = <DanmuSource>[
      ...state.sources,
      if (state.manualSource != null &&
          !state.sources
              .any((s) => s.episodeId == state.manualSource!.episodeId))
        state.manualSource!,
    ];

    return ListView.builder(
      itemCount: allSources.length,
      itemBuilder: (context, index) {
        final source = allSources[index];
        final isSelected = source.episodeId == state.selectedSource?.episodeId;
        final isManual = state.manualSource != null &&
            source.episodeId == state.manualSource!.episodeId;
        return GestureDetector(
          onTap: () => notifier.selectSource(source),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF666666).withAlpha(76),
              borderRadius: BorderRadius.circular(12),
              border: isSelected
                  ? Border.all(color: const Color(0xFFFFE796), width: 1.5)
                  : null,
            ),
            child: Row(
              children: [
                if (source.imageUrl.isNotEmpty)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: Image.network(source.imageUrl,
                        width: 48,
                        height: 36,
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) =>
                            const SizedBox(width: 48, height: 36)),
                  ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          if (isManual)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 4, vertical: 1),
                              margin: const EdgeInsets.only(right: 6),
                              decoration: BoxDecoration(
                                color: const Color(0xFF4FC3F7).withAlpha(51),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text('手动',
                                  style: TextStyle(
                                      color: Color(0xFF4FC3F7), fontSize: 10)),
                            ),
                          Expanded(
                            child: Text(
                              source.animeTitle,
                              style: TextStyle(
                                color: isSelected
                                    ? const Color(0xFFFFE796)
                                    : Colors.white,
                                fontSize: 14,
                                fontWeight:
                                    isSelected ? FontWeight.bold : null,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${source.episodeTitle}  ${source.typeDescription}',
                        style: const TextStyle(
                            color: Colors.white54, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _openSearchPage(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => DanmuSearchPage(fileId: fileId),
    ));
  }

  void _openSettingsPanel(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => DanmuSettingsPanel(fileId: fileId),
    );
  }
}
