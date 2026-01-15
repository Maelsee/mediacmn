import 'package:flutter_test/flutter_test.dart';

void main() {
  // 用于保证 flutter test 在工程内可正常执行的基础用例。
  test('基础 smoke 测试', () {
    expect(1 + 1, 2);
  });
}
