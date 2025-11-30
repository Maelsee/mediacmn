# API变更记录

## 剧集单集数据增强API变更

### 新增功能
基于TMDB单集API，为剧集提供完整的单集元数据支持。

### 数据库模型变更

#### EpisodeExt表新增字段
```sql
-- 新增字段
ALTER TABLE tv_episode_ext ADD COLUMN overview TEXT;
ALTER TABLE tv_episode_ext ADD COLUMN still_path VARCHAR(500);
ALTER TABLE tv_episode_ext ADD COLUMN vote_count INTEGER;
ALTER TABLE tv_episode_ext ADD COLUMN episode_type VARCHAR(50);

-- 新增约束和索引
ALTER TABLE tv_episode_ext ADD CONSTRAINT uq_episode_per_user 
    UNIQUE (user_id, series_core_id, season_number, episode_number);
CREATE INDEX idx_episode_lookup ON tv_episode_ext 
    (user_id, series_core_id, season_number, episode_number);
```

### 新增TMDB API端点

#### 单集详情端点
```http
GET /tv/{series_id}/season/{season_number}/episode/{episode_number}
参数：
  - language: 语言代码 (默认: zh-CN)
返回：
  - 单集标题、简介、播出日期、时长、评分等
```

#### 单集演职员端点
```http
GET /tv/{series_id}/season/{season_number}/episode/{episode_number}/credits
参数：
  - language: 语言代码 (默认: zh-CN)
返回：
  - cast: 演员列表
  - crew: 制作人员列表
```

#### 单集剧照端点
```http
GET /tv/{series_id}/season/{season_number}/episode/{episode_number}/images
参数：
  - language: 语言代码 (默认: zh-CN)
返回：
  - stills: 剧照列表
```

### 数据获取流程变更

#### 优化前流程
```
1. /search/tv - 搜索剧集
2. /tv/{id} - 获取剧集详情
3. 保存基础单集信息（仅季号、集号）
```

#### 优化后流程
```
1. /search/tv - 搜索剧集
2. /tv/{id}/season/{s}/episode/{e} - 获取单集详情（新增）
3. /tv/{id}/season/{s}/episode/{e}/credits - 获取单集演职员（新增）
4. /tv/{id}/season/{s}/episode/{e}/images - 获取单集剧照（新增）
5. 保存完整单集信息（标题、简介、剧照、评分等）
```

### 数据映射关系

#### EpisodeExt字段映射
| 数据库字段 | TMDB字段 | 说明 |
|------------|----------|------|
| title | name | 单集标题 |
| overview | overview | 单集简介 |
| aired_date | air_date | 播出日期 |
| runtime | runtime | 时长（分钟） |
| rating | vote_average | 平均评分 |
| vote_count | vote_count | 评分数量 |
| still_path | still_path | 剧照路径 |
| episode_type | episode_type | 集类型 |

#### Artwork数据映射
| 数据库字段 | TMDB字段 | 说明 |
|------------|----------|------|
| type | - | 固定为'backdrop' |
| url | file_path | 完整图片URL |
| width | width | 图片宽度 |
| height | height | 图片高度 |
| language | iso_639_1 | 语言代码 |
| rating | vote_average | 图片评分 |
| vote_count | vote_count | 图片评分数量 |

#### Credit数据映射
| 数据库字段 | TMDB字段 | 说明 |
|------------|----------|------|
| type | - | 固定为'actor' |
| name | name | 演员姓名 |
| role | character | 饰演角色 |
| order | order | 排序 |
| image_url | profile_path | 头像URL |

### 性能影响

#### 网络请求
- 新增3个API调用，增加约200-500ms延迟
- 采用异步并发调用，总体影响可控

#### 数据库性能
- 新增索引提升查询性能
- 唯一约束保证数据一致性
- 数据量增长约30-50%

### 错误处理

#### 降级策略
```python
# 单集API失败时回退到剧集详情
try:
    episode_details = await get_episode_details(...)
except Exception:
    # 回退到剧集级详情
    series_details = await get_details(...)
```

#### 数据完整性
- 部分字段缺失时保持为空值
- API调用失败不影响整体流程
- 事务处理保证数据一致性

### 使用示例

#### 查询单集信息
```python
# 获取树影迷宫S01E02的完整信息
episode = session.query(EpisodeExt).filter(
    EpisodeExt.series_core_id == series_id,
    EpisodeExt.season_number == 1,
    EpisodeExt.episode_number == 2
).first()

# 返回数据
{
    "title": "死者通话记录查到赶鹅",
    "overview": "第二集剧情详细介绍...",
    "aired_date": "2025-11-01",
    "runtime": 54,
    "rating": 0.0,
    "vote_count": 0,
    "still_path": "/lb8RMfNKudt4H3VvVHDCITDVxCY.jpg",
    "episode_type": "standard"
}
```

#### 查询单集剧照
```python
# 获取单集剧照
stills = session.query(Artwork).filter(
    Artwork.core_id == episode_core_id,
    Artwork.type == 'backdrop'
).all()
```

#### 查询单集演职员
```python
# 获取单集演职员
credits = session.query(Credit).filter(
    Credit.core_id == episode_core_id,
    Credit.type == 'actor'
).order_by(Credit.order).all()
```

## 电影合集功能API变更

### 新增功能
基于TMDB合集数据，提供完整的电影合集管理功能。

### 新增数据库模型

#### Collection表
```sql
CREATE TABLE collections (
    id INTEGER PRIMARY KEY,          -- TMDB合集ID
    name VARCHAR(500) NOT NULL,      -- 合集名称
    poster_path VARCHAR(500),        -- 海报路径
    backdrop_path VARCHAR(500),     -- 背景图路径
    overview TEXT,                    -- 合集简介
    created_at TIMESTAMP,             -- 创建时间
    updated_at TIMESTAMP              -- 更新时间
);
```

### 新增API端点

#### 合集列表
```http
GET /api/collections/
参数：
  - skip: 跳过数量 (默认: 0)
  - limit: 返回数量 (默认: 100)
返回：
  - 合集列表，包含电影数量统计
```

#### 合集详情
```http
GET /api/collections/{collection_id}
参数：
  - collection_id: 合集ID
返回：
  - 合集详细信息
```

#### 合集电影列表
```http
GET /api/collections/{collection_id}/movies
参数：
  - collection_id: 合集ID
  - skip: 跳过数量 (默认: 0)
  - limit: 返回数量 (默认: 100)
返回：
  - 合集中的电影列表
```

### 数据获取流程

#### TMDB合集数据提取
```
1. /movie/{id} - 获取电影详情
2. 提取belongs_to_collection字段
3. 保存合集信息到Collection表
4. 更新MovieExt的collection_id字段
```

### 数据库关系

#### 电影与合集关联
```sql
-- MovieExt表新增字段
ALTER TABLE movie_ext ADD COLUMN collection_id INTEGER;
ALTER TABLE movie_ext ADD CONSTRAINT fk_movie_collection 
    FOREIGN KEY (collection_id) REFERENCES collections(id);
```

### 使用示例

#### 查询用户合集
```python
# 获取用户所有合集
collections = session.query(Collection, func.count(MovieExt.id).label('movie_count'))
    .join(MovieExt, Collection.id == MovieExt.collection_id)
    .filter(MovieExt.user_id == user_id)
    .group_by(Collection.id)
    .all()
```

#### 查询合集中的电影
```python
# 获取合集中的电影
movies = session.query(MediaCore, MovieExt)
    .join(MovieExt, MediaCore.id == MovieExt.core_id)
    .filter(MovieExt.collection_id == collection_id)
    .filter(MovieExt.user_id == user_id)
    .all()
```