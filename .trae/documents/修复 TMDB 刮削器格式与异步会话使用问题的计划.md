# 问题概览
- 非法上下文用法：`async with self._get_session() as session`（`_get_session`已改为异步返回会话对象，不再可直接 `async with` 其协程）。
- 导入缺失：使用了 `timedelta`，但顶部仅 `from datetime import datetime`。
- 缩进错误：`search/_get_credits/_get_artworks/get_episode_details` 中存在错位缩进，易引发 `IndentationError`。
- 会话复用策略与上下文：共享会话不应每次在 `async with` 中关闭，调用应统一为 `session = await self._get_session()` + `async with session.get(...)`。

# 修复方案
1. 导入修复：顶部改为 `from datetime import datetime, timedelta`。
2. 统一会话用法：
   - 将所有 `async with self._get_session() as session:` 替换为 `session = await self._get_session()`。
   - 保留请求级 `async with session.get(...)`，不关闭共享会话。
3. 缩进修复：
   - `search(...)` 中 `session = await self._get_session()` 后的日志与请求代码块去除多余缩进。
   - `_get_credits(...)`、`_get_artworks(...)`、`get_episode_details(...)` 同步调整缩进，并在各请求前后保持计数更新。
4. 轻度一致性校验：确保所有新增计数（`_req_count/_fail_count`）位置正确并不影响逻辑；保留现有功能行为不变。

# 验收标准
- 模块可正常导入与运行异步方法；不再报 `IndentationError` 或 `NameError: timedelta`。
- 所有 HTTP 请求使用共享会话；无不当关闭导致的资源问题。
- 现有刮削功能（搜索、详情、演职员、图片、单集）在接口契约上保持一致。