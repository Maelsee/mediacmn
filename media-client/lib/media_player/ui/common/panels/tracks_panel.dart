import 'package:flutter/material.dart';

import '../components/side_panel.dart';

class TracksPanel extends StatelessWidget {
  final List<dynamic> audioTracks;
  final dynamic currentAudio;
  final List<dynamic> subtitleTracks;
  final dynamic currentSubtitle;
  final List<dynamic> videoTracks;
  final List<Map<String, dynamic>> externalSubtitles;
  final bool loadingExternalSubtitles;
  final String? externalSubtitleError;
  final void Function(dynamic) onAudioSelected;
  final void Function(dynamic) onSubtitleSelected;
  final void Function(Map<String, dynamic>) onExternalSubtitleSelected;
  final void Function(dynamic) onVideoSelected;

  const TracksPanel({
    super.key,
    required this.audioTracks,
    required this.currentAudio,
    required this.subtitleTracks,
    required this.currentSubtitle,
    required this.videoTracks,
    required this.externalSubtitles,
    required this.loadingExternalSubtitles,
    required this.externalSubtitleError,
    required this.onAudioSelected,
    required this.onSubtitleSelected,
    required this.onExternalSubtitleSelected,
    required this.onVideoSelected,
  });

  @override
  Widget build(BuildContext context) {
    return SidePanel(
      title: '字幕/音轨',
      child: DefaultTabController(
        length: 3,
        child: Column(
          children: [
            const TabBar(
              labelColor: Colors.blue,
              unselectedLabelColor: Colors.white70,
              indicatorColor: Colors.blue,
              tabs: [
                Tab(text: '音频'),
                Tab(text: '字幕'),
                Tab(text: '视频'),
              ],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  _buildAudioTab(),
                  _buildSubtitleTab(),
                  _buildVideoTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAudioTab() {
    return ListView(
      children: audioTracks.map((track) {
        final title =
            track.title ?? track.language ?? track.id ?? track.toString();
        final selected = track == currentAudio;
        return ListTile(
          title: Text(
            title.toString(),
            style: const TextStyle(color: Colors.white),
          ),
          selected: selected,
          onTap: () => onAudioSelected(track),
          trailing:
              selected ? const Icon(Icons.check, color: Colors.blue) : null,
        );
      }).toList(),
    );
  }

  Widget _buildSubtitleTab() {
    final items = <Widget>[];

    if (subtitleTracks.isNotEmpty) {
      items.add(
        const ListTile(
          title: Text(
            '内嵌字幕',
            style: TextStyle(
              color: Colors.white70,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      );
      items.addAll(subtitleTracks.map((track) {
        final title =
            track.title ?? track.language ?? track.id ?? track.toString();
        final selected = track == currentSubtitle;
        return ListTile(
          title: Text(
            title.toString(),
            style: const TextStyle(color: Colors.white),
          ),
          selected: selected,
          onTap: () => onSubtitleSelected(track),
          trailing:
              selected ? const Icon(Icons.check, color: Colors.blue) : null,
        );
      }));
    }

    if (loadingExternalSubtitles) {
      items.add(
        const ListTile(
          title: Text(
            '正在加载外挂字幕...',
            style: TextStyle(color: Colors.white70),
          ),
        ),
      );
    } else if (externalSubtitleError != null) {
      items.add(
        ListTile(
          title: Text(
            '加载外挂字幕失败: $externalSubtitleError',
            style: const TextStyle(color: Colors.redAccent),
          ),
        ),
      );
    }

    if (!loadingExternalSubtitles && externalSubtitles.isNotEmpty) {
      items.add(
        const ListTile(
          title: Text(
            '外挂字幕',
            style: TextStyle(
              color: Colors.white70,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      );
      for (final sub in externalSubtitles) {
        final name =
            (sub['name'] ?? sub['path'] ?? sub['url'] ?? sub['id'] ?? '')
                .toString();
        final selected = _isExternalSubtitleSelected(sub);
        items.add(
          ListTile(
            title: Text(
              name,
              style: const TextStyle(color: Colors.white),
            ),
            selected: selected,
            onTap: () => onExternalSubtitleSelected(sub),
            trailing:
                selected ? const Icon(Icons.check, color: Colors.blue) : null,
          ),
        );
      }
    }

    if (items.isEmpty) {
      items.add(
        const ListTile(
          title: Text(
            '暂无字幕信息',
            style: TextStyle(color: Colors.white70),
          ),
        ),
      );
    }

    return ListView(children: items);
  }

  bool _isExternalSubtitleSelected(Map<String, dynamic> sub) {
    if (currentSubtitle == null) return false;
    final id = sub['id'] ?? sub['url'];
    if (id == null) return false;
    final currentId = currentSubtitle.id;
    return currentId != null && currentId.toString() == id.toString();
  }

  Widget _buildVideoTab() {
    return ListView(
      children: videoTracks.map((track) {
        final title =
            track.title ?? track.language ?? track.id ?? track.toString();
        return ListTile(
          title: Text(
            title.toString(),
            style: const TextStyle(color: Colors.white),
          ),
          onTap: () => onVideoSelected(track),
        );
      }).toList(),
    );
  }
}
