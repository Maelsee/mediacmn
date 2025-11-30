class PlayableSource {
  final String uri;
  final Map<String, String>? headers;
  final String? format;
  final DateTime? expiresAt;
  final int? fileId;
  final int? startPositionMs;
  const PlayableSource({
    required this.uri,
    this.headers,
    this.format,
    this.expiresAt,
    this.fileId,
    this.startPositionMs,
  });
}
