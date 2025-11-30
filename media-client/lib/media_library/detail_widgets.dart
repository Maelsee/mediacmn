import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:palette_generator/palette_generator.dart';
import '../core/config.dart';
import 'media_models.dart';

// 1. 背景构造模块
class DetailBackground extends StatefulWidget {
  final MediaDetail detail;
  final int? selectedSeasonIndex;
  final ValueChanged<Color>? onColorChanged;

  const DetailBackground({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
    this.onColorChanged,
  });

  @override
  State<DetailBackground> createState() => _DetailBackgroundState();
}

class _DetailBackgroundState extends State<DetailBackground> {
  Color? _extractedColor;
  ImageProvider? _currentImageProvider;

  /// 根据媒体类型选择背景图地址：
  /// - 电影：使用 `detail.backdropPath`
  /// - 剧集：优先当前季的 `cover`
  /// - 兜底：回退到 `detail.backdropPath`
  /// 返回值可能为 `null` 或空字符串，需在构建阶段处理
  String? _getImageUrl() {
    String? imageUrl;
    if (widget.detail.mediaType == 'movie') {
      imageUrl = widget.detail.backdropPath;
    } else {
      final seasons = widget.detail.seasons ?? [];
      final index =
          (widget.selectedSeasonIndex ?? 0).clamp(0, seasons.length - 1);
      if (seasons.isNotEmpty) {
        imageUrl = seasons[index].cover;
      }
    }
    // Fallback
    if (imageUrl == null || imageUrl.isEmpty) {
      imageUrl = widget.detail.backdropPath;
    }
    return imageUrl;
  }

  /// 异步从图片中提取代表性的深色作为页面背景主色：
  /// - 提取优先级：`darkMuted` > `darkVibrant` > `dominant`
  /// - 成功后：
  ///   1) 更新本组件的 `_extractedColor`
  ///   2) 通过 `onColorChanged` 回调通知父组件，用于统一设置 `Scaffold` 背景色
  /// - 失败时：保留主题默认表面色，避免阻塞 UI
  Future<void> _updatePalette(ImageProvider imageProvider) async {
    try {
      final paletteGenerator = await PaletteGenerator.fromImageProvider(
        imageProvider,
        maximumColorCount: 20,
      );
      if (!mounted) return;

      // 优先取深色静谧色，否则取深色鲜艳色，最后取默认深色
      final color = paletteGenerator.darkMutedColor?.color ??
          paletteGenerator.darkVibrantColor?.color ??
          paletteGenerator.dominantColor?.color;

      if (color != null) {
        setState(() {
          _extractedColor = color;
        });
        widget.onColorChanged?.call(color);
      }
    } catch (e) {
      debugPrint('Palette generation failed: $e');
    }
  }

  /// 当父组件传入的季索引或详情数据变更时，重置当前的图片提供者，
  /// 以便在下一帧重新进行调色板提取，保证背景颜色与新的图片一致。
  @override
  void didUpdateWidget(covariant DetailBackground oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedSeasonIndex != widget.selectedSeasonIndex ||
        oldWidget.detail != widget.detail) {
      _currentImageProvider = null; // Reset to trigger rebuild/re-extract
    }
  }

  @override

  /// 构建背景：
  /// - 底层以提取色铺满，保证“无限向下延伸”
  /// - 顶层放置对齐于顶部的封面图（`BoxFit.cover`）
  /// - 叠加自上而下的线性渐变，提前在 0.98 处过渡为纯色以消除缝隙
  /// - 额外加入 2px 的底部纯色条（向下偏移 1px）作为物理兜底，避免亚像素渲染产生细线
  Widget build(BuildContext context) {
    final imageUrl = _getImageUrl();
    final backgroundColor =
        _extractedColor ?? Theme.of(context).colorScheme.surface;

    if (imageUrl == null || imageUrl.isEmpty) {
      return Container(color: backgroundColor);
    }

    final url =
        (imageUrl.startsWith('http') ? '' : AppConfig.baseUrl) + imageUrl;

    // Create ImageProvider only if url changed to avoid loop
    final imageProvider = NetworkImage(url);
    if (_currentImageProvider != imageProvider) {
      _currentImageProvider = imageProvider;
      // Post frame callback to not block build
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _updatePalette(imageProvider);
      });
    }

    return Container(
      color: backgroundColor, // 底层铺满提取的颜色
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image(
            image: imageProvider,
            fit: BoxFit.cover,
            alignment: Alignment.topCenter,
            errorBuilder: (_, __, ___) => Container(color: backgroundColor),
          ),
          // 渐变遮罩：从透明过渡到提取的背景色
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  stops: const [0.0, 0.4, 0.98, 1.0], // 提前结束渐变，确保底部完全融合
                  colors: [
                    Colors.transparent,
                    backgroundColor.withValues(alpha: 0.0), // 中间保持透明
                    backgroundColor, // 底部变为纯色
                    backgroundColor, // 确保最后一点也是纯色
                  ],
                ),
              ),
            ),
          ),
          // 额外的底部覆盖层，防止亚像素渲染导致的细线
          Positioned(
            left: 0,
            right: 0,
            bottom: -1, // 稍微向下延伸，覆盖可能的缝隙
            height: 2,
            child: Container(color: backgroundColor),
          ),
        ],
      ),
    );
  }
}

// 2. 名称显示模块
class DetailTitle extends StatelessWidget {
  final MediaDetail detail;
  final int? selectedSeasonIndex;

  const DetailTitle({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
  });

  @override

  /// 展示媒体标题，使用主题的 `headlineMedium`，固定为白色以保证在深色背景上可读。
  Widget build(BuildContext context) {
    String title = detail.title;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Text(
        title,
        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: Colors.white,
            ),
      ),
    );
  }
}

// 3. 基本信息显示模块
class DetailInfo extends StatelessWidget {
  final MediaDetail detail;
  final int? selectedSeasonIndex;

  const DetailInfo({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
  });

  @override

  /// 汇总评分、日期、时长与最多三个类型标签，并以 `|` 分隔展示。
  /// 电影直取 `detail` 字段；剧集取当前季的对应字段。
  Widget build(BuildContext context) {
    double? rating;
    String? date;
    int? runtime;
    List<String> genres = detail.genres;

    if (detail.mediaType == 'movie') {
      rating = detail.rating;
      date = detail.releaseDate;
      runtime = detail.runtime;
    } else {
      final seasons = detail.seasons ?? [];
      final index = (selectedSeasonIndex ?? 0).clamp(0, seasons.length - 1);
      if (seasons.isNotEmpty) {
        final season = seasons[index];
        rating = season.rating;
        date = season.airDate;
        runtime = season.runtime;
      }
    }

    final parts = <String>[];
    if (rating != null) parts.add('⭐ ${rating.toStringAsFixed(1)}');
    if (date != null && date.isNotEmpty) parts.add(date.split('T').first);
    if (runtime != null) parts.add('${runtime}min');
    if (genres.isNotEmpty) parts.addAll(genres.take(3));

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Text(
        parts.join('  |  '),
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Colors.white70,
            ),
      ),
    );
  }
}

// 4. 简介模块
class DetailOverview extends StatefulWidget {
  /// 剧情简介模块：支持点击展开/收起，默认最多展示 4 行。
  final MediaDetail detail;
  final int? selectedSeasonIndex;

  const DetailOverview({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
  });

  @override
  State<DetailOverview> createState() => _DetailOverviewState();
}

class _DetailOverviewState extends State<DetailOverview> {
  bool _isExpanded = false;

  @override

  /// 根据媒体类型选择简介内容（电影直接取 `detail.overview`，剧集取当前季的 `overview`）。
  /// 点击标题右侧箭头或正文可切换展开状态。
  Widget build(BuildContext context) {
    String? overview;
    if (widget.detail.mediaType == 'movie') {
      overview = widget.detail.overview;
    } else {
      final seasons = widget.detail.seasons ?? [];
      final index =
          (widget.selectedSeasonIndex ?? 0).clamp(0, seasons.length - 1);
      if (seasons.isNotEmpty) {
        overview = seasons[index].overview;
      }
    }

    if (overview == null || overview.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '剧情简介',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
              ),
              InkWell(
                onTap: () {
                  setState(() {
                    _isExpanded = !_isExpanded;
                  });
                },
                child: Icon(
                  _isExpanded
                      ? Icons.keyboard_arrow_up
                      : Icons.keyboard_arrow_down,
                  color: Colors.white70,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          GestureDetector(
            onTap: () {
              setState(() {
                _isExpanded = !_isExpanded;
              });
            },
            child: Text(
              overview,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: Colors.white70),
              maxLines: _isExpanded ? null : 4,
              overflow:
                  _isExpanded ? TextOverflow.visible : TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

// 5. 演员表模块
class DetailCast extends StatelessWidget {
  final MediaDetail detail;
  final int? selectedSeasonIndex;

  const DetailCast({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
  });

  @override

  /// 展示演员横向列表：
  /// - 电影：取 `detail.cast`
  /// - 剧集：取当前季 `cast`
  /// 每项展示头像、姓名，若有角色名则附加一行小字。
  Widget build(BuildContext context) {
    List<CastItem> cast = [];
    if (detail.mediaType == 'movie') {
      cast = detail.cast ?? [];
    } else {
      final seasons = detail.seasons ?? [];
      final index = (selectedSeasonIndex ?? 0).clamp(0, seasons.length - 1);
      if (seasons.isNotEmpty) {
        cast = seasons[index].cast ?? [];
      }
    }

    if (cast.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Text(
            '相关演员',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
          ),
        ),
        SizedBox(
          height: 140, // Increased height for character name
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            scrollDirection: Axis.horizontal,
            itemCount: cast.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final c = cast[index];
              final url = c.imageUrl;
              final fullUrl = (url != null && !url.startsWith('http'))
                  ? '${AppConfig.baseUrl}$url'
                  : url;

              return Column(
                children: [
                  CircleAvatar(
                    radius: 36,
                    backgroundImage:
                        fullUrl != null ? NetworkImage(fullUrl) : null,
                    child: fullUrl == null ? const Icon(Icons.person) : null,
                  ),
                  const SizedBox(height: 4),
                  SizedBox(
                    width: 72,
                    child: Text(
                      c.name,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: Colors.white),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                    ),
                  ),
                  if (c.character != null && c.character!.isNotEmpty)
                    SizedBox(
                      width: 72,
                      child: Text(
                        c.character!,
                        style: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(color: Colors.white54, fontSize: 10),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                      ),
                    ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }
}

// 6. 存储路径模块
class DetailPath extends StatelessWidget {
  final MediaDetail detail;
  final int? selectedSeasonIndex;
  final int? selectedEpisodeIndex;
  final int? selectedVersionIndex;

  const DetailPath({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
    this.selectedEpisodeIndex,
    this.selectedVersionIndex,
  });

  @override

  /// 展示当前选择的资源对应的本地/远程存储路径：
  /// - 电影：取选中版本的首个资源路径
  /// - 剧集：取当前季/当前集的首个资源路径
  /// 若不可用则不渲染该模块。
  Widget build(BuildContext context) {
    String pathInfo = '';

    if (detail.mediaType == 'movie') {
      final versions = detail.versions;
      if (versions != null && versions.isNotEmpty) {
        final vIndex =
            (selectedVersionIndex ?? 0).clamp(0, versions.length - 1);
        final assets = versions[vIndex].assets;
        if (assets.isNotEmpty) {
          pathInfo = assets.first.path;
        }
      }
    } else {
      final seasons = detail.seasons ?? [];
      final sIndex = (selectedSeasonIndex ?? 0).clamp(0, seasons.length - 1);
      if (seasons.isNotEmpty) {
        final episodes = seasons[sIndex].episodes;
        final eIndex =
            (selectedEpisodeIndex ?? 0).clamp(0, episodes.length - 1);
        if (episodes.isNotEmpty) {
          final assets = episodes[eIndex].assets;
          if (assets.isNotEmpty) {
            pathInfo = assets.first.path;
          }
        }
      }
    }

    if (pathInfo.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Text(
        '存储路径: $pathInfo',
        style:
            Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.grey),
      ),
    );
  }
}

// 7. 播放按钮模块
class DetailPlayButton extends StatelessWidget {
  final MediaDetail detail;
  final int? selectedSeasonIndex;
  final int? selectedEpisodeIndex;
  final int? selectedVersionIndex;

  const DetailPlayButton({
    super.key,
    required this.detail,
    this.selectedSeasonIndex,
    this.selectedEpisodeIndex,
    this.selectedVersionIndex,
  });

  @override

  /// 播放按钮：根据当前选择的季/集/版本，计算首选资源并携带候选列表，
  /// 跳转到播放页 `/media/play/{detail.id}`。
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: SizedBox(
        width: double.infinity,
        height: 48,
        child: FilledButton.icon(
          onPressed: () {
            // Logic to play
            final sIndex = selectedSeasonIndex ?? 0;
            final eIndex = selectedEpisodeIndex ?? 0;
            final vIndex = selectedVersionIndex ?? 0;

            AssetItem? asset;
            List<dynamic> candidates = [];

            if (detail.mediaType == 'movie') {
              if (detail.versions != null && detail.versions!.isNotEmpty) {
                final version = detail
                    .versions![vIndex.clamp(0, detail.versions!.length - 1)];
                if (version.assets.isNotEmpty) {
                  asset = version.assets.first;
                  candidates = [asset];
                }
              }
            } else {
              final seasons = detail.seasons ?? [];
              if (seasons.isNotEmpty) {
                final season = seasons[sIndex.clamp(0, seasons.length - 1)];
                final episodes = season.episodes;
                if (episodes.isNotEmpty) {
                  final episode =
                      episodes[eIndex.clamp(0, episodes.length - 1)];
                  if (episode.assets.isNotEmpty) {
                    asset = episode.assets.first;
                    candidates = episode.assets;
                  }
                }
              }
            }

            context.push('/media/play/${detail.id}', extra: {
              'detail': detail,
              'asset': asset,
              'candidates': candidates,
            });
          },
          icon: const Icon(Icons.play_arrow),
          label: const Text('播放'),
          style: FilledButton.styleFrom(
            backgroundColor: Colors.white,
            foregroundColor: Colors.black,
          ),
        ),
      ),
    );
  }
}

// 8. 电影版本模块
class DetailVersions extends StatelessWidget {
  final MediaDetail detail;
  final int selectedVersionIndex;
  final ValueChanged<int> onVersionSelected;

  const DetailVersions({
    super.key,
    required this.detail,
    required this.selectedVersionIndex,
    required this.onVersionSelected,
  });

  @override

  /// 电影版本选择列表：横向滚动，展示清晰度与资源大小信息。
  /// 选中态以白色描边突出，并通过回调上报选中索引。
  Widget build(BuildContext context) {
    if (detail.mediaType != 'movie' ||
        detail.versions == null ||
        detail.versions!.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Text(
            '影片版本',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
          ),
        ),
        SizedBox(
          height: 80, // Increased height for more info
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            scrollDirection: Axis.horizontal,
            itemCount: detail.versions!.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final v = detail.versions![index];
              final isSelected = index == selectedVersionIndex;

              // Get size info from first asset if available
              String sizeInfo = '';
              if (v.assets.isNotEmpty) {
                sizeInfo = v.assets.first.sizeText ?? '';
              }

              return GestureDetector(
                onTap: () => onVersionSelected(index),
                child: Container(
                  width: 160,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white10,
                    borderRadius: BorderRadius.circular(8),
                    border: isSelected
                        ? Border.all(color: Colors.white, width: 2)
                        : null,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        v.quality ?? v.label ?? 'Unknown',
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 4),
                      if (sizeInfo.isNotEmpty)
                        Text(
                          sizeInfo,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 12,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

// 9. 系列季-集模块
class DetailSeasonsEpisodes extends StatelessWidget {
  final MediaDetail detail;
  final int selectedSeasonIndex;
  final int selectedEpisodeIndex;
  final ValueChanged<int> onSeasonSelected;
  final ValueChanged<int> onEpisodeSelected;

  const DetailSeasonsEpisodes({
    super.key,
    required this.detail,
    required this.selectedSeasonIndex,
    required this.selectedEpisodeIndex,
    required this.onSeasonSelected,
    required this.onEpisodeSelected,
  });

  @override

  /// 剧集季/集选择模块：
  /// - 顶部下拉选择季
  /// - 底部横向列表选择具体集，选中项以白色描边强调
  /// 通过回调通知父组件更新选择状态。
  Widget build(BuildContext context) {
    if (detail.mediaType != 'tv' ||
        detail.seasons == null ||
        detail.seasons!.isEmpty) {
      return const SizedBox.shrink();
    }

    final seasons = detail.seasons!;
    final currentSeason =
        seasons[selectedSeasonIndex.clamp(0, seasons.length - 1)];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Season Selector
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: DropdownButton<int>(
            value: selectedSeasonIndex,
            dropdownColor: Colors.grey[900],
            style: const TextStyle(color: Colors.white),
            items: List.generate(seasons.length, (index) {
              return DropdownMenuItem(
                value: index,
                child: Text('第 ${seasons[index].seasonNumber} 季'),
              );
            }),
            onChanged: (v) {
              if (v != null) onSeasonSelected(v);
            },
            underline: Container(),
            icon: const Icon(Icons.arrow_drop_down, color: Colors.white),
          ),
        ),

        // Episodes List
        SizedBox(
          height: 140,
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            scrollDirection: Axis.horizontal,
            itemCount: currentSeason.episodes.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final ep = currentSeason.episodes[index];
              final stillUrl = ep.stillPath;
              final fullStillUrl =
                  (stillUrl != null && !stillUrl.startsWith('http'))
                      ? '${AppConfig.baseUrl}$stillUrl'
                      : stillUrl;

              final isSelected = index == selectedEpisodeIndex;

              return GestureDetector(
                onTap: () => onEpisodeSelected(index),
                child: SizedBox(
                  width: 200,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Container(
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(8),
                            border: isSelected
                                ? Border.all(color: Colors.white, width: 2)
                                : null,
                            image: fullStillUrl != null
                                ? DecorationImage(
                                    image: NetworkImage(fullStillUrl),
                                    fit: BoxFit.cover,
                                    colorFilter: ColorFilter.mode(
                                      Colors.black.withValues(alpha: 0.3),
                                      BlendMode.darken,
                                    ),
                                  )
                                : null,
                            color: Colors.white10,
                          ),
                          child: fullStillUrl == null
                              ? const Center(
                                  child:
                                      Icon(Icons.movie, color: Colors.white54))
                              : null,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${ep.episodeNumber}. ${ep.title}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: isSelected ? Colors.white : Colors.white70,
                            fontWeight: isSelected
                                ? FontWeight.bold
                                : FontWeight.normal),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}
