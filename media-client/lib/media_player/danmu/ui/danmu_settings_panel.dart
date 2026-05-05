import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../provider/danmu_provider.dart';

class DanmuSettingsPanel extends ConsumerStatefulWidget {
  final String fileId;

  const DanmuSettingsPanel({super.key, required this.fileId});

  @override
  ConsumerState<DanmuSettingsPanel> createState() => _DanmuSettingsPanelState();
}

class _DanmuSettingsPanelState extends ConsumerState<DanmuSettingsPanel> {
  double _fontSize = 17;
  double _area = 0.3;
  double _speed = 70;
  double _opacity = 0.5;
  double _density = 0.3;
  double _timeOffset = 0;
  bool _initialized = false;

  @override
  Widget build(BuildContext context) {
    final engine = ref.read(danmuProvider(widget.fileId).notifier).engine;
    final size = MediaQuery.of(context).size;
    final isLandscape = size.width > size.height;

    if (engine == null) {
      return const SizedBox.shrink();
    }

    // 从 engine 读取初始值（仅一次）
    if (!_initialized) {
      _fontSize = engine.fontSize;
      _area = engine.area;
      _speed = engine.speed;
      _opacity = engine.opacity;
      _density = engine.density;
      _timeOffset = engine.timeOffset;
      _initialized = true;
    }

    // 滑块列表内容
    final sliders = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildSliderRow(
          label: '字体大小',
          value: _fontSize,
          min: 12,
          max: 32,
          divisions: 20,
          format: (v) => '${v.round()}',
          onChanged: (v) {
            setState(() => _fontSize = v);
            engine.setFontSize(v);
          },
        ),
        _buildSliderRow(
          label: '显示区域',
          value: _area,
          min: 0.0,
          max: 1.0,
          divisions: 10,
          format: (v) => '${(v * 100).round()}%',
          onChanged: (v) {
            setState(() => _area = v);
            engine.setArea(v);
          },
        ),
        _buildSliderRow(
          label: '滚动速度',
          value: _speed,
          min: 20,
          max: 200,
          divisions: 18,
          format: (v) => '${v.round()}px/s',
          onChanged: (v) {
            setState(() => _speed = v);
            engine.setSpeed(v);
          },
        ),
        _buildSliderRow(
          label: '透明度',
          value: _opacity,
          min: 0.0,
          max: 1.0,
          divisions: 10,
          format: (v) => '${(v * 100).round()}%',
          onChanged: (v) {
            setState(() => _opacity = v);
            engine.setOpacity(v);
          },
        ),
        _buildSliderRow(
          label: '弹幕密度',
          value: _density,
          min: 0.1,
          max: 1.0,
          divisions: 9,
          format: (v) => '${(v * 100).round()}%',
          onChanged: (v) {
            setState(() => _density = v);
            engine.setDensity(v);
          },
        ),
        _buildSliderRow(
          label: '时间偏移',
          labelSuffix: _timeOffset != 0 ? ' 重置' : null,
          onLabelTap: _timeOffset != 0
              ? () {
                  setState(() => _timeOffset = 0);
                  engine.setTimeOffset(0);
                }
              : null,
          value: _timeOffset,
          min: -30.0,
          max: 30.0,
          divisions: 60,
          format: (v) => '${v >= 0 ? '+' : ''}${v.toStringAsFixed(1)}s',
          onChanged: (v) {
            setState(() => _timeOffset = v);
            engine.setTimeOffset(v);
          },
        ),
      ],
    );

    // 构建头部（标题 + 拖拽条）
    Widget buildHeader() => Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!isLandscape)
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
            const Text('弹幕设置',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold)),
            SizedBox(height: isLandscape ? 16 : 12),
          ],
        );

    // 竖屏限制高度为屏幕 50%（与其他面板一致），横屏自适应
    final panelHeight = isLandscape ? null : size.height * 0.5;

    return Container(
      height: panelHeight,
      padding: EdgeInsets.fromLTRB(20, isLandscape ? 24 : 12, 20, 24),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E1E),
        borderRadius: isLandscape
            ? null
            : const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          buildHeader(),
          Expanded(
            child: SingleChildScrollView(child: sliders),
          ),
        ],
      ),
    );
  }

  Widget _buildSliderRow({
    required String label,
    required double value,
    required double min,
    required double max,
    required int divisions,
    required String Function(double) format,
    required ValueChanged<double> onChanged,
    String? labelSuffix,
    VoidCallback? onLabelTap,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          SizedBox(
            width: 72,
            child: GestureDetector(
              onTap: onLabelTap,
              child: Text.rich(
                TextSpan(
                  text: label,
                  style: const TextStyle(color: Colors.white70, fontSize: 14),
                  children: labelSuffix != null
                      ? [
                          TextSpan(
                            text: labelSuffix,
                            style: const TextStyle(
                                color: Color(0xFFFFE796), fontSize: 12),
                          ),
                        ]
                      : null,
                ),
              ),
            ),
          ),
          Expanded(
            child: SliderTheme(
              data: SliderThemeData(
                activeTrackColor: const Color(0xFFFFE796),
                inactiveTrackColor: Colors.white24,
                thumbColor: const Color(0xFFFFE796),
                overlayColor: const Color(0xFFFFE796).withAlpha(0x33),
                trackHeight: 3,
                thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
              ),
              child: Slider(
                value: value.clamp(min, max),
                min: min,
                max: max,
                divisions: divisions,
                onChanged: onChanged,
              ),
            ),
          ),
          SizedBox(
            width: 56,
            child: Text(format(value),
                textAlign: TextAlign.right,
                style: const TextStyle(color: Colors.white54, fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
