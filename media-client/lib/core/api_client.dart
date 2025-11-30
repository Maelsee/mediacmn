import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:hive_flutter/hive_flutter.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'config.dart';
import '../source_library/tasks/task_models.dart';
import '../source_library/source_models.dart';
import '../media_library/media_models.dart';

class ApiClient {
  final http.Client _client;
  String? _token;
  String? _refreshToken;
  String? _tokenType;
  DateTime? _tokenExpiresAt;
  ApiClient({http.Client? client}) : _client = client ?? http.Client() {
    _restoreFromHive();
  }

  Uri _u(String path) => Uri.parse('${AppConfig.baseUrl}$path');

  bool _isTokenValid() {
    final t = _token;
    if (t == null || t.isEmpty) return false;
    final exp = _tokenExpiresAt;
    if (exp == null) return true;
    return DateTime.now().isBefore(exp);
  }

  void _restoreFromHive() {
    if (!Hive.isBoxOpen('auth')) return;
    final box = Hive.box('auth');
    final t = box.get('token') as String?;
    final rt = box.get('refresh_token') as String?;
    final tt = box.get('token_type') as String?;
    final expMs = box.get('token_expires_at') as int?;
    _token = t;
    _refreshToken = rt;
    _tokenType = tt;
    _tokenExpiresAt =
        expMs != null ? DateTime.fromMillisecondsSinceEpoch(expMs) : null;
  }

  void _writeHive(String key, dynamic value) {
    if (!Hive.isBoxOpen('auth')) return;
    final box = Hive.box('auth');
    if (value == null) {
      box.delete(key);
      return;
    }
    box.put(key, value);
  }

  void setToken(String? token) {
    _token = token;
    _writeHive('token', token);
  }

  void setRefreshToken(String? token) {
    _refreshToken = token;
    _writeHive('refresh_token', token);
  }

  void setTokenType(String? type) {
    _tokenType = type;
    _writeHive('token_type', type);
  }

  void setTokenExpiresIn(int? seconds) {
    _tokenExpiresAt =
        seconds != null ? DateTime.now().add(Duration(seconds: seconds)) : null;
    _writeHive('token_expires_at', _tokenExpiresAt?.millisecondsSinceEpoch);
  }

  Map<String, String> authHeaders() {
    final h = <String, String>{};
    if (_isTokenValid()) {
      h['Authorization'] = '${_tokenType ?? 'Bearer'} ${_token!}';
    }
    return h;
  }

  Map<String, String> _headers({Map<String, String>? headers}) {
    final h = <String, String>{};
    if (headers != null) {
      h.addAll(headers);
    }
    if (_isTokenValid()) {
      h['Authorization'] = '${_tokenType ?? 'Bearer'} ${_token!}';
    }
    return h;
  }

  bool get isLoggedIn => _isTokenValid();

  Future<Map<String, dynamic>?> getCurrentUser() async {
    if (!_isTokenValid()) return null;
    final res = await _client.get(_u('/api/auth/me'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    return null;
  }

  Future<void> refreshToken() async {
    final rt = _refreshToken;
    if (rt == null || rt.isEmpty) {
      return;
    }
    final res = await _client.post(_u('/api/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': rt}));
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final newRt = data['refresh_token'] as String?;
      if (newRt != null && newRt.isNotEmpty) {
        setRefreshToken(newRt);
      }
      return;
    }
    throw Exception('refresh_failed');
  }

  Future<void> logout() async {
    try {
      await _client.post(_u('/api/auth/logout'), headers: _headers());
    } catch (_) {}
    setToken(null);
    setRefreshToken(null);
    setTokenType(null);
    setTokenExpiresIn(null);
  }

  Future<ScanGroup> scanAll({List<String>? sourceIds}) async {
    final qs = <String>[];
    if (sourceIds != null && sourceIds.isNotEmpty) {
      qs.add('sources=${Uri.encodeComponent(sourceIds.join(','))}');
    }
    final q = qs.isEmpty ? '' : '?${qs.join('&')}';
    final res = await _client.get(_u('/api/scan/all$q'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      // 后端 TaskResponse → 需要适配为 ScanGroup 结构的最小体
      final gid = (data['task_id'] as String?) ?? 'group';
      return ScanGroup(
          groupId: gid,
          status: data['status'] as String? ?? 'pending',
          progress: 0,
          tasks: const []);
    }
    throw Exception('scan_all_failed');
  }

  Future<String> createScanTask({required String storageId}) async {
    final sid = int.tryParse(storageId);
    final res = await _client.post(_u('/api/scan/create-task'),
        headers: _headers(headers: {'Content-Type': 'application/json'}),
        body: jsonEncode({'storage_id': sid ?? storageId}));
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final taskId = data['task_id'] as String?;
      if (taskId != null && taskId.isNotEmpty) return taskId;
    }
    throw Exception('create_scan_task_failed');
  }

  Future<List<ScanTask>> getGroup(String groupId) async {
    final res =
        await _client.get(_u('/scan/groups/$groupId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final items = (data['tasks'] as List).cast<Map<String, dynamic>>();
      return items.map(ScanTask.fromJson).toList();
    }
    throw Exception('scan_group_failed');
  }

  Future<SourceCreateResponse> createSource(
      Map<String, dynamic> payload) async {
    final res = await _client.post(_u('/api/storage'),
        headers: _headers(headers: {'Content-Type': 'application/json'}),
        body: jsonEncode(payload));
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return SourceCreateResponse.fromJson(data);
    }
    throw Exception('create_source_failed');
  }

  Future<List<ScanTask>> getTasksBySource(String sourceId) async {
    final res =
        await _client.get(_u('/tasks?sources=$sourceId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list.map(ScanTask.fromJson).toList();
    }
    throw Exception('get_tasks_failed');
  }

  Future<Map<String, dynamic>> getScanTaskStatus(String taskId) async {
    final res =
        await _client.get(_u('/api/scan/task/$taskId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('get_task_status_failed');
  }

  Future<bool> testStorageConnection(String storageId) async {
    final sid = int.tryParse(storageId) ?? storageId;
    final res = await _client.get(_u('/api/storage-unified/$sid/test'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return (data['success'] as bool?) ?? true;
    }
    return false;
  }

  Future<Map<String, dynamic>> getPlayUrl(int fileId) async {
    final res =
        await _client.get(_u('/api/media/play/$fileId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('get_play_url_failed');
  }

  Future<Map<String, dynamic>> refreshPlayUrl(int fileId) async {
    final res = await _client.post(_u('/api/media/play/refresh'),
        headers: _headers(headers: {'Content-Type': 'application/json'}),
        body: jsonEncode({'file_id': fileId}));
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('refresh_play_url_failed');
  }

  Future<int?> getPlaybackProgress(int fileId) async {
    final res = await _client.get(_u('/api/playback/progress/$fileId'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final v = (data['position_ms'] as num?)?.toInt();
      return v;
    }
    return null;
  }

  Future<void> reportPlaybackProgress({
    required int fileId,
    int? coreId,
    required int positionMs,
    int? durationMs,
    String? status,
    String? platform,
    String? deviceId,
    String? mediaType,
    int? seriesCoreId,
    int? seasonCoreId,
    int? episodeCoreId,
    int? versionId,
  }) async {
    final payload = {
      'file_id': fileId,
      if (coreId != null) 'core_id': coreId,
      'position_ms': positionMs,
      if (durationMs != null) 'duration_ms': durationMs,
      if (status != null) 'status': status,
      if (platform != null) 'platform': platform,
      if (deviceId != null) 'device_id': deviceId,
      if (mediaType != null) 'media_type': mediaType,
      if (seriesCoreId != null) 'series_core_id': seriesCoreId,
      if (seasonCoreId != null) 'season_core_id': seasonCoreId,
      if (episodeCoreId != null) 'episode_core_id': episodeCoreId,
      if (versionId != null) 'version_id': versionId,
    };
    if (!_isTokenValid()) {
      await refreshToken();
    }
    final res = await _client.post(
      _u('/api/playback/progress'),
      headers: _headers(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(payload),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return;
  }

  Future<List<RecentCardItem>> getRecent(
      {int limit = 20, String? sort, String? dedup}) async {
    final qs = <String>['limit=$limit'];
    if (sort != null && sort.isNotEmpty) qs.add('sort=$sort');
    if (dedup != null && dedup.isNotEmpty) qs.add('dedup=$dedup');
    final res = await _client.get(_u('/api/playback/recent?${qs.join('&')}'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list.map(RecentCardItem.fromApi).toList();
    }
    throw Exception('get_recent_failed');
  }

  Future<List<Map<String, dynamic>>> getRecentRaw({
    int? page,
    int? pageSize,
    String? dedup,
    String? sort,
  }) async {
    final qs = <String>[];
    if (page != null && page > 0) qs.add('page=$page');
    if (pageSize != null && pageSize > 0) qs.add('page_size=$pageSize');
    if (dedup != null && dedup.isNotEmpty) qs.add('dedup=$dedup');
    if (sort != null && sort.isNotEmpty) qs.add('sort=$sort');
    final q = qs.isEmpty ? '' : '?${qs.join('&')}';
    final res =
        await _client.get(_u('/api/playback/recent$q'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list;
    }
    throw Exception('get_recent_raw_failed');
  }

  Future<void> deletePlaybackProgress(int fileId) async {
    final res = await _client.delete(_u('/api/playback/progress/$fileId'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('delete_progress_failed');
  }

  Future<HomeCardsResponse> getLibraryHome() async {
    // 接入后端真实API：/api/media/cards/home
    final res =
        await _client.get(_u('/api/media/cards/home'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return HomeCardsResponse.fromJson(data);
    }
    throw Exception('get_library_home_failed');
  }

  Future<PagedMediaResponse> getLibraryCategoryItems(String categoryId,
      {int page = 1, int pageSize = 30}) async {
    final res = await _client.get(
        _u('/library/categories/$categoryId/items?page=$page&page_size=$pageSize'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return PagedMediaResponse.fromJson(data);
    }
    throw Exception('get_category_items_failed');
  }

  Future<FilterCardsResponse> searchMedia(
    String query, {
    int page = 1,
    int pageSize = 30,
    String? kind,
    List<String>? genres,
    String? year,
    String? region,
    String? sort,
  }) async {
    final params = <String, String>{
      'q': query,
      'page': '$page',
      'page_size': '$pageSize',
    };
    if (kind != null && kind.isNotEmpty && kind != '全部') {
      params['type'] = kind;
    }
    if (genres != null && genres.isNotEmpty && !genres.contains('全部')) {
      params['genres'] = genres.join(',');
    }
    if (year != null && year.isNotEmpty && year != '全部') {
      params['year'] = year;
    }
    if (region != null && region.isNotEmpty && region != '全部') {
      params['countries'] = region;
    }
    if (sort != null && sort.isNotEmpty) {
      params['sort'] = sort;
    }
    final queryString = params.entries
        .map((e) => '${e.key}=${Uri.encodeComponent(e.value)}')
        .join('&');
    final res = await _client.get(_u('/api/media/cards?$queryString'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return FilterCardsResponse.fromJson(data);
    }
    throw Exception('search_failed');
  }

  Future<MediaDetail> getMediaDetail(int id) async {
    final res =
        await _client.get(_u('/api/media/$id/detail'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return MediaDetail.fromJson(data);
    }
    throw Exception('get_media_detail_failed');
  }

  Future<List<Map<String, dynamic>>> getSubtitles(int fileId) async {
    final res =
        await _client.get(_u('/subtitles/$fileId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list;
    }
    throw Exception('get_subtitles_failed');
  }

  Future<List<SourceItem>> getSources({int page = 1, int size = 20}) async {
    final res = await _client.get(_u('/api/storage'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list.map(SourceItem.fromJson).toList();
    }
    throw Exception('get_sources_failed');
  }

  Future<void> scanSource(String sourceId) async {
    final res =
        await _client.post(_u('/sources/$sourceId/scan'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('scan_source_failed');
  }

  Future<SourceItem> getSource(String sourceId) async {
    final res =
        await _client.get(_u('/api/storage/$sourceId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final wrapped = data['data'] as Map<String, dynamic>?;
      return SourceItem.fromJson(wrapped ?? data);
    }
    throw Exception('get_source_failed');
  }

  Future<Map<String, dynamic>> getStorageDetail(String sourceId) async {
    final res =
        await _client.get(_u('/api/storage/$sourceId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final wrapped = data['data'] as Map<String, dynamic>?;
      return wrapped ?? data;
    }
    throw Exception('get_storage_detail_failed');
  }

  Future<void> updateSource(
      String sourceId, Map<String, dynamic> payload) async {
    final res = await _client.put(_u('/api/storage/$sourceId'),
        headers: _headers(headers: {'Content-Type': 'application/json'}),
        body: jsonEncode(payload));
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('update_source_failed');
  }

  Future<void> toggleSource(String sourceId, {required bool enabled}) async {
    final res = await _client.post(
        _u('/sources/$sourceId/${enabled ? 'enable' : 'disable'}'),
        headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('toggle_source_failed');
  }

  Future<void> deleteSource(String sourceId) async {
    final res =
        await _client.delete(_u('/api/storage/$sourceId'), headers: _headers());
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('delete_source_failed');
  }

  Future<String> loginWithEmail(String email, String password) async {
    final res = await _client.post(_u('/api/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}));
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final accessToken = data['access_token'] as String?;
      final token = accessToken ?? data['token'] as String?;
      final refreshToken = data['refresh_token'] as String?;
      final tokenType = data['token_type'] as String?;
      final expiresIn = (data['expires_in'] as num?)?.toInt();
      if (token == null || token.isEmpty) {
        throw Exception('login_token_missing');
      }
      setToken(token);
      setRefreshToken(refreshToken);
      setTokenType(tokenType);
      setTokenExpiresIn(expiresIn);
      return token;
    }
    throw Exception('login_failed');
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final authUserProvider = FutureProvider<Map<String, dynamic>?>(
  (ref) async {
    final api = ref.watch(apiClientProvider);
    return api.getCurrentUser();
  },
);
