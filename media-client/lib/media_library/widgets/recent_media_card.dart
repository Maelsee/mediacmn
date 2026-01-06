import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../media_models.dart';
import '../../core/config.dart';

class RecentMediaCard extends StatelessWidget {
  final RecentCardItem item;
  final VoidCallback? onPlayReturn;

  const RecentMediaCard({super.key, required this.item, this.onPlayReturn});

  String _formatDuration(int ms) {
    final s = ms ~/ 1000;
    final m = s ~/ 60;
    final sec = s % 60;
    return '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    // 封面图
    String? imageUrl = item.coverUrl;

    // 标题处理
    String displayTitle = item.name;

    final progressText = (item.positionMs != null && item.durationMs != null)
        ? '${_formatDuration(item.positionMs!)} / ${_formatDuration(item.durationMs!)}'
        : null;

    final hasProgress = (item.positionMs != null &&
        item.durationMs != null &&
        item.durationMs! > 0);
    final progressValue =
        hasProgress ? (item.positionMs! / item.durationMs!) : 0.0;

    return GestureDetector(
      onTap: () async {
        await GoRouter.of(context).push('/player/${item.id}', extra: {
          'fileId': item.fileId,
          'detail': {
            'id': item.id,
            'media_type': item.mediaType,
            'name': item.name,
            'poster_path': item.coverUrl,
          },
          'asset': null,
          'candidates': const <dynamic>[],
          'start': item.positionMs, // 传递播放进度
        });
        if (onPlayReturn != null) {
          onPlayReturn!();
        }
      },
      child: SizedBox(
        width: 240, // 调整为更小的宽度 (280 -> 240)
        // margin: const EdgeInsets.only(right: 12), // 移除内部 Margin，由父级布局控制间距
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 封面区域 (16:9)
            AspectRatio(
              aspectRatio: 16 / 9,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (imageUrl != null)
                      Image.network(
                        (imageUrl.startsWith('http://') ||
                                imageUrl.startsWith('https://'))
                            ? imageUrl
                            : '${AppConfig.baseUrl}$imageUrl',
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) =>
                            Container(color: Colors.grey.shade900),
                      )
                    else
                      Container(color: Colors.grey.shade900),

                    // 渐变遮罩 (底部向上)
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      height: 80,
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.bottomCenter,
                            end: Alignment.topCenter,
                            colors: [
                              Colors.black.withValues(alpha: 0.8),
                              Colors.transparent,
                            ],
                          ),
                        ),
                      ),
                    ),

                    // 中心播放按钮
                    Center(
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.5),
                          shape: BoxShape.circle,
                        ),
                        padding: const EdgeInsets.all(8),
                        child: const Icon(Icons.play_arrow_rounded,
                            color: Colors.white, size: 32),
                      ),
                    ),

                    // 底部进度条 (可选)
                    if (hasProgress)
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        child: LinearProgressIndicator(
                          value: progressValue,
                          backgroundColor: Colors.white24,
                          valueColor: const AlwaysStoppedAnimation<Color>(
                              Colors.redAccent),
                          minHeight: 3,
                        ),
                      ),

                    // 进度时间文本
                    if (progressText != null)
                      Positioned(
                        right: 8,
                        bottom: 8,
                        child: Text(
                          progressText,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            shadows: [
                              Shadow(color: Colors.black, blurRadius: 2)
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            // 标题区域
            Text(
              displayTitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ),
    );
  }
}
