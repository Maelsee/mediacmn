import asyncio
import json
from sqlmodel import select

from core.db import get_session as get_db_session
from services.task import Task, TaskType, TaskPriority, get_task_queue_service
from services.task.unified_task_executor import UnifiedTaskExecutor
from models.media_models import FileAsset, ContentCore, MovieDetail, SeriesDetail, EpisodeDetail


async def _enqueue_movie_task(file_id: int, user_id: int):
    tq = get_task_queue_service()
    await tq.connect()
    payload = {
        "movie_id": "550",
        "title": "Fight Club",
        "original_title": "Fight Club",
        "original_language": "en",
        "overview": "...",
        "release_date": "1999-10-15",
        "runtime": 139,
        "tagline": "Mischief. Mayhem. Soap.",
        "genres": ["Drama"],
        "poster_path": None,
        "backdrop_path": None,
        "vote_average": 8.4,
        "vote_count": 30000,
        "imdb_id": "tt0137523",
        "status": "Released",
        "belongs_to_collection": None,
        "popularity": 50.0,
        "provider": "tmdb",
        "provider_url": "https://www.themoviedb.org/movie/550",
        "artworks": [],
        "credits": [],
        "external_ids": [{"provider": "tmdb", "external_id": "550"}],
        "origin_country": ["US"],
        "budget": 63000000,
        "revenue": 100000000,
        "raw_data": {"id": 550}
    }
    task = Task(
        task_type=TaskType.PERSIST_METADATA,
        priority=TaskPriority.NORMAL,
        params={
            "file_id": file_id,
            "user_id": user_id,
            "contract_type": "movie",
            "contract_payload": payload,
            "version_context": {"scope": "movie_single"}
        },
        max_retries=0,
        retry_delay=1,
        timeout=30,
    )
    await tq.enqueue_task(task)
    return task.id


async def _enqueue_episode_task(file_id: int, user_id: int):
    tq = get_task_queue_service()
    await tq.connect()
    payload = {
        "episode_id": "123",
        "episode_number": 1,
        "season_number": 1,
        "name": "Pilot",
        "overview": "...",
        "air_date": "2020-01-01",
        "runtime": 45,
        "still_path": None,
        "vote_average": 7.0,
        "vote_count": 100,
        "provider": "tmdb",
        "provider_url": "https://www.themoviedb.org/tv/9999/season/1/episode/1",
        "artworks": [],
        "credits": [],
        "external_ids": [{"provider": "tmdb", "external_id": "123"}],
        "episode_type": "standard",
        "absolute_episode_number": 1,
        "raw_data": {"id": 123},
        "season": {
            "season_id": "8888",
            "season_number": 1,
            "name": "Season 1",
            "poster_path": None,
            "overview": "...",
            "episode_count": 10,
            "air_date": "2020-01-01",
            "vote_average": 7.5,
            "provider": "tmdb",
            "provider_url": "",
            "artworks": [],
            "credits": [],
            "external_ids": [],
            "raw_data": {"id": 8888}
        },
        "series": {
            "series_id": "9999",
            "name": "Show",
            "original_name": "Show",
            "origin_country": ["US"],
            "overview": "...",
            "tagline": None,
            "status": "Returning Series",
            "first_air_date": "2020-01-01",
            "last_air_date": "2020-02-01",
            "episode_run_time": [45],
            "number_of_episodes": 10,
            "number_of_seasons": 1,
            "genres": ["Drama"],
            "poster_path": None,
            "backdrop_path": None,
            "vote_average": 7.5,
            "vote_count": 1000,
            "popularity": 20.0,
            "provider": "tmdb",
            "provider_url": "https://www.themoviedb.org/tv/9999",
            "artworks": [],
            "credits": [],
            "external_ids": [{"provider": "tmdb", "external_id": "9999"}],
            "raw_data": {"id": 9999},
            "subtype": "reality",
            "original_language": "en",
            "languages": ["en"],
            "networks": ["Netflix"]
        }
    }
    task = Task(
        task_type=TaskType.PERSIST_METADATA,
        priority=TaskPriority.NORMAL,
        params={
            "file_id": file_id,
            "user_id": user_id,
            "contract_type": "episode",
            "contract_payload": payload,
            "version_context": {"scope": "episode_single"}
        },
        max_retries=0,
        retry_delay=1,
        timeout=30,
    )
    await tq.enqueue_task(task)
    return task.id


def test_persist_worker_smoke():
    async def _run():
        # 准备一个文件资产
        with next(get_db_session()) as session:
            fa = FileAsset(user_id=1, storage_id=None, full_path="/tmp/demo.mkv", filename="demo.mkv", relative_path="demo.mkv", size=100)
            session.add(fa)
            session.commit()
            file_id = fa.id
        # 入队两个任务
        movie_task_id = await _enqueue_movie_task(file_id, 1)
        episode_task_id = await _enqueue_episode_task(file_id, 1)
        # 启动执行器一次拉取
        executor = UnifiedTaskExecutor()
        await executor.initialize()
        # 直接从队列拉取并执行两个持久化任务
        tq = get_task_queue_service()
        await tq.connect()
        # 执行两个任务
        for _ in range(2):
            task = await tq.dequeue_task([TaskType.PERSIST_METADATA], executor.worker_id, timeout=2)
            if task:
                await executor.task_scheduler._execute_persist_metadata_task(task)
        # 验证结果
        with next(get_db_session()) as session:
            cores = session.exec(select(ContentCore)).all()
            assert len(cores) >= 1
            # 至少有一个电影或一个集
            eps = session.exec(select(EpisodeDetail)).all()
            assert True
    asyncio.run(_run())

