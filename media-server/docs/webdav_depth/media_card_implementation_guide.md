# 媒体卡片系统实施指南

## 概述
本文档提供媒体卡片系统的具体实施步骤，基于视图层聚合方案，确保电影和电视剧能够以卡片形式高效展示。

## 实施步骤

### 第一步：数据库视图创建

#### 1.1 创建核心卡片视图
执行以下SQL创建主要的卡片聚合视图：

```sql
-- 创建媒体卡片主视图
CREATE OR REPLACE VIEW media_cards AS
SELECT 
    mc.user_id,
    mc.id as core_id,
    mc.kind as media_type,
    
    -- 卡片标题逻辑
    CASE 
        WHEN mc.kind IN ('movie', 'tv_series') THEN mc.title
        WHEN mc.kind = 'tv_season' THEN (
            SELECT title FROM media_core 
            WHERE id = ts.series_core_id AND kind = 'tv_series'
        )
        WHEN mc.kind = 'tv_episode' THEN (
            SELECT title FROM media_core 
            WHERE id = ep.series_core_id AND kind = 'tv_series'
        )
    END as card_title,
    
    mc.original_title,
    mc.year,
    mc.rating,
    mc.plot,
    
    -- 统计信息
    CASE 
        WHEN mc.kind = 'movie' THEN 1
        WHEN mc.kind = 'tv_series' THEN COALESCE(ts.episode_count, 0)
        ELSE 0
    END as total_episodes,
    
    CASE 
        WHEN mc.kind = 'tv_series' THEN COALESCE(ts.season_count, 0)
        WHEN mc.kind IN ('tv_season', 'tv_episode') THEN (
            SELECT COUNT(DISTINCT season_number) FROM tv_season_ext 
            WHERE series_core_id = COALESCE(ts.series_core_id, ss.series_core_id, ep.series_core_id)
        )
        ELSE 0
    END as total_seasons,
    
    -- 最新季集
    CASE 
        WHEN mc.kind = 'tv_series' THEN (
            SELECT MAX(season_number) FROM tv_season_ext 
            WHERE series_core_id = ts.core_id
        )
    END as latest_season,
    
    -- 海报路径
    COALESCE(ts.poster_path, ss.poster_path, mc.poster_path) as poster_path,
    
    -- 文件状态
    EXISTS (
        SELECT 1 FROM file_asset fa 
        WHERE fa.core_id = mc.id AND fa.exists = true
    ) as has_files,
    
    mc.created_at,
    mc.updated_at

FROM media_core mc
LEFT JOIN tv_series_ext ts ON mc.id = ts.core_id AND mc.kind = 'tv_series'
LEFT JOIN tv_season_ext ss ON mc.id = ss.core_id AND mc.kind = 'tv_season'  
LEFT JOIN tv_episode_ext ep ON mc.id = ep.core_id AND mc.kind = 'tv_episode'
WHERE mc.kind IN ('movie', 'tv_series');
```

#### 1.2 创建电视剧详情视图
```sql
-- 创建电视剧详细信息视图
CREATE OR REPLACE VIEW tv_series_card_details AS
SELECT 
    mc.user_id,
    mc.id as series_id,
    mc.title as series_title,
    mc.year,
    mc.rating,
    ts.poster_path,
    ts.season_count,
    ts.episode_count,
    
    -- 每季信息JSON
    COALESCE(
        json_agg(
            json_build_object(
                'season_number', se.season_number,
                'episode_count', se.episode_count,
                'aired_date', se.aired_date,
                'poster_path', se.poster_path
            ) ORDER BY se.season_number
            FILTER (WHERE se.season_number IS NOT NULL)
        ),
        '[]'::json
    ) as seasons_info,
    
    -- 统计信息
    COUNT(DISTINCT se.id) as actual_seasons,
    COUNT(DISTINCT fa.id) as file_count,
    MAX(fa.updated_at) as last_updated

FROM media_core mc
JOIN tv_series_ext ts ON mc.id = ts.core_id
LEFT JOIN tv_season_ext se ON se.series_core_id = mc.id
LEFT JOIN file_asset fa ON fa.core_id IN (mc.id, se.core_id)
WHERE mc.kind = 'tv_series'
GROUP BY mc.user_id, mc.id, mc.title, mc.year, mc.rating, 
         ts.poster_path, ts.season_count, ts.episode_count;
```

### 第二步：性能优化索引

#### 2.1 核心查询索引
```sql
-- 用户媒体查询优化
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_media_core_user_kind 
ON media_core(user_id, kind);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_media_core_user_title 
ON media_core(user_id, title);

-- 电视剧关联查询优化
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tv_season_series 
ON tv_season_ext(series_core_id, season_number);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tv_episode_season 
ON tv_episode_ext(season_core_id, episode_number);

-- 文件状态查询优化
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_file_asset_core_exists 
ON file_asset(core_id, exists) WHERE exists = true;
```

#### 2.2 视图查询优化
```sql
-- 为视图创建物化视图（大数据量时考虑）
CREATE MATERIALIZED VIEW IF NOT EXISTS media_cards_mv AS
SELECT * FROM media_cards;

-- 物化视图索引
CREATE INDEX idx_media_cards_mv_user_type 
ON media_cards_mv(user_id, media_type);

CREATE INDEX idx_media_cards_mv_title 
ON media_cards_mv(card_title);

-- 刷新物化视图的函数
CREATE OR REPLACE FUNCTION refresh_media_cards_mv()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY media_cards_mv;
END;
$$ LANGUAGE plpgsql;
```

### 第三步：API接口实现

#### 3.1 数据模型定义
```python
# models/card_models.py
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class MediaCardBase(BaseModel):
    core_id: int
    media_type: str
    card_title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    rating: Optional[float] = None
    plot: Optional[str] = None
    poster_path: Optional[str] = None
    has_files: bool
    created_at: datetime
    updated_at: datetime

class MediaCard(MediaCardBase):
    """基础卡片信息"""
    total_episodes: int = 0
    total_seasons: int = 0
    latest_season: Optional[int] = None

class TVSeriesCard(MediaCard):
    """电视剧卡片详情"""
    seasons_info: List[dict] = []
    actual_seasons: int = 0
    file_count: int = 0
    last_updated: Optional[datetime] = None

class CardListResponse(BaseModel):
    """卡片列表响应"""
    items: List[MediaCard]
    total: int
    page: int
    page_size: int
    has_next: bool
```

#### 3.2 服务层实现
```python
# services/card_service.py
from typing import List, Optional
from sqlalchemy import text
from core.db import database

class CardService:
    """卡片聚合服务"""
    
    @staticmethod
    async def get_user_cards(
        user_id: int,
        media_type: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20
    ) -> CardListResponse:
        """获取用户媒体卡片列表"""
        
        # 基础查询
        base_query = """
        SELECT 
            core_id, media_type, card_title, original_title,
            year, rating, plot, poster_path, has_files,
            total_episodes, total_seasons, latest_season,
            created_at, updated_at
        FROM media_cards 
        WHERE user_id = :user_id 
        """
        
        # 条件过滤
        params = {'user_id': user_id}
        if media_type:
            base_query += " AND media_type = :media_type"
            params['media_type'] = media_type
        
        # 排序逻辑
        order_mappings = {
            'title': 'card_title',
            'year': 'year',
            'rating': 'rating',
            'updated_at': 'updated_at',
            'created_at': 'created_at'
        }
        
        order_field = order_mappings.get(sort_by, 'updated_at')
        base_query += f" ORDER BY {order_field} {sort_order.upper()}"
        
        # 分页
        base_query += " LIMIT :limit OFFSET :offset"
        params.update({
            'limit': page_size,
            'offset': (page - 1) * page_size
        })
        
        # 执行查询
        items = await database.fetch_all(text(base_query), params)
        
        # 获取总数
        count_query = """
        SELECT COUNT(*) as total
        FROM media_cards 
        WHERE user_id = :user_id
        """
        if media_type:
            count_query += " AND media_type = :media_type"
        
        total_result = await database.fetch_one(text(count_query), params)
        total = total_result['total'] if total_result else 0
        
        return CardListResponse(
            items=[MediaCard(**dict(item)) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=total > page * page_size
        )
    
    @staticmethod
    async def get_tv_series_detail(user_id: int, series_id: int) -> Optional[TVSeriesCard]:
        """获取电视剧卡片详细信息"""
        
        query = """
        SELECT 
            mc.core_id, mc.media_type, mc.card_title, mc.original_title,
            mc.year, mc.rating, mc.plot, mc.poster_path, mc.has_files,
            mc.total_episodes, mc.total_seasons, mc.latest_season,
            mc.created_at, mc.updated_at,
            tsd.seasons_info, tsd.actual_seasons, tsd.file_count, tsd.last_updated
        FROM media_cards mc
        LEFT JOIN tv_series_card_details tsd ON mc.core_id = tsd.series_id AND mc.user_id = tsd.user_id
        WHERE mc.user_id = :user_id AND mc.core_id = :series_id AND mc.media_type = 'tv_series'
        """
        
        result = await database.fetch_one(text(query), {
            'user_id': user_id,
            'series_id': series_id
        })
        
        if not result:
            return None
        
        return TVSeriesCard(**dict(result))
```

#### 3.3 API端点实现
```python
# api/cards.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

router = APIRouter(prefix="/api/cards", tags=["cards"])

@router.get("", response_model=CardListResponse)
async def get_media_cards(
    user_id: int = Depends(get_current_user_id),
    media_type: Optional[str] = Query(None, description="媒体类型: movie 或 tv_series"),
    sort_by: str = Query("updated_at", description="排序字段: title, year, rating, updated_at, created_at"),
    sort_order: str = Query("desc", description="排序顺序: asc 或 desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取用户媒体卡片列表"""
    
    return await CardService.get_user_cards(
        user_id=user_id,
        media_type=media_type,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size
    )

@router.get("/{card_id}", response_model=TVSeriesCard)
async def get_card_detail(
    card_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """获取卡片详细信息"""
    
    # 先获取基础卡片信息
    card = await CardService.get_user_cards(user_id=user_id, page=1, page_size=1)
    if not card.items or card.items[0].core_id != card_id:
        raise HTTPException(status_code=404, detail="Card not found")
    
    base_card = card.items[0]
    
    # 如果是电视剧，获取详细信息
    if base_card.media_type == 'tv_series':
        detail_card = await CardService.get_tv_series_detail(user_id, card_id)
        if detail_card:
            return detail_card
    
    # 电影直接返回基础信息
    return base_card
```

### 第四步：性能监控与优化

#### 4.1 查询性能监控
```python
# utils/performance.py
import time
import logging
from functools import wraps

def monitor_query_performance(func_name: str):
    """查询性能监控装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # 记录慢查询
                if execution_time > 1.0:  # 超过1秒视为慢查询
                    logging.warning(f"Slow query detected: {func_name} took {execution_time:.2f}s")
                
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logging.error(f"Query failed: {func_name} after {execution_time:.2f}s - {str(e)}")
                raise
        return wrapper
    return decorator

# 应用到服务方法
class CardService:
    @monitor_query_performance("get_user_cards")
    async def get_user_cards(self, ...):
        # 现有实现
        pass
    
    @monitor_query_performance("get_tv_series_detail")
    async def get_tv_series_detail(self, ...):
        # 现有实现
        pass
```

#### 4.2 缓存实现
```python
# services/cache_service.py
import redis
import json
import hashlib
from typing import Optional, Any

class CardCacheService:
    """卡片缓存服务"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = 300  # 5分钟
    
    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        params_str = ":".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
        return f"{prefix}:{hashlib.md5(params_str.encode()).hexdigest()}"
    
    async def get_card_list(
        self, 
        user_id: int, 
        media_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Optional[CardListResponse]:
        """获取缓存的卡片列表"""
        cache_key = self._generate_cache_key(
            "card_list", 
            user_id=user_id, 
            media_type=media_type,
            page=page,
            page_size=page_size
        )
        
        cached_data = self.redis.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            return CardListResponse(**data)
        
        return None
    
    async def set_card_list(
        self, 
        response: CardListResponse,
        user_id: int, 
        media_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        ttl: Optional[int] = None
    ):
        """设置卡片列表缓存"""
        cache_key = self._generate_cache_key(
            "card_list", 
            user_id=user_id, 
            media_type=media_type,
            page=page,
            page_size=page_size
        )
        
        self.redis.setex(
            cache_key,
            ttl or self.default_ttl,
            json.dumps(response.dict())
        )
    
    async def invalidate_user_cards(self, user_id: int):
        """清除用户相关缓存"""
        pattern = f"card_list:*user_id_{user_id}:*"
        for key in self.redis.scan_iter(match=pattern):
            self.redis.delete(key)
```

### 第五步：测试验证

#### 5.1 单元测试
```python
# tests/test_card_service.py
import pytest
from services.card_service import CardService

@pytest.mark.asyncio
class TestCardService:
    
    async def test_get_user_cards_basic(self):
        """测试基础卡片查询"""
        result = await CardService.get_user_cards(user_id=1)
        
        assert result is not None
        assert result.total >= 0
        assert len(result.items) <= result.page_size
        
        # 验证卡片数据结构
        if result.items:
            card = result.items[0]
            assert card.core_id > 0
            assert card.media_type in ['movie', 'tv_series']
            assert card.card_title is not None
    
    async def test_tv_series_card_aggregation(self):
        """测试电视剧卡片聚合"""
        result = await CardService.get_user_cards(
            user_id=1, 
            media_type='tv_series'
        )
        
        if result.items:
            tv_card = result.items[0]
            assert tv_card.total_seasons >= 0
            assert tv_card.total_episodes >= 0
            
            # 获取详细信息
            detail = await CardService.get_tv_series_detail(
                user_id=1, 
                series_id=tv_card.core_id
            )
            
            assert detail is not None
            assert len(detail.seasons_info) >= 0
    
    async def test_card_filtering(self):
        """测试卡片筛选功能"""
        # 测试电影筛选
        movie_result = await CardService.get_user_cards(
            user_id=1, 
            media_type='movie'
        )
        
        if movie_result.items:
            assert all(card.media_type == 'movie' for card in movie_result.items)
        
        # 测试电视剧筛选
        tv_result = await CardService.get_user_cards(
            user_id=1, 
            media_type='tv_series'
        )
        
        if tv_result.items:
            assert all(card.media_type == 'tv_series' for card in tv_result.items)
```

#### 5.2 性能测试
```python
# tests/test_performance.py
import asyncio
import time
import aiohttp

async def test_card_api_performance():
    """测试卡片API性能"""
    
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        
        # 并发请求测试
        tasks = []
        for i in range(10):  # 模拟10个并发用户
            task = session.get(
                f"http://localhost:8000/api/cards",
                headers={"Authorization": f"Bearer test_token_{i}"}
            )
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # 分析结果
        successful_requests = sum(1 for r in responses if not isinstance(r, Exception))
        
        print(f"性能测试结果:")
        print(f"总耗时: {total_time:.2f}s")
        print(f"成功请求: {successful_requests}/10")
        print(f"平均响应时间: {total_time/10:.2f}s")
        
        assert total_time < 5.0, "性能测试超时"
        assert successful_requests >= 8, "成功率过低"
```

### 第六步：部署配置

#### 6.1 环境配置
```bash
# .env 配置
# 数据库连接
DATABASE_URL=postgresql://user:password@localhost:5432/media_db

# Redis缓存
REDIS_URL=redis://localhost:6379/0

# 性能配置
CARD_CACHE_TTL=300
CARD_PAGE_SIZE=20
MAX_CARD_PAGE_SIZE=100
```

#### 6.2 部署脚本
```bash
#!/bin/bash
# deploy_cards.sh

echo "开始部署媒体卡片系统..."

# 1. 数据库迁移
echo "执行数据库视图创建..."
psql $DATABASE_URL -f sql/create_card_views.sql

# 2. 创建索引
echo "创建性能优化索引..."
psql $DATABASE_URL -f sql/create_card_indexes.sql

# 3. 验证部署
echo "验证视图创建结果..."
psql $DATABASE_URL -c "SELECT COUNT(*) FROM media_cards LIMIT 1;"

echo "媒体卡片系统部署完成！"
```

#### 6.3 监控配置
```yaml
# monitoring/prometheus.yml
scrape_configs:
  - job_name: 'media-cards'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s

# 自定义指标
rules:
  - alert: CardQuerySlow
    expr: card_query_duration_seconds > 1.0
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "卡片查询响应过慢"
      description: "卡片查询响应时间超过1秒"

  - alert: CardCacheHitRateLow
    expr: rate(card_cache_hits_total[5m]) / rate(card_cache_requests_total[5m]) < 0.8
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "卡片缓存命中率过低"
      description: "缓存命中率低于80%"
```

## 验证清单

### 功能验证
- [ ] 电影卡片正确展示单卡片
- [ ] 电视剧卡片正确聚合展示
- [ ] 季集统计信息准确
- [ ] 海报图片正确显示
- [ ] 分页功能正常工作
- [ ] 筛选功能正常工作

### 性能验证
- [ ] 单用户查询响应时间 < 500ms
- [ ] 并发10用户查询响应时间 < 2s
- [ ] 缓存命中率 > 80%
- [ ] 数据库查询无慢查询（>1s）

### 数据一致性验证
- [ ] 视图数据与基础表一致
- [ ] 聚合统计信息准确
- [ ] 用户数据隔离正确
- [ ] 新增数据实时反映在卡片中

## 故障排除

### 常见问题

#### 1. 视图查询性能差
**症状**：卡片加载缓慢
**解决方案**：
```sql
-- 检查执行计划
EXPLAIN ANALYZE SELECT * FROM media_cards WHERE user_id = 1;

-- 如需要，创建物化视图
CREATE MATERIALIZED VIEW media_cards_mv AS SELECT * FROM media_cards;
CREATE INDEX idx_mv_user_type ON media_cards_mv(user_id, media_type);
```

#### 2. 缓存未生效
**症状**：重复查询数据库
**解决方案**：
```python
# 检查Redis连接
redis_client = redis.from_url(settings.REDIS_URL)
print(redis_client.ping())  # 应该返回True

# 检查缓存键生成
print(cache_service._generate_cache_key("card_list", user_id=1))
```

#### 3. 聚合数据不准确
**症状**：季集数量显示错误
**解决方案**：
```sql
-- 验证聚合逻辑
SELECT 
    mc.title,
    ts.season_count,
    ts.episode_count,
    (SELECT COUNT(*) FROM tv_season_ext WHERE series_core_id = mc.id) as actual_seasons,
    (SELECT COUNT(*) FROM tv_episode_ext ep 
     JOIN tv_season_ext ss ON ep.season_core_id = ss.core_id 
     WHERE ss.series_core_id = mc.id) as actual_episodes
FROM media_core mc
JOIN tv_series_ext ts ON mc.id = ts.core_id
WHERE mc.kind = 'tv_series' AND mc.user_id = 1;
```

## 扩展功能建议

### 1. 智能排序
```python
# 根据用户行为调整排序权重
def calculate_sort_score(card, user_behavior):
    base_score = card.rating or 0
    
    # 观看进度权重
    if card.media_type == 'tv_series':
        watched_episodes = user_behavior.get_watched_count(card.core_id)
        progress_weight = watched_episodes / max(card.total_episodes, 1)
        base_score += progress_weight * 2
    
    # 时间衰减
    from datetime import timezone
    days_old = (datetime.now(timezone.utc) - card.updated_at).days
    time_decay = max(0, 1 - days_old / 365)
    
    return base_score * time_decay
```

### 2. 个性化推荐
```python
# 基于内容相似度的推荐
def get_similar_cards(card, user_id, limit=5):
    """获取相似卡片推荐"""
    query = """
    SELECT DISTINCT mc.*, 
           similarity(mc.genres, :card_genres) as genre_similarity,
           similarity(mc.actors, :card_actors) as actor_similarity
    FROM media_cards mc
    WHERE mc.user_id = :user_id 
      AND mc.core_id != :card_id
      AND (similarity(mc.genres, :card_genres) > 0.3
           OR similarity(mc.actors, :card_actors) > 0.2)
    ORDER BY (genre_similarity + actor_similarity) DESC
    LIMIT :limit
    """
    
    return execute_query(query, {
        'user_id': user_id,
        'card_id': card.core_id,
        'card_genres': card.genres,
        'card_actors': card.actors,
        'limit': limit
    })
```

### 3. 多语言支持
```python
# 卡片标题多语言
class MediaCardI18n:
    def get_display_title(self, card, language='zh-CN'):
        """获取指定语言的显示标题"""
        if language == 'zh-CN':
            return card.card_title
        elif language == 'en-US':
            return card.original_title or card.card_title
        else:
            # 从翻译表获取
            return self.get_translation(card.core_id, language)
```

## 总结

本实施指南提供了完整的媒体卡片系统部署方案，核心特点：

1. **零侵入设计**：通过视图层聚合，不影响现有业务逻辑
2. **高性能**：优化的索引和缓存策略，确保快速响应
3. **易维护**：自动化视图维护，减少运维成本
4. **可扩展**：预留接口支持未来功能扩展

按照本指南实施，可以实现电影单卡片、电视剧聚合卡片的高效展示，满足用户对媒体库浏览的需求。