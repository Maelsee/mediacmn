# 文档生成计划（不落地）

## 目标
- 输出“修改后的数据库架构设计详情”至 `docs/media_card_architecture_design.md`，覆盖：
  - 字段作用与意义（逐实体、逐字段）
  - 完整 ER 图（Mermaid 代码块）与不可视环境 ASCII 关系图
  - 列表与详情查询映射与索引建议
  - 版本管理（电影按文件、剧集按季、无季剧季1）与解析数据流说明

## 内容结构
- 概览与设计原则：统一作品层、版本单位、无季剧季1
- 实体模型与字段说明（逐表）：
  - MediaCore（作品层）字段与索引（models/media_models.py:36-61）
  - MediaVersion（版本层）字段与索引（models/media_models.py:63-77 扩展）
  - SeasonExt（季层）字段与索引（models/media_models.py:125-145 扩展）
  - EpisodeExt（集层）字段与索引（models/media_models.py:147-169 扩展）
  - FileAsset（文件层）字段与索引（models/media_models.py:171-205 扩展）
  - Artwork（图片层）字段与索引（models/media_models.py:209-215 扩展）
  - ExternalID、Genre、MediaCoreGenre、Person、Credit、ScanJob 概览
- 关系图：
  - ASCII 关系图（保证显示）
  - Mermaid ER 图（完整实体与关系）
- 查询映射：列表与详情的典型查询与筛选维度；索引建议与排序策略
- 解析与归属数据流：扫描轻量、刮削深度、版本归属与 preferred 选择
- 迁移步骤与一致性校验：字段灰度新增、无季剧季1、版本指纹与文件指纹、覆盖率计算

## 交付方式
- 在 `docs/media_card_architecture_design.md` 追加/重写成系统化章节：
  - 保留原文中的视图示意作为参考（若存在），并新增完整字段与关系章节
  - 插入 ASCII 与 Mermaid ER 双方案，确保“ER 不可视环境”可阅读

## 验收要点
- 文档包含所有媒体相关实体与关系，字段含义清晰、可用于前端与数据迁移
- ASCII 图与 Mermaid 图一致；查询与索引建议可直接指导实现

> 确认后将生成并写入上述文档文件，保持可读性与完整性。