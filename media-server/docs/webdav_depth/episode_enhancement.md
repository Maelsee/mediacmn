# 剧集单集数据增强方案

## 概述
基于真实TMDB API数据，对剧集单集数据存储和获取进行全面增强，提供更丰富的单集元数据支持。

## 改进内容

### 1. 数据库模型增强

#### EpisodeExt模型扩展
新增字段：
- `overview: Optional[str]` - 单集剧情简介
- `still_path: Optional[str]` - 单集剧照路径  
- `vote_count: Optional[int]` - 评分数量
- `episode_type: Optional[str]` - 集类型(standard/finale/special)

新增约束：
- 唯一约束: `(user_id, series_core_id, season_number, episode_number)`
- 复合索引: `(user_id, series_core_id, season_number, episode_number)`

### 2. TMDB刮削器增强

#### 新增API端点支持
- `GET /tv/{series_id}/season/{season_number}/episode/{episode_number}` - 单集详情
- `GET /tv/{series_id}/season/{season_number}/episode/{episode_number}/credits` - 单集演职员
- `GET /tv/{series_id}/season/{season_number}/episode/{episode_number}/images` - 单集剧照

#### 新增方法
```python
async def get_episode_details(self, series_id: str, season_number: int, 
                              episode_number: int, language: str) -> Optional[ScraperResult]
```

返回数据包含：
- 单集标题、简介、播出日期、时长
- 单集剧照路径(still_path)
- 单集演职员信息(cast/crew)
- 单集剧照集合(stills)
- 评分和投票数

### 3. 元数据丰富流程优化

#### 处理逻辑改进
1. **优先获取单集详情**: 当检测到tv_episode且有时，优先调用单集API
2. **数据映射**: 将TMDB单集数据完整映射到EpisodeExt模型
3. **艺术作品存储**: 单集剧照存储到Artwork模型，类型为backdrop
4. **演职员存储**: 单集演职员存储到Credit模型

#### 数据填充映射
```python
# EpisodeExt数据填充
ee.title = metadata.episode_title          # 单集标题
ee.overview = metadata.overview           # 单集简介  
ee.aired_date = metadata.release_date     # 播出日期
ee.runtime = metadata.runtime              # 时长
ee.rating = metadata.rating               # 评分
ee.vote_count = metadata.vote_count        # 评分数量
ee.still_path = still_path                # 剧照路径
ee.episode_type = episode_type            # 集类型
```

## 实际效果对比

### 优化前（当前状态）
对于《树影迷宫.S01E02.2025.mkv》：
```json
{
  "title": "S01E02",
  "episode_number": 2,
  "season_number": 1,
  "aired_date": null,
  "runtime": null,
  "rating": null,
  "overview": null,
  "still_path": null
}
```

### 优化后（预期效果）
```json
{
  "title": "死者通话记录查到赶鹅",
  "episode_number": 2,
  "season_number": 1,
  "aired_date": "2025-11-01",
  "runtime": 54,
  "rating": 0.0,
  "vote_count": 0,
  "overview": "第二集剧情详细介绍...",
  "still_path": "/lb8RMfNKudt4H3VvVHDCITDVxCY.jpg",
  "episode_type": "standard"
}
```

## 技术实现细节

### 文件变更
1. **models/media_models.py** - EpisodeExt模型扩展
2. **services/scraper/tmdb.py** - 单集数据获取方法
3. **services/media/metadata_enricher.py** - 单集数据处理逻辑

### API端点调用顺序
1. `/search/tv` - 搜索剧集
2. `/tv/{id}/season/{season}/episode/{episode}` - 获取单集详情（新增）
3. `/tv/{id}/season/{season}/episode/{episode}/credits` - 获取单集演职员（新增）
4. `/tv/{id}/season/{season}/episode/{episode}/images` - 获取单集剧照（新增）

### 数据存储策略
- **单集核心信息**: EpisodeExt表存储
- **单集剧照**: Artwork表存储，类型为backdrop
- **单集演职员**: Credit表存储，关联到单集core_id
- **单集剧照路径**: EpisodeExt.still_path冗余存储，便于快速访问

## 性能考虑
- 新增API调用会增加网络请求时间，但提供丰富数据
- 数据库索引优化查询性能
- 唯一约束防止重复数据

## 后续扩展
- 支持单集评分聚合统计
- 单集播放状态跟踪
- 单集收藏/观看历史功能
- 基于单集数据的推荐算法