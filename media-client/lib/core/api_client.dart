import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:hive_flutter/hive_flutter.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'config.dart';
import 'playback_history/local_playback_store.dart';
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
  Uri u(String path) => _u(path);
  http.Client get client => _client;

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

  Map<String, dynamic> _normalizeWebdavPayload(Map<String, dynamic> payload) {
    final out = Map<String, dynamic>.from(payload);
    final configAny = out['config'];
    if (configAny is! Map) return out;

    final config = <String, dynamic>{};
    for (final e in configAny.entries) {
      config['${e.key}'] = e.value;
    }

    final storageType = out['storage_type'];
    final isWebdav = storageType == 'webdav' ||
        (config.containsKey('root_path') && config.containsKey('verify_ssl'));
    if (!isWebdav) return out;

    final raw = config['hostname'];
    if (raw is String) {
      var hostname = raw.trim();
      while (hostname.endsWith('/')) {
        hostname = hostname.substring(0, hostname.length - 1);
      }
      if (hostname.isNotEmpty && !hostname.contains('://')) {
        hostname = 'http://$hostname';
      }
      config['hostname'] = hostname;
      out['config'] = config;
    }
    return out;
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

  Map<String, String> getHeaders({Map<String, String>? headers}) =>
      _headers(headers: headers);

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
    final res = await _client.post(
      _u('/api/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': rt}),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final accessToken = data['access_token'] as String?;
      final token = accessToken ?? data['token'] as String?;
      final tokenType = data['token_type'] as String?;
      final expiresIn = (data['expires_in'] as num?)?.toInt();
      if (token != null && token.isNotEmpty) {
        setToken(token);
        setTokenType(tokenType);
        setTokenExpiresIn(expiresIn);
      }
      final newRt = data['refresh_token'] as String?;
      if (newRt != null && newRt.isNotEmpty) {
        setRefreshToken(newRt);
      }
      return;
    }
    throw Exception('刷新令牌失败');
  }

  Future<void> logout() async {
    try {
      await _client.post(_u('/api/auth/logout'), headers: _headers());
    } catch (_) {}
    setToken(null);
    setRefreshToken(null);
    setTokenType(null);
    setTokenExpiresIn(null);
    try {
      await LocalPlaybackStore.clearAll();
    } catch (_) {}
  }

  /// 启动扫描任务
  /// [storageId] 可选的存储 ID，如果不传则扫描所有存储
  /// [scanPath] 可选的扫描路径列表，如果不传则扫描存储根路径
  Future<String> startScan({int? storageId, List<String>? scanPath}) async {
    final payload = <String, dynamic>{
      if (storageId != null) 'storage_id': storageId,
      'scan_path': scanPath ?? [],
    };

    if (!_isTokenValid()) {
      await refreshToken();
    }

    final res = await _client.post(
      _u('/api/scan/start'),
      headers: _headers(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(payload),
    );

    if (res.statusCode == 401) {
      await refreshToken();
      final retry = await _client.post(
        _u('/api/scan/start'),
        headers: _headers(headers: {'Content-Type': 'application/json'}),
        body: jsonEncode(payload),
      );
      if (retry.statusCode >= 200 && retry.statusCode < 300) {
        final data = jsonDecode(retry.body) as Map<String, dynamic>;
        return (data['task_id'] as String?) ?? '';
      }
      throw Exception('启动扫描失败(401)');
    }

    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      // 返回任务 ID，如果是批量任务则返回批次 ID
      return (data['task_id'] as String?) ?? '';
    }
    throw Exception('启动扫描任务失败');
  }

  Future<List<Map<String, dynamic>>> listDirectory(
    int storageId,
    String path,
  ) async {
    final res = await _client.get(
      _u(
        '/api/storage-server/$storageId/list?path=${Uri.encodeComponent(path)}',
      ),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final entries = (data['entries'] as List).cast<Map<String, dynamic>>();
      return entries;
    }
    throw Exception('获取目录列表失败');
  }

  Future<List<Map<String, dynamic>>> listOnlyDirectory(
    int storageId,
    String path,
  ) async {
    final res = await _client.get(
      _u(
        '/api/storage-server/$storageId/listdir?path=${Uri.encodeComponent(path)}',
      ),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final entries = (data['entries'] as List).cast<Map<String, dynamic>>();
      return entries;
    }
    throw Exception('获取目录列表失败');
  }

  Future<bool> testConnection(int storageId) async {
    final res = await _client.get(
      _u('/api/storage-server/$storageId/test'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return (data['success'] as bool?) ?? false;
    }
    return false;
  }

  Future<void> enableStorage(int storageId) async {
    final res = await _client.post(
      _u('/api/storage-server/$storageId/enable'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('启用存储失败');
  }

  Future<void> disableStorage(int storageId) async {
    final res = await _client.post(
      _u('/api/storage-server/$storageId/disable'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('禁用存储失败');
  }

  /// 获取任务组状态（任务托盘下线后不再使用）

  /// 创建存储配置
  Future<SourceCreateResponse> createSource(
    Map<String, dynamic> payload,
  ) async {
    final normalized = _normalizeWebdavPayload(payload);
    // 307 Redirect fix: Add trailing slash
    final res = await _client.post(
      _u('/api/storage-config/'),
      headers: _headers(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(normalized),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return SourceCreateResponse.fromJson(data);
    }
    throw Exception('创建存储失败');
  }

  /// 获取指定存储的任务列表（已废弃，任务托盘下线后不再使用）

  /// 获取扫描任务状态
  Future<Map<String, dynamic>> getScanTaskStatus(String taskId) async {
    final res = await _client.get(
      _u('/api/scan/status/$taskId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('获取任务状态失败');
  }

  /// 获取通用任务状态
  ///
  /// 对应接口：`GET /api/tasks/{task_id}`
  Future<Map<String, dynamic>> getTaskStatus(String taskId) async {
    final res = await _client.get(
      _u('/api/tasks/$taskId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('获取任务状态失败');
  }

  Future<bool> testStorageConnection(String storageId) async {
    final sid = int.tryParse(storageId) ?? storageId;
    final res = await _client.get(
      _u('/api/storage-server/$sid/test'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return (data['success'] as bool?) ?? true;
    }
    return false;
  }

  Future<Map<String, dynamic>> getPlayUrl(int fileId) async {
    final res = await _client.get(
      _u('/api/media/play/$fileId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('获取播放地址失败');
  }

  Future<Map<String, dynamic>> refreshPlayUrl(int fileId) async {
    final res = await _client.post(
      _u('/api/media/play/refresh'),
      headers: _headers(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode({'file_id': fileId}),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return data;
    }
    throw Exception('刷新播放地址失败');
  }

  /// 获取指定文件的历史播放进度（用于续播）。
  ///
  /// 对应接口：`GET /api/playback/progress/{file_id}`，返回示例：
  /// `{ "position_ms": 0, "duration_ms": null }`。
  /// 仅使用 `position_ms`，未记录或请求失败时返回 null。
  Future<int?> getPlaybackProgress(int fileId) async {
    final res = await _client.get(
      _u('/api/playback/progress/$fileId'),
      headers: _headers(),
    );
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

  Future<List<RecentCardItem>> getRecent({
    int limit = 20,
    String? sort,
    String? dedup,
  }) async {
    final qs = <String>['limit=$limit'];
    if (sort != null && sort.isNotEmpty) qs.add('sort=$sort');
    if (dedup != null && dedup.isNotEmpty) qs.add('dedup=$dedup');
    final res = await _client.get(
      _u('/api/playback/recent?${qs.join('&')}'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list.map(RecentCardItem.fromApi).toList();
    }
    throw Exception('获取最近播放失败');
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
    final res = await _client.get(
      _u('/api/playback/recent$q'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list;
    }
    throw Exception('获取原始播放历史失败');
  }

  Future<void> deletePlaybackProgress(int fileId) async {
    final res = await _client.delete(
      _u('/api/playback/progress/$fileId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('删除播放进度失败');
  }

  Future<HomeCardsResponse> getLibraryHome() async {
    // 接入后端真实API：/api/media/cards/home
    final res = await _client.get(
      _u('/api/media/cards/home'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return HomeCardsResponse.fromJson(data);
    }
    throw Exception('获取首页内容失败');
  }

  Future<PagedMediaResponse> getLibraryCategoryItems(
    String categoryId, {
    int page = 1,
    int pageSize = 30,
  }) async {
    final res = await _client.get(
      _u(
        '/api/library/categories/$categoryId/items?page=$page&page_size=$pageSize',
      ),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return PagedMediaResponse.fromJson(data);
    }
    throw Exception('获取分类项失败');
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
    final res = await _client.get(
      _u('/api/media/cards?$queryString'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return FilterCardsResponse.fromJson(data);
    }
    throw Exception('搜索失败');
  }

  /// 获取媒体详情
  Future<MediaDetail> getMediaDetail(int id) async {
    final res = await _client.get(
      _u('/api/media/$id/detail'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return MediaDetail.fromJson(data);
    }
    throw Exception('获取媒体详情失败');
  }

  /// 获取指定文件的外挂字幕列表
  Future<List<Map<String, dynamic>>> getSubtitles(int fileId) async {
    final res = await _client.get(
      _u('/api/media/file/$fileId/subtitles'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final items =
          (data['items'] as List? ?? const []).cast<Map<String, dynamic>>();
      return items;
    }
    throw Exception('获取字幕失败');
  }

  /// 下载指定字幕文件内容
  Future<String> getSubtitleContent(int fileId, String path) async {
    final encodedPath = Uri.encodeComponent(path);
    final res = await _client.get(
      _u('/api/media/file/$fileId/subtitles/content?path=$encodedPath'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return (data['content'] as String?) ?? '';
    }
    throw Exception('下载字幕失败');
  }

  /// 获取指定文件所属剧集的选集列表
  Future<FileEpisodesResponse> getEpisodes(int fileId) async {
    final res = await _client.get(
      _u('/api/media/file/$fileId/episodes'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return FileEpisodesResponse.fromJson(data);
    }
    throw Exception('获取选集列表失败');
  }

  Future<List<SourceItem>> getSources({int page = 1, int size = 20}) async {
    final res = await _client.get(
      _u('/api/storage-config/'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      return list.map(SourceItem.fromJson).toList();
    }
    throw Exception('获取存储源失败');
  }

  Future<void> scanSource(String sourceId) async {
    final id = int.tryParse(sourceId);
    if (id != null) {
      await startScan(storageId: id);
      return;
    }
    throw Exception('无效的存储 ID');
  }

  Future<SourceItem> getSource(String sourceId) async {
    final res = await _client.get(
      _u('/api/storage-config/$sourceId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final wrapped = data['data'] as Map<String, dynamic>?;
      return SourceItem.fromJson(wrapped ?? data);
    }
    throw Exception('获取存储源失败');
  }

  Future<Map<String, dynamic>> getStorageDetail(String sourceId) async {
    final res = await _client.get(
      _u('/api/storage-config/$sourceId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final wrapped = data['data'] as Map<String, dynamic>?;
      return wrapped ?? data;
    }
    throw Exception('获取存储详情失败');
  }

  Future<void> updateSource(
    String sourceId,
    Map<String, dynamic> payload,
  ) async {
    final normalized = _normalizeWebdavPayload(payload);
    final res = await _client.put(
      _u('/api/storage-config/$sourceId'),
      headers: _headers(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(normalized),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('更新存储失败');
  }

  Future<void> toggleSource(String sourceId, {required bool enabled}) async {
    final id = int.tryParse(sourceId);
    if (id != null) {
      if (enabled) {
        await enableStorage(id);
      } else {
        await disableStorage(id);
      }
      return;
    }
    throw Exception('无效的存储 ID');
  }

  Future<void> deleteSource(String sourceId) async {
    final res = await _client.delete(
      _u('/api/storage-config/$sourceId'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw Exception('删除存储失败');
  }

  Future<String> loginWithEmail(
    String email,
    String password, {
    String? language,
  }) async {
    final payload = {'email': email, 'password': password};
    if (language != null) {
      payload['language'] = language;
    }
    final res = await _client.post(
      _u('/api/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
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
    throw Exception('登录失败');
  }

  Future<void> register(
    String email,
    String password, {
    String? language,
  }) async {
    final payload = {'email': email, 'password': password};
    if (language != null) {
      payload['language'] = language;
    }
    final res = await _client.post(
      _u('/api/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return;
    }
    throw Exception('注册失败');
  }

  /// 搜索 TMDB 媒体信息
  Future<Map<String, dynamic>> searchTmdb(
    String query,
    String type, {
    int page = 1,
  }) async {
    final encodedQuery = Uri.encodeComponent(query);
    // 新接口: /api/tmdb/search/tv?q=...
    // 假设 movie 接口为 /api/tmdb/search/movie?q=...
    final res = await _client.get(
      _u('/api/tmdb/search/$type?q=$encodedQuery&page=$page&language=zh-CN'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    throw Exception('搜索 TMDB 失败');
  }

  /// 获取 TMDB 剧集的所有季列表
  Future<Map<String, dynamic>> getTmdbTvSeasons(int tmdbTvId) async {
    // 新接口: /api/tmdb/tv/{id}?language=zh-CN
    final res = await _client.get(
      _u('/api/tmdb/tv/$tmdbTvId?language=zh-CN'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    throw Exception('获取季列表失败');
  }

  /// 获取 TMDB 某一季的所有集信息
  Future<Map<String, dynamic>> getTmdbTvSeasonEpisodes(
    int tmdbTvId,
    int seasonNumber,
  ) async {
    // 新接口: /api/tmdb/tv/{id}/season/{season}?language=zh-CN
    final res = await _client.get(
      _u('/api/tmdb/tv/$tmdbTvId/season/$seasonNumber?language=zh-CN'),
      headers: _headers(),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    throw Exception('获取集列表失败');
  }

  /// 保存手动匹配结果
  Future<Map<String, dynamic>> saveManualMatch(
    int mediaId,
    Map<String, dynamic> payload,
  ) async {
    final res = await _client.put(
      _u('/api/media/$mediaId/manual-match'),
      headers: _headers(headers: {'Content-Type': 'application/json'}),
      body: jsonEncode(payload),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    throw Exception('保存匹配结果失败');
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final authUserProvider = FutureProvider<Map<String, dynamic>?>((ref) async {
  final api = ref.watch(apiClientProvider);
  return api.getCurrentUser();
});
