# 电影合集功能实现分析

## 当前实现状态

### 1. 数据库模型
在 `MovieExt` 模型中有一个字段：
```python
collection_id: Optional[int] = Field(default=None, description="所属电影合集ID")
```

### 2. 数据来源 - TMDB API
从TMDB API的响应中可以看到合集数据：

**示例：复仇者联盟4的合集数据**
```json
{
    "belongs_to_collection": {
        "id": 86311,
        "name": "复仇者联盟（系列）",
        "poster_path": "/8HxgBGdTI8Gviy2dKPW0iANYBZx.jpg",
        "backdrop_path": "/zuW6fOiusv4X9nnW3paHGfXcSll.jpg"
    }
}
```

**示例：无合集的电影**
```json
{
    "belongs_to_collection": null
}
```

### 3. 当前实现的问题

#### ❌ 缺失的功能：
1. **无Collection模型** - 没有创建collections表来存储合集信息
2. **无数据提取** - TMDB刮削器没有提取`belongs_to_collection`字段
3. **无数据处理** - metadata_enricher没有处理合集数据
4. **无API接口** - 没有提供查询合集的API端点

## 完整实现方案

### 1. 创建Collection模型

```python
class Collection(SQLModel, table=True):
    """电影合集模型"""
    __tablename__ = "collections"
    
    id: int = Field(primary_key=True, description="合集ID（来自TMDB）")
    name: str = Field(description="合集名称")
    poster_path: Optional[str] = Field(default=None, description="海报路径")
    backdrop_path: Optional[str] = Field(default=None, description="背景图路径")
    
    # 可以添加更多字段如：overview, created_at, updated_at等
```

### 2. 修改TMDB刮削器

在 `services/scraper/tmdb.py` 的 `_convert_details` 方法中添加：

```python
def _convert_details(self, data: Dict, media_type: MediaType, language: str) -> Optional[ScraperResult]:
    # ... 现有代码 ...
    
    # 添加合集信息到ScraperResult
    if data.get("belongs_to_collection"):
        collection = data["belongs_to_collection"]
        result.collection = {
            "id": collection.get("id"),
            "name": collection.get("name"),
            "poster_path": collection.get("poster_path"),
            "backdrop_path": collection.get("backdrop_path")
        }
    
    return result
```

### 3. 修改ScraperResult模型

在 `services/scraper/base.py` 的 `ScraperResult` 中添加：

```python
@dataclass
class ScraperResult:
    # ... 现有字段 ...
    
    # 合集信息
    collection: Optional[Dict] = None  # 新增字段
```

### 4. 修改metadata_enricher

在 `services/media/metadata_enricher.py` 的 `_save_metadata_to_db_sync` 方法中添加：

```python
def _save_metadata_to_db_sync(self, session, media_file, metadata) -> bool:
    # ... 现有代码 ...
    
    # 保存合集信息
    if hasattr(metadata, 'collection') and metadata.collection:
        collection_data = metadata.collection
        
        # 创建或更新合集
        collection = session.query(Collection).filter(Collection.id == collection_data["id"]).first()
        if not collection:
            collection = Collection(
                id=collection_data["id"],
                name=collection_data["name"],
                poster_path=collection_data.get("poster_path"),
                backdrop_path=collection_data.get("backdrop_path")
            )
            session.add(collection)
        
        # 更新电影的合集ID
        movie_ext.collection_id = collection.id
    
    return True
```

### 5. 创建API端点

在API路由中添加：

```python
# 获取用户的所有合集
GET /api/collections/

# 获取合集详情
GET /api/collections/{collection_id}

# 获取合集中的电影
GET /api/collections/{collection_id}/movies
```

## 使用示例

### 查询所有合集
```bash
curl -X GET "http://localhost:8000/api/collections/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

响应示例：
```json
[
  {
    "id": 86311,
    "name": "复仇者联盟（系列）",
    "poster_path": "/8HxgBGdTI8Gviy2dKPW0iANYBZx.jpg",
    "backdrop_path": "/zuW6fOiusv4X9nnW3paHGfXcSll.jpg",
    "movie_count": 4
  },
  {
    "id": 131295,
    "name": "速度与激情（系列）",
    "poster_path": "//8HxgBGdTI8Gviy2dKPW0iANYBZx.jpg",
    "backdrop_path": null,
    "movie_count": 10
  }
]
```

### 查询合集详情
```bash
curl -X GET "http://localhost:8000/api/collections/86311" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 当前状态总结

✅ **已存在：**
- 数据库字段 `collection_id` 在 `MovieExt` 表中
- TMDB API 返回合集数据

❌ **需要实现：**
- Collection数据模型
- 数据提取和处理逻辑
- API查询接口

## 建议

建议优先实现完整的合集功能，因为：
1. 用户可以通过合集更好地组织电影
2. 提供更丰富的浏览体验
3. 数据已经可从TMDB获取，实现成本不高
4. 数据库字段已预留，无需迁移