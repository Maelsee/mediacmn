class CreditItem(BaseModel):
    name: str
    character: Optional[str] = None
    image_url: Optional[str] = None


class FileAssert(BaseModel):
    file_id: int
    path: str
    size: Optional[int] = None
    size_text: Optional[str] = None
    language: Optional[str] = None
    storage: Optional[dict] = None


class VersionItem(BaseModel):
    id: int
    quality: Optional[str] = None
    assets: List[FileAssert]


class SeasonEpisode(BaseModel):
    id: int
    episode_number: int
    title: str   
    still_path: Optional[str] = None
    assets: Optional[List[FileAssert]] = None


class SeasonDetail(BaseModel):
    id: int
    season_number: int
    title: str
    air_date: Optional[str] = None
    cover: Optional[str] = None
    overview: Optional[str] = None
    rating: Optional[float] = None
    cast: Optional[List[CreditItem]] = None
    runtime: Optional[int] = None
    runtime_text: Optional[str] = None
    episodes: Optional[List[SeasonEpisode]] = None





class MediaDetailResponse(BaseModel):
    id: int
    title: str
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    rating: Optional[float] = None
    release_date: Optional[str] = None
    overview: Optional[str] = None
    genres: List[str]
    versions: Optional[List[VersionItem]] = None
    cast: Optional[List[CreditItem]] = None
    media_type: str
    runtime: Optional[int] = None
    runtime_text: Optional[str] = None
    # TV 专属
    season_count: Optional[int] = None
    episode_count: Optional[int] = None
    seasons: Optional[List[SeasonDetail]] = None
    directors: Optional[List[CreditItem]] = None
    writers: Optional[List[CreditItem]] = None

以下是首页展示的卡片数据结构：
class HomeCardGenre(BaseModel):
    id: int
    name: str


class HomeCardItem(BaseModel):
    id: int
    name: str
    cover_url: Optional[str] = Field(None, description="封面URL")
    rating: Optional[float] = None
    release_date: Optional[str] = None
    media_type: str


class HomeCardsResponse(BaseModel):
    genres: List[HomeCardGenre]
    movie: List[HomeCardItem]
    tv: List[HomeCardItem]

{
  "file_id": 16,
  "playurl": "http://maelsea.site:5244/dav/302/133quark302/test/%E6%AF%95%E6%AD%A3%E6%98%8E%E7%9A%84%E8%AF%81%E6%98%8E.The.Return.of.The.Lame.Hero.2025.2160p.WEB-DL.H265.HDR.DDP5.1-PandaQT.mkv",
  "headers": {
    "Authorization": "Basic bWFlbDoxMTA="
  },
  "expires_at": null,
  "format": "file",
  "source_type": "webdav"
}


已完成搜索页面重构和后端对接准备。

**已完成的修改**

1.  **SearchPage UI 重构 (`search_page.dart`)**：
    *   实现了 **5 类筛选行** (Type, Sort, Genre, Region, Year)。
    *   点击筛选选项 **立即更新** 下方的卡片列表。
    *   输入框内容变更需要 **点击搜索按钮** 才会触发更新。
    *   使用 `LayoutBuilder` 实现了 **动态网格布局**，列数随屏幕宽度自动调整 (最小卡片宽度 110px)。
    *   使用现有的 `MediaCard` 组件展示后端返回的数据。

2.  **数据模型更新 (`media_models.dart`)**：
    *   新增 `TypeCounts` 模型：对应后端的类型统计 (movie, tv, anime, etc.)。
    *   新增 `FilterCardsResponse` 模型：完全匹配后端返回格式 (page, page_size, total, items, type_counts)。

3.  **API 客户端更新 (`api_client.dart`)**：
    *   更新 `searchMedia` 方法以返回 `FilterCardsResponse`。
    *   实现了所有筛选参数的传递逻辑（自动排除 "全部" 选项）。

**后端 API 实现所需的参数**

这是前端 `SearchPage` 发送给后端的查询参数（Query Parameters），请在后端 `/api/media/cards` 接口中实现这些参数的接收和处理：

| 参数名 | 类型 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `q` | `string` | "钢铁侠" | 搜索关键词（来自输入框） |
| `page` | `int` | `1` | 当前页码 |
| `page_size` | `int` | `30` | 每页数量 |
| `type` | `string` | "movie" | 媒体类型 (movie, tv, anime, variety, documentary, concert)。选 "全部" 时不传此参数。 |
| `genres` | `string` | "Action,Sci-Fi" | 类型列表，逗号分隔。选 "全部" 时不传此参数。 |
| `year` | `string` | "2023" | 年份。选 "全部" 时不传此参数。 |
| `countries` | `string` | "US" | 地区代码。选 "全部" 时不传此参数。 |
| `sort` | `string` | "updated" | 排序方式 (updated, released, added, rating)。 |

**前端筛选值映射参考**

前端显示的中文标签会转换为以下代码传给后端：

*   **类型 (Type)**: `电影` -> `movie`, `剧集` -> `tv`, `动漫` -> `anime`, `综艺` -> `variety`, `纪录片` -> `documentary`, `演唱会` -> `concert`
*   **排序 (Sort)**: `最新更新` -> `updated`, `最新上映` -> `released`, `最新入库` -> `added`, `最高评分` -> `rating`
*   **地区 (Region)**: `中国大陆` -> `CN`, `中国香港` -> `HK`, `中国台湾` -> `TW`, `美国` -> `US`, `日本` -> `JP`, `韩国` -> `KR`, `英国` -> `UK`, `法国` -> `FR`

现在前端已经准备就绪，您可以根据上述参数实现后端 API 逻辑。