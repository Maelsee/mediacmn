import 'package:media_kit/media_kit.dart';

/// 轨道名称格式化工具。
///
/// 用于统一音轨和字幕轨道的显示名称生成逻辑。
class TrackFormatter {
  const TrackFormatter._();

  /// 获取音轨展示名称。
  static String audio(AudioTrack track) {
    if (track.id == 'auto') return '自动';
    if (track.id == 'no') return '无';

    return _format(
      id: track.id,
      title: track.title,
      language: track.language,
      fallbackPrefix: '音轨',
    );
  }

  /// 获取字幕展示名称。
  static String subtitle(SubtitleTrack track) {
    if (track.id == 'auto') return '自动';
    if (track.id == 'no') return '无';

    return _format(
      id: track.id,
      title: track.title,
      language: track.language,
      fallbackPrefix: '字幕',
    );
  }

  /// 通用格式化逻辑
  static String _format({
    required String id,
    String? title,
    String? language,
    required String fallbackPrefix,
  }) {
    // 优先使用 flow analysis 避免 ! 强转
    final safeTitle = (title != null && title.isNotEmpty) ? title : null;
    final safeLanguage =
        (language != null && language.isNotEmpty) ? language : null;

    final langName =
        safeLanguage != null ? _getLanguageName(safeLanguage) : null;

    // 1. 只有标题 -> 标题
    // 2. 只有语言 -> 语言
    // 3. 都有 -> 标题 (语言)  (如果标题已包含语言名则不重复显示)
    // 4. 都无 -> 前缀 ID

    if (safeTitle != null) {
      if (langName != null && !safeTitle.contains(langName)) {
        return '$safeTitle ($langName)';
      }
      return safeTitle;
    }

    if (langName != null) {
      return langName;
    }

    // 尝试解析 ID 是否为数字，如果是则显示 "前缀 N"
    // media_kit 的 ID 通常是 "0", "1" 等字符串
    if (int.tryParse(id) != null) {
      return '$fallbackPrefix ${int.parse(id) + 1}'; // 索引通常从0开始，显示习惯+1
    }

    return '$fallbackPrefix $id';
  }

  static String _getLanguageName(String code) {
    final c = code.toLowerCase();
    // 优先全匹配
    if (_languageMap.containsKey(c)) return _languageMap[c]!;

    // 尝试取前3位 (ISO 639-2)
    if (c.length > 3) {
      final short = c.substring(0, 3);
      if (_languageMap.containsKey(short)) return _languageMap[short]!;
    }

    // 尝试取前2位 (ISO 639-1)
    if (c.length > 2) {
      final short = c.substring(0, 2);
      if (_languageMap.containsKey(short)) return _languageMap[short]!;
    }

    return code;
  }

  // ISO 639-1/2 常用语言映射表
  static const _languageMap = {
    // 中文
    'chi': '中文', 'zho': '中文', 'zh': '中文', 'cmn': '普通话', 'chn': '中文',
    'yue': '粤语', 'can': '粤语',
    'wuu': '吴语',
    'min': '闽南语',

    // 英语
    'eng': '英语', 'en': '英语', 'usa': '英语', 'gbr': '英语',

    // 日韩
    'jpn': '日语', 'ja': '日语',
    'kor': '韩语', 'ko': '韩语',

    // 欧洲常用
    'fre': '法语', 'fra': '法语', 'fr': '法语',
    'ger': '德语', 'deu': '德语', 'de': '德语',
    'spa': '西班牙语', 'es': '西班牙语',
    'ita': '意大利语', 'it': '意大利语',
    'rus': '俄语', 'ru': '俄语',
    'por': '葡萄牙语', 'pt': '葡萄牙语',
    'nld': '荷兰语', 'dut': '荷兰语', 'nl': '荷兰语',
    'pol': '波兰语', 'pl': '波兰语',
    'swe': '瑞典语', 'sv': '瑞典语',
    'dan': '丹麦语', 'da': '丹麦语',
    'fin': '芬兰语', 'fi': '芬兰语',
    'nor': '挪威语', 'no': '挪威语',
    'ukr': '乌克兰语', 'uk': '乌克兰语',

    // 东南亚/其他
    'vie': '越南语', 'vi': '越南语',
    'tha': '泰语', 'th': '泰语',
    'ind': '印尼语', 'id': '印尼语',
    'ms': '马来语', 'may': '马来语', 'msa': '马来语',
    'ara': '阿拉伯语', 'ar': '阿拉伯语',
    'hin': '印地语', 'hi': '印地语',
    'tur': '土耳其语', 'tr': '土耳其语',

    // 特殊
    'und': '未知语言',
    'mul': '多语言',
  };
}
