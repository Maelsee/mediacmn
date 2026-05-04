import 'dart:convert';
import '../../../core/api_client.dart';
import '../models/danmu_models.dart';

extension DanmuApi on ApiClient {
  /// 自动匹配弹幕
  Future<DanmuMatchResult> danmuAutoMatch(String fileId,
      {String? title, int? season, int? episode}) async {
    final payload = <String, dynamic>{
      'file_id': fileId,
    };
    // if (title != null) payload['title'] = title;
    // if (season != null) payload['season'] = season;
    // if (episode != null) payload['episode'] = episode;

    final res = await client.post(
      u('/api/danmu/match/auto'),
      headers: getHeaders(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(payload),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('弹幕匹配失败: ${res.statusCode} ${res.body}');
    }
    final json = jsonDecode(res.body) as Map<String, dynamic>;
    return DanmuMatchResult.fromJson(json);
  }

  /// 搜索弹幕
  Future<List<DanmuSearchItem>> danmuSearch(String keyword,
      {String type = 'anime', int limit = 20}) async {
    final payload = <String, dynamic>{
      'keyword': keyword,
      'type': type,
      'limit': limit,
    };
    final res = await client.post(
      u('/api/danmu/search'),
      headers: getHeaders(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(payload),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('搜索失败');
    }
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    return (data['items'] as List?)
            ?.map((e) => DanmuSearchItem.fromJson(e as Map<String, dynamic>))
            .toList() ??
        const [];
  }

  /// 获取 bangumi 详情（含 episodes）
  Future<DanmuBangumi> getDanmuBangumi(int animeId) async {
    final res = await client.get(
      u('/api/danmu/bangumi/$animeId'),
      headers: getHeaders(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('获取番剧信息失败');
    }
    return DanmuBangumi.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 按 episodeId 获取弹幕
  Future<DanmuData> getDanmuByEpisode(int episodeId, String fileId,
      {String loadMode = 'segment'}) async {
    final qs =
        'file_id=${Uri.encodeComponent(fileId)}&load_mode=${Uri.encodeComponent(loadMode)}';
    final res = await client.get(
      u('/api/danmu/$episodeId?$qs'),
      headers: getHeaders(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('获取弹幕失败');
    }
    final json = jsonDecode(res.body) as Map<String, dynamic>;
    return DanmuData.fromJson(json);
  }

  /// 加载下一分片
  Future<DanmuNextSegmentResult> danmuNextSegment(
      DanmuSegment segment, int episodeId,
      {String format = 'json'}) async {
    final payload = <String, dynamic>{
      'type': segment.type,
      'segment_start': segment.segmentStart.toInt(),
      'segment_end': segment.segmentEnd.toInt(),
      'url': segment.url,
      'episode_id': episodeId.toString(),
      'format': format,
    };

    final res = await client.post(
      u('/api/danmu/$episodeId/next-segment'),
      headers: getHeaders(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(payload),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('加载分片失败: ${res.statusCode} ${res.body}');
    }
    return DanmuNextSegmentResult.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 保存手动绑定
  Future<DanmuBinding> saveDanmuBinding(String fileId, int episodeId) async {
    final res = await client.post(
      u('/api/danmu/match/bind/$fileId'),
      headers: getHeaders(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode({'episode_id': episodeId}),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('保存绑定失败');
    }
    return DanmuBinding.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// 删除绑定
  Future<void> deleteDanmuBinding(String fileId) async {
    final res = await client.delete(
      u('/api/danmu/match/bind/$fileId'),
      headers: getHeaders(),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('删除绑定失败');
    }
  }

  /// 调整偏移量
  Future<DanmuBinding> updateDanmuOffset(String fileId, double offset) async {
    final res = await client.put(
      u('/api/danmu/match/bind/$fileId/offset'),
      headers: getHeaders(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode({'offset': offset}),
    );
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('调整偏移失败');
    }
    return DanmuBinding.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }
}
