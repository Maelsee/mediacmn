from fastapi import FastAPI, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SourceItem(BaseModel):
    id: str
    type: str
    name: str
    status: str
    last_scan: Optional[str] = None

class SourceCreateRequest(BaseModel):
    type: str
    name: str
    endpoint: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    base_path: Optional[str] = None
    scan_policy: Optional[Dict[str, Any]] = None

class SourceCreateResponse(BaseModel):
    id: str
    task_id: Optional[str] = None

class ScanTask(BaseModel):
    id: str
    source_id: str
    status: str
    progress: int
    error: Optional[str] = None

class ScanGroup(BaseModel):
    group_id: str
    status: str
    progress: int
    tasks: List[ScanTask]

class Category(BaseModel):
    id: str
    name: str
    cover: Optional[str] = None

class MediaItem(BaseModel):
    id: str
    kind: str
    title: str
    poster: Optional[str] = None
    backdrop: Optional[str] = None
    rating: Optional[float] = None
    year: Optional[int] = None

class PagedResult(BaseModel):
    total: int
    items: List[MediaItem]

class LibraryHome(BaseModel):
    categories: List[Category]
    recent: List[MediaItem]
    movies: PagedResult
    tv: PagedResult
    scan_summary: Optional[Dict[str, Any]] = None

class AssetItemDetail(BaseModel):
    file_id: int
    path: str
    type: str
    size: Optional[int] = None
    size_text: Optional[str] = None

class VersionItemDetail(BaseModel):
    id: int
    label: Optional[str] = None
    quality: Optional[str] = None
    source: Optional[str] = None
    edition: Optional[str] = None
    assets: List[AssetItemDetail] = []

class CastItemDetail(BaseModel):
    name: str
    character: Optional[str] = None

class EpisodeItemDetail(BaseModel):
    episode_number: int
    title: str
    assets: List[AssetItemDetail] = []
    technical: Optional[Dict[str, Any]] = None

class SeasonItemDetail(BaseModel):
    season_number: int
    episodes: List[EpisodeItemDetail] = []

class MediaDetailResponse(BaseModel):
    id: int
    title: str
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    rating: Optional[float] = None
    release_date: Optional[str] = None
    overview: Optional[str] = None
    genres: List[str] = []
    versions: List[VersionItemDetail] = []
    cast: List[CastItemDetail] = []
    media_type: str
    seasons: Optional[List[SeasonItemDetail]] = None

db_sources: Dict[str, SourceItem] = {
    "src_123": SourceItem(id="src_123", type="webdav", name="家庭NAS", status="enabled", last_scan=datetime.utcnow().isoformat() + "Z"),
    "src_456": SourceItem(id="src_456", type="local", name="本地文件夹", status="disabled", last_scan=datetime.utcnow().isoformat() + "Z"),
}
db_tasks: Dict[str, ScanTask] = {
    "task_001": ScanTask(id="task_001", source_id="src_123", status="succeeded", progress=100),
    "task_002": ScanTask(id="task_002", source_id="src_456", status="failed", progress=100, error="路径不可访问"),
}
db_groups: Dict[str, List[str]] = {}
library_categories: List[Category] = [
    Category(id="genre_drama", name="剧情"),
    Category(id="genre_action", name="动作"),
    Category(id="genre_comedy", name="喜剧"),
]
library_movies: List[MediaItem] = [
    MediaItem(id="m1", kind="movie", title="示例电影 1", year=2020, rating=7.2, poster="/posters/m1.jpg"),
    MediaItem(id="m2", kind="movie", title="动作电影 2", year=2021, rating=6.8, poster="/posters/m2.jpg"),
    MediaItem(id="m3", kind="movie", title="剧情电影 3", year=2019, rating=8.1, poster="/posters/m3.jpg"),
]
library_tv: List[MediaItem] = [
    MediaItem(id="t1", kind="tv", title="示例剧集 1", year=2018, rating=7.9, poster="/posters/t1.jpg"),
    MediaItem(id="t2", kind="tv", title="动作剧集 2", year=2022, rating=7.0, poster="/posters/t2.jpg"),
]
recent_items: List[MediaItem] = [library_movies[0], library_tv[0]]

db_media_detail: Dict[int, MediaDetailResponse] = {
    0: MediaDetailResponse(
        id=0,
        title="示例电影 1",
        poster_path="/posters/m1.jpg",
        backdrop_path="/posters/m1.jpg",
        rating=7.2,
        release_date="2020-06-01",
        overview="这是一部用于演示的电影详情。",
        genres=["剧情", "动作"],
        versions=[
            VersionItemDetail(
                id=1,
                label="院线版",
                quality="1080p",
                source="Web",
                edition="Theatrical",
                assets=[
                    AssetItemDetail(file_id=1001, path="/hls/demo/master.m3u8", type="hls_master", size=None, size_text="HLS"),
                    AssetItemDetail(file_id=1002, path="/videos/demo_1080p.mp4", type="file", size=2147483648, size_text="2.0 GB"),
                ],
            ),
            VersionItemDetail(
                id=2,
                label="蓝光版",
                quality="2160p",
                source="BluRay",
                edition="UHD",
                assets=[
                    AssetItemDetail(file_id=1003, path="/videos/demo_4k.mp4", type="file", size=6442450944, size_text="6.0 GB"),
                ],
            ),
        ],
        cast=[
            CastItemDetail(name="演员甲", character="主角"),
            CastItemDetail(name="演员乙", character="配角"),
        ],
        media_type="movie",
    ),
    1: MediaDetailResponse(
        id=1,
        title="示例剧集 1",
        poster_path="/posters/t1.jpg",
        backdrop_path="/posters/t1.jpg",
        rating=7.9,
        release_date="2018-01-01",
        overview="这是一部用于演示的剧集详情。",
        genres=["剧情", "悬疑"],
        versions=[],
        cast=[
            CastItemDetail(name="演员丙", character="侦探"),
            CastItemDetail(name="演员丁", character="嫌疑人"),
        ],
        media_type="tv",
        seasons=[
            SeasonItemDetail(
                season_number=1,
                episodes=[
                    EpisodeItemDetail(
                        episode_number=1,
                        title="第一集",
                        assets=[
                            AssetItemDetail(file_id=2001, path="/hls/t1_s1_e1/master.m3u8", type="hls_master", size=None, size_text="HLS"),
                            AssetItemDetail(file_id=2002, path="/videos/t1_s1_e1_1080p.mp4", type="file", size=2147483648, size_text="2.0 GB"),
                        ],
                        technical={"size_label": "2.0 GB"},
                    ),
                    EpisodeItemDetail(
                        episode_number=2,
                        title="第二集",
                        assets=[
                            AssetItemDetail(file_id=2003, path="/hls/t1_s1_e2/master.m3u8", type="hls_master", size=None, size_text="HLS"),
                            AssetItemDetail(file_id=2004, path="/videos/t1_s1_e2_1080p.mp4", type="file", size=2147483648, size_text="2.0 GB"),
                        ],
                        technical={"size_label": "2.0 GB"},
                    ),
                ],
            ),
            SeasonItemDetail(
                season_number=2,
                episodes=[
                    EpisodeItemDetail(
                        episode_number=1,
                        title="第一集",
                        assets=[
                            AssetItemDetail(file_id=2005, path="/hls/t1_s2_e1/master.m3u8", type="hls_master", size=None, size_text="HLS"),
                            AssetItemDetail(file_id=2006, path="/videos/t1_s2_e1_1080p.mp4", type="file", size=2147483648, size_text="2.0 GB"),
                        ],
                        technical={"size_label": "2.0 GB"},
                    ),
                ],
            ),
        ],
    ),
}

def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

@app.get("/sources", response_model=List[SourceItem])
def list_sources(page: int = 1, size: int = 20):
    items = list(db_sources.values())
    start = (page - 1) * size
    end = start + size
    return items[start:end]

@app.post("/sources", response_model=SourceCreateResponse)
def create_source(req: SourceCreateRequest):
    sid = _new_id("src")
    src = SourceItem(id=sid, type=req.type, name=req.name, status="enabled", last_scan=None)
    db_sources[sid] = src
    tid = _new_id("task")
    task = ScanTask(id=tid, source_id=sid, status="queued", progress=0)
    db_tasks[tid] = task
    return SourceCreateResponse(id=sid, task_id=tid)

@app.get("/sources/{source_id}", response_model=SourceItem)
def get_source(source_id: str):
    return db_sources[source_id]

class SourceUpdateRequest(BaseModel):
    name: Optional[str] = None

@app.put("/sources/{source_id}")
def update_source(source_id: str, req: SourceUpdateRequest):
    src = db_sources[source_id]
    if req.name:
        src.name = req.name
    db_sources[source_id] = src
    return {"ok": True}

@app.post("/sources/{source_id}/enable")
def enable_source(source_id: str):
    src = db_sources[source_id]
    src.status = "enabled"
    db_sources[source_id] = src
    return {"ok": True}

@app.post("/sources/{source_id}/disable")
def disable_source(source_id: str):
    src = db_sources[source_id]
    src.status = "disabled"
    db_sources[source_id] = src
    return {"ok": True}

@app.delete("/sources/{source_id}")
def delete_source(source_id: str):
    db_sources.pop(source_id, None)
    return {"ok": True}

@app.post("/sources/{source_id}/scan")
def scan_source(source_id: str):
    tid = _new_id("task")
    task = ScanTask(id=tid, source_id=source_id, status="running", progress=0)
    db_tasks[tid] = task
    return {"task_id": tid}

@app.get("/tasks", response_model=List[ScanTask])
def list_tasks(sources: Optional[str] = Query(None)):
    if sources:
        return [t for t in db_tasks.values() if t.source_id == sources]
    return list(db_tasks.values())

class ScanAllRequest(BaseModel):
    sources: Optional[List[str]] = None

@app.post("/scan/all", response_model=ScanGroup)
def scan_all(req: ScanAllRequest):
    gid = _new_id("group")
    src_ids = req.sources or list(db_sources.keys())
    tasks: List[ScanTask] = []
    for sid in src_ids:
        tid = _new_id("task")
        t = ScanTask(id=tid, source_id=sid, status="running", progress=0)
        db_tasks[tid] = t
        tasks.append(t)
    db_groups[gid] = [t.id for t in tasks]
    return ScanGroup(group_id=gid, status="running", progress=0, tasks=tasks)

@app.get("/scan/groups/{group_id}")
def get_group(group_id: str):
    ids = db_groups.get(group_id, [])
    tasks = [db_tasks[i] for i in ids]
    return {"tasks": [t.dict() for t in tasks]}

@app.get("/library/home", response_model=LibraryHome)
def library_home():
    summary = {
        "running_tasks": len([t for t in db_tasks.values() if t.status == "running"]),
        "last_global_scan": datetime.utcnow().isoformat() + "Z",
        "added": 3,
        "failed": 0,
    }
    return LibraryHome(
        categories=library_categories,
        recent=recent_items,
        movies=PagedResult(total=len(library_movies), items=library_movies[:9]),
        tv=PagedResult(total=len(library_tv), items=library_tv[:9]),
        scan_summary=summary,
    )

@app.get("/api/media/{id}/detail", response_model=MediaDetailResponse)
def media_detail(id: int):
    return db_media_detail.get(id, db_media_detail[1])

@app.get("/library/categories/{category_id}/items", response_model=PagedResult)
def category_items(category_id: str, page: int = 1, page_size: int = 30):
    data = library_movies if category_id.endswith("movie") or category_id == "movie" else library_tv
    start = (page - 1) * page_size
    end = start + page_size
    return PagedResult(total=len(data), items=data[start:end])

@app.get("/media/search", response_model=PagedResult)
def media_search(
    q: str,
    page: int = 1,
    page_size: int = 30,
    kind: Optional[str] = None,
    genres: Optional[str] = None,
    year: Optional[str] = None,
    region: Optional[str] = None,
):
    all_items = library_movies + library_tv
    if kind == "movie":
        all_items = library_movies
    elif kind == "tv":
        all_items = library_tv
    matched = [m for m in all_items if q.lower() in m.title.lower()]
    if year:
        try:
            y = int(year)
            matched = [m for m in matched if (m.year or 0) == y]
        except Exception:
            pass
    if genres:
        genre_list = [g.strip() for g in genres.split(',') if g.strip()]
        if genre_list:
            # 模拟：如果类别命中关键词则保留（真实实现应基于媒体模型的genres字段）
            matched = [m for m in matched if any(g in (m.title or '') for g in genre_list)]
    if region:
        # 演示数据没有 region 字段，这里仅保留逻辑占位
        pass
    start = (page - 1) * page_size
    end = start + page_size
    return PagedResult(total=len(matched), items=matched[start:end])

@app.get("/posters/{poster_id}.jpg")
def get_poster(poster_id: str):
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABQCAYAAABbC1sUAAAACXBIWXMAAAsTAAALEwEAmpwYAAABJ0lEQVR4nO3ZsQ3CMBRA0UeQJ+gIuQkYIuQkYIuQkYIuQkYIvQmPqQWJQkzZfY8Hbn9VwqfK3cQxkQ8D2I6n9mYcYwGf0jv0w2B3YQf1wqCqFf3yqgG8M0KjU9Qf9LJfQf0zjWvYlKfL1uA6b6jK3KqkJ0yY2f3nQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2JQeY2KQv8kHkA7g3q9o6w5QJ9xqgAAAABJRU5ErkJggg=="
    )
    return Response(content=base64.b64decode(png_b64), media_type="image/png")

@app.head("/posters/{poster_id}.jpg")
def head_poster(poster_id: str):
    return Response(status_code=200)