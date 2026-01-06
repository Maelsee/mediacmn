import pytest

from services.media.metadata_enricher import MetadataEnricher
from services.scraper.base import ScraperSearchResult


def _make_result(
    *,
    id: int,
    title: str,
    original_name: str | None,
    year: int | None,
    origin_country: list[str] | None = None,
    original_language: str | None = None,
    vote_average: float | None = None,
    vote_count: int | None = None,
    popularity: float | None = None,
):
    return ScraperSearchResult(
        id=id,
        title=title,
        original_name=original_name,
        original_language=original_language,
        release_date=None,
        vote_average=vote_average,
        vote_count=vote_count,
        origin_country=origin_country or [],
        popularity=popularity,
        provider="tmdb",
        media_type="tv",
        poster_path=None,
        backdrop_path=None,
        year=year,
        provider_url=None,
    )


def test_best_match_prefers_exact_title_and_close_year():
    enricher = MetadataEnricher()

    parsed_data = {
        "title": "现在就出发",
        "year": 2024,
        "language": "zh-CN",
        "country": "CN",
    }

    preferred = _make_result(
        id=1,
        title="现在就出发",
        original_name=None,
        year=2023,
        origin_country=["CN"],
        original_language="zh",
        vote_average=8.5,
        vote_count=200,
        popularity=50.0,
    )

    other = _make_result(
        id=2,
        title="出发吧少年",
        original_name=None,
        year=2024,
        origin_country=["CN"],
        original_language="zh",
        vote_average=8.5,
        vote_count=200,
        popularity=50.0,
    )

    best = enricher._get_best_match([other, preferred], parsed_data)

    assert best is not None
    assert best.id == preferred.id


def test_best_match_uses_language_and_country_when_year_missing():
    enricher = MetadataEnricher()

    parsed_data = {
        "title": "现在就出发",
        "year": None,
        "language": "zh-CN",
        "country": "CN",
    }

    zh_cn = _make_result(
        id=1,
        title="现在就出发",
        original_name=None,
        year=2023,
        origin_country=["CN"],
        original_language="zh",
        vote_average=7.5,
        vote_count=50,
        popularity=30.0,
    )

    foreign = _make_result(
        id=2,
        title="Xian Zai Chu Fa",
        original_name=None,
        year=2023,
        origin_country=["US"],
        original_language="en",
        vote_average=9.0,
        vote_count=200,
        popularity=80.0,
    )

    best = enricher._get_best_match([foreign, zh_cn], parsed_data)

    assert best is not None
    assert best.id == zh_cn.id

