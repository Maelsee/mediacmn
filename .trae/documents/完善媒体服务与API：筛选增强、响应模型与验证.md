## 目标
- 增强筛选能力（类型/分类/年份区间/地区），统一响应结构。
- 为 `media_service.py` 方法补充响应模型与注释，优化字段映射与性能。
- 更新 `routes_media.py` 路由入参解析与返回模型，确保前后端一致。
- 添加基本验证与测试用例（若存在测试框架），确保接口稳定。

## 拟改动
1) 服务层增强（media_service.py）
- 为 `list_media_cards` 增加：
  - 更稳健的 `countries` 条件（若存储为字符串列表或逗号字符串，改为 LIKE/IN 方式）
  - 可选排序参数（release_date/rating/updated_at）与默认降序。
- 对字段来源统一：
  - 电影：release_date 从 `MovieExt.release_date`；评分优先 MovieExt.rating
  - 剧集：release_date 从 `SeasonExt.aired_date` 首季；评分可取 `TVSeriesExt.rating`（若有）
- 返回统一响应模型（Pydantic）：MediaCard/MediaCardsResponse

- 为 `get_media_detail` 增加：
  - 电影与剧集的结构统一，明确必填与可选字段；
  - 追加背景/海报为 fallback（poster/backdrop）说明；
  - 版本与路径统一提取；
  - 响应模型（Pydantic）：MediaDetail

2) 路由层（routes_media.py）
- `GET /media/cards`：入参增加排序与更明确类型枚举；返回 `MediaCardsResponse`
- `GET /media/{id}/detail`：返回 `MediaDetail`
- 注释与 OpenAPI 描述完善

3) 文档与注释
- 为服务方法添加 docstring 注释，说明参数/返回/行为
- 在开发文档中记录筛选字段含义与映射来源（简要）

4) 验证
- 手动调用两个路由进行验证（示例参数），检查分页、筛选与详情字段完整性
- 若测试框架可用，添加轻量测试用例（列表过滤、详情存在）

## 不改动
- 保留现有文件列表与文件详情路由，实现独立；后续再统一风格

## 交付标准
- 列表返回卡片字段完整且筛选生效；
- 详情返回电影/剧集完整字段；
- 路由入参/出参清晰，注释完善；
- 基本验证通过。