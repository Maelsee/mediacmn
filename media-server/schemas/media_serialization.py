from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


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
    animation: List[HomeCardItem]
    reality: List[HomeCardItem]


# class TypeCounts(BaseModel):
#     movie: int
#     tv: int


class FilterCardsResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: List[HomeCardItem]
    # type_counts: TypeCounts


class CreditItem(BaseModel):
    name: str
    character: Optional[str] = None
    image_url: Optional[str] = None


class FileAssert(BaseModel):
    file_id: int
    path: str
    size: Optional[int] = None
    size_text: Optional[str] = None
    resolution: Optional[str] = None
    frame_rate: Optional[str] = None
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
    versions: Optional[List[dict]] = None
    





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
