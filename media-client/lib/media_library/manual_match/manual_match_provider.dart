import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import 'manual_match_notifier.dart';
import 'manual_match_state.dart';

final manualMatchProvider = StateNotifierProvider.family
    .autoDispose<ManualMatchNotifier, ManualMatchState, int>((ref, mediaId) {
  final api = ref.read(apiClientProvider);
  return ManualMatchNotifier(api, mediaId);
});
