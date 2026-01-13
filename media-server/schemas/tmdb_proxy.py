from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TmdbSearchTvItem(BaseModel):
    tmdb_id: int = Field(..., description="TMDB 系列 ID")
    name: str
    original_name: Optional[str] = None
    first_air_date: Optional[str] = None
    origin_country: List[str] = Field(default_factory=list)
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None


class TmdbSearchTvResponse(BaseModel):
    page: int
    total_pages: int
    total_results: int
    items: List[TmdbSearchTvItem] = Field(default_factory=list)


class TmdbSearchMovieItem(BaseModel):
    tmdb_id: int = Field(..., description="TMDB 电影 ID")
    title: str
    original_title: Optional[str] = None
    release_date: Optional[str] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None


class TmdbSearchMovieResponse(BaseModel):
    page: int
    total_pages: int
    total_results: int
    items: List[TmdbSearchMovieItem] = Field(default_factory=list)


class TmdbTvSeasonItem(BaseModel):
    season_number: int
    name: str
    episode_count: Optional[int] = None
    air_date: Optional[str] = None
    poster_path: Optional[str] = None


class TmdbTvSeasonsResponse(BaseModel):
    tmdb_id: int = Field(..., description="TMDB 系列 ID")
    name: str
    seasons: List[TmdbTvSeasonItem] = Field(default_factory=list)


class TmdbSeasonEpisodeItem(BaseModel):
    episode_number: int
    episode_tmdb_id: int
    name: str
    air_date: Optional[str] = None
    overview: Optional[str] = None
    still_path: Optional[str] = None
    runtime: Optional[int] = None


class TmdbSeasonEpisodesResponse(BaseModel):
    series_tmdb_id: int
    season_number: int
    episodes: List[TmdbSeasonEpisodeItem] = Field(default_factory=list)
