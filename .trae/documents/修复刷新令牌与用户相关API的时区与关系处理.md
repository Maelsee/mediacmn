## 问题诊断
- 错误来源：`models/refresh_token.py:30` 比较 `datetime.now(timezone.utc)` 与 `self.expires_at` 时抛出 `TypeError: can't compare offset-naive and offset-aware datetimes`
- 根因：某些刷新令牌记录的 `expires_at` 为无时区（naive）时间；代码使用带时区（UTC）的当前时间进行比较，导致不可比较
- 伴随问题：`services/refresh_token_service.py:81` 使用 `refresh_token.user` 获取用户，但模型关系已注释，可能返回 `None`

## 修复方案
### 1) 修复刷新令牌过期判断的时区一致性
- 修改 `models/refresh_token.py:28-35` 的 `is_expired`：在比较前统一将 `expires_at` 规范为 UTC-aware
- 变更示意：
```
now = datetime.now(timezone.utc)
expires = self.expires_at
if expires.tzinfo is None:
    expires = expires.replace(tzinfo=timezone.utc)
return now > expires
```

### 2) 稳健获取用户对象，避免关系为空
- 修改 `services/refresh_token_service.py:80-88`：改用 `session.get(User, refresh_token.user_id)` 显式加载用户，避免依赖被移除的关系字段
- 变更示意：
```
user = session.get(User, refresh_token.user_id)
if not user:
    raise ValueError("用户不存在")
```

### 3) 保持端到端一致的时区写入
- 创建/轮换刷新令牌时已经使用 `datetime.now(timezone.utc)`（`create_refresh_token`, `revoke_*`, `cleanup_expired_tokens` 均如此）
- 保持这些写入逻辑不变；新增对读取比较的健壮性（第1步）即可解决现有数据的混合时区问题

### 4) API层返回语义一致
- `api/routes_auth.py:77-111` 已在 `ValueError` 时返回 401；修复后该接口将不再抛 500
- 无需变更响应契约，仅确保内部异常不再发生

## 测试与验证
### 单元测试
- 为 `RefreshToken.is_expired` 添加测试：
  - `expires_at` 为 naive UTC（无 tzinfo）：应能正确比较并返回过期/未过期
  - `expires_at` 为 aware UTC：行为一致
- 为 `RefreshTokenService.refresh_access_token` 添加测试：
  - 有效令牌：返回新的 `access_token`，在启用轮换时可取到新的 `refresh_token`
  - 过期/吊销令牌：返回 401（通过路由层）

### 集成测试
- 调用 `/api/auth/login` 获取刷新令牌；随后：
  - `/api/auth/refresh` 使用有效刷新令牌返回 200
  - 使用手工构造的过期（或吊销）令牌返回 401
- 复跑 `corrected_system_test.py`，确保刷新接口不再出现 500

## 数据兼容与可选修复
- 若历史数据存在大量 naive `expires_at`：
  - 可选一次性迁移：将 `refresh_tokens.expires_at` 统一设为 UTC-aware（更新时区为 `timezone.utc`）
  - 由于第1步已在读取时做规范化，迁移不是强制项

## 交付变更列表
- 修改文件：
  - `models/refresh_token.py:28-35` 统一时区比较
  - `services/refresh_token_service.py:80-88` 显式加载用户
- 新增测试：
  - `tests/test_refresh_token_timezone.py`
  - `tests/test_auth_refresh_endpoint.py`

## 风险与回滚
- 风险低：逻辑仅增强健壮性与关系加载明确化
- 回滚：如需回退，恢复原有两处代码即可

请确认以上方案，我将按步骤实施修复并补充测试，随后验证接口行为与系统稳定性。