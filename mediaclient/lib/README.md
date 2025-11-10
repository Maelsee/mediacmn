# 前端模块说明（用户登录流程）

本说明记录 Flutter 前端中“我的/用户”模块的实现与使用方式。

## 模块结构

- pages/user/user_profile.dart：我的页面（未登录与已登录态）
- pages/user/login_phone.dart：手机号输入页（协议勾选）
- pages/user/login_code.dart：验证码输入页（6位框、倒计时、重新发送）
- state/auth_scope.dart：认证状态管理（ChangeNotifier + InheritedNotifier）
- main.dart：在 MaterialApp 的 `home` 外层注入 `AuthScope`

## 交互流程

1. 在底部导航点击“用户”进入 `UserProfilePage`。
2. 未登录时展示提示卡片，点击“登录”跳转到 `LoginPhonePage`。
3. 输入 11 位手机号并勾选协议后，点击“登录”：
   - `AuthController.sendCode(phone)` 启动 60s 倒计时并进入验证码页。
4. 在 `LoginCodePage` 输入 6 位验证码：
   - Demo 中验证码为固定值 `123456`；校验通过后登录成功并返回首页。
5. 已登录态显示头像与遮掩手机号（如 `156******04`），底部包含“退出登录”。

## 运行与调试

在项目根的 mediaclient 下：

```bash
flutter clean
flutter pub get
flutter run -d web-server --web-hostname=localhost --web-port=5200
```

浏览器访问 http://localhost:5200/，可使用 `r` 热重载。

## 设计与错误处理

- 登录按钮禁用：未勾选协议或手机号非 11 位时，按钮不可点击。
- 验证码倒计时：`resendSeconds > 0` 时“重新获取”按钮禁用；倒计时结束后可重新发送。
- 校验错误：验证码非 `123456` 时通过 SnackBar 显示“验证码错误，请重试”。
- 退出登录：`AuthController.logout()` 清理状态并回到未登录页。

## 扩展到后端

将 `AuthController.sendCode/verifyCode` 接入后端 FastAPI 的短信服务接口即可实现真实登录：

- `POST /api/auth/send_code`：入参手机号，返回发送结果与过期时间。
- `POST /api/auth/verify_code`：入参手机号+验证码，返回用户会话或 JWT。

接入后，将本地固定码逻辑替换为服务端校验，并在成功后保存用户信息和会话。