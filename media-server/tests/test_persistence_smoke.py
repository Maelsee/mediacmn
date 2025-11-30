import os
import sys
from sqlmodel import SQLModel, Session, create_engine, select

# 将项目根路径加入搜索路径，确保可导入 models 和 services
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.user import User
from models.media_models import FileAsset, MediaCore, TVSeriesExt, SeasonExt, EpisodeExt
from services.media.metadata_persistence_service import persistence_service
from services.scraper.base import ScraperSeriesDetail, ScraperSeasonDetail, ScraperEpisodeDetail, ScraperArtwork, ArtworkType, ScraperMovieDetail

def run():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        u = User(email="test@example.com", hashed_password="x")
        session.add(u)
        session.flush()
        user_id = u.id

        fa = FileAsset(
            user_id=user_id,
            storage_id=None,
            full_path="/tmp/episode_s01e01.mkv",
            filename="episode_s01e01.mkv",
            relative_path="episode_s01e01.mkv",
            size=123,
        )
        session.add(fa)
        session.flush()

        sd = ScraperSeriesDetail(
            series_id="100",
            name="测试剧",
            original_name="测试剧",
            overview="系列介绍",
            status="Ended",
            first_air_date="2024-01-01",
            last_air_date="2024-12-31",
            episode_run_time=[45],
            number_of_episodes=12,
            number_of_seasons=2,
            genres=["动作", "剧情"],
            poster_path="https://image.tmdb.org/t/p/w500/abc",
            backdrop_path="https://image.tmdb.org/t/p/w1280/def",
            vote_average=7.8,
            vote_count=1000,
            popularity=10.0,
            provider="tmdb",
            provider_url="https://www.themoviedb.org/tv/100",
            artworks=[],
            credits=[],
            external_ids=[],
            raw_data={"k": "v"},
        )

        se = ScraperSeasonDetail(
            season_id="200",
            season_number=1,
            name="第1季",
            poster_path="https://image.tmdb.org/t/p/w500/s1",
            overview="第一季介绍",
            episode_count=6,
            air_date="2024-01-01",
            vote_average=7.5,
            provider="tmdb",
            provider_url="https://www.themoviedb.org/tv/100/season/1",
            artworks=[],
            credits=[],
            external_ids=[],
            raw_data={"season": 1},
        )

        ed = ScraperEpisodeDetail(
            episode_id="300",
            episode_number=1,
            season_number=1,
            name="第一集",
            overview="第一集介绍",
            air_date="2024-01-02",
            runtime=44,
            still_path="https://image.tmdb.org/t/p/w500/xyz.jpg",
            vote_average=7.6,
            vote_count=100,
            provider="tmdb",
            provider_url="https://www.themoviedb.org/tv/100/season/1/episode/1",
            artworks=[ScraperArtwork(type=ArtworkType.THUMB, url="https://image.tmdb.org/t/p/w500/xyz.jpg")],
            credits=[],
            external_ids=[],
            raw_data={"ep": 1},
            series=sd,
            season=se,
        )

        persistence_service.apply_metadata(session, fa, ed)
        session.flush()

        ep_ext = session.exec(select(EpisodeExt).filter(EpisodeExt.user_id == user_id)).first()
        assert ep_ext is not None
        assert ep_ext.still_path is not None and ep_ext.still_path.startswith("https://image.tmdb.org/t/p/w500/")

        series_core = session.exec(select(MediaCore).filter(MediaCore.kind == "tv_series", MediaCore.user_id == user_id)).first()
        assert series_core is not None
        tv_ext = session.exec(select(TVSeriesExt).filter(TVSeriesExt.core_id == series_core.id, TVSeriesExt.user_id == user_id)).first()
        assert tv_ext is not None
        assert tv_ext.backdrop_path == sd.backdrop_path
        assert tv_ext.status == sd.status
        assert tv_ext.episode_run_time == 45
        assert tv_ext.last_aired_date is not None
        assert tv_ext.raw_data is not None

        season_core = session.exec(select(MediaCore).filter(MediaCore.kind == "tv_season", MediaCore.user_id == user_id)).first()
        assert season_core is not None
        se_ext = session.exec(select(SeasonExt).filter(SeasonExt.core_id == season_core.id, SeasonExt.user_id == user_id)).first()
        assert se_ext is not None
        assert se_ext.raw_data is not None

        fa_movie = FileAsset(
            user_id=user_id,
            storage_id=None,
            full_path="/tmp/movie.mp4",
            filename="movie.mp4",
            relative_path="movie.mp4",
            size=456,
        )
        session.add(fa_movie)
        session.flush()

        md = ScraperMovieDetail(
            movie_id="m1",
            title="测试电影",
            overview="电影介绍",
            release_date="2024-02-02",
            poster_path="https://image.tmdb.org/t/p/w500/m_poster.jpg",
            backdrop_path="https://image.tmdb.org/t/p/w1280/m_backdrop.jpg",
            vote_average=8.1,
            vote_count=200,
            genres=["剧情"],
            provider="tmdb",
            artworks=[
                ScraperArtwork(type=ArtworkType.POSTER, url="https://image.tmdb.org/t/p/w500/m_poster.jpg"),
                ScraperArtwork(type=ArtworkType.BACKDROP, url="https://image.tmdb.org/t/p/w1280/m_backdrop.jpg"),
            ],
        )
        persistence_service.apply_metadata(session, fa_movie, md)
        session.flush()

        movie_core = session.exec(select(MediaCore).filter(MediaCore.kind == "movie", MediaCore.user_id == user_id)).first()
        assert movie_core is not None
        from models.media_models import MovieExt, Artwork
        mx = session.exec(select(MovieExt).filter(MovieExt.core_id == movie_core.id, MovieExt.user_id == user_id)).first()
        assert mx is not None
        art_p = session.exec(select(Artwork).filter(Artwork.user_id == user_id, Artwork.core_id == movie_core.id, Artwork.type == "poster")).first()
        art_b = session.exec(select(Artwork).filter(Artwork.user_id == user_id, Artwork.core_id == movie_core.id, Artwork.type == "backdrop")).first()
        assert art_p is not None and art_p.remote_url == mx.poster_path
        assert art_b is not None and art_b.remote_url == mx.backdrop_path
        print("OK")

if __name__ == "__main__":
    run()
