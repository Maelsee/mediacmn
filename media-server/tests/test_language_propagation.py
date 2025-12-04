import os
import sys
import asyncio
from typing import Optional, List, Dict

from sqlmodel import SQLModel, Session, create_engine, select

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.task import Task, TaskType, TaskPriority
from services.task.unified_task_scheduler import UnifiedTaskScheduler, TaskExecutionResult
from services.media.metadata_enricher import metadata_enricher
from services.scraper.base import ScraperSearchResult, MediaType, ScraperMovieDetail
from services.scraper import scraper_manager
from models.user import User
from models.media_models import FileAsset


def test_combined_task_language_param_propagates():
    async def _run():
        scheduler = UnifiedTaskScheduler()
        scheduler._initialized = True
        captured: Dict[str, Optional[object]] = {"language": None, "file_ids": None}

        async def fake_create_metadata_task(storage_id: int, file_ids: List[int], user_id: int = 1, language: str = "zh-CN", priority: TaskPriority = TaskPriority.NORMAL, batch_size: int = 20):
            captured["language"] = language
            captured["file_ids"] = list(file_ids)
            return ["t1"]

        scheduler.create_metadata_task = fake_create_metadata_task  # type: ignore

        async def fake_scan(task: Task) -> TaskExecutionResult:
            return TaskExecutionResult(success=True, data={"new_file_ids": [123], "scan_result": {}})

        scheduler._execute_scan_task = fake_scan  # type: ignore

        t = Task(task_type=TaskType.COMBINED_SCAN, priority=TaskPriority.NORMAL, params={"storage_id": 1, "user_id": 1, "language": "en-US"})
        await scheduler._execute_combined_task(t)
        assert captured["language"] == "en-US"
        assert captured["file_ids"] == [123]

    asyncio.run(_run())


def test_enricher_passes_language_to_plugin():
    async def _run():
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)

        import core.db as core_db
        core_db.engine = engine

        def get_session_override():
            with Session(engine) as s:
                yield s

        core_db.get_session = get_session_override  # type: ignore

        with Session(engine) as session:
            u = User(email="user@example.com", hashed_password="x")
            session.add(u)
            session.flush()
            fa = FileAsset(user_id=u.id, storage_id=None, full_path="/tmp/demo.mkv", filename="demo.mkv", relative_path="demo.mkv", size=100)
            session.add(fa)
            session.commit()
            file_id = fa.id

        async def ensure_plugins_override():
            return None

        scraper_manager.ensure_default_plugins = ensure_plugins_override  # type: ignore

        async def search_with_type_correction_override(title: str, year: Optional[int], initial_type: MediaType, language: str):
            r = ScraperSearchResult(id="xyz", title="Demo", provider="tmdb", year=2024)
            return [r], MediaType.MOVIE

        scraper_manager.search_with_type_correction = search_with_type_correction_override  # type: ignore

        class DummyPlugin:
            name = "tmdb"
            version = "1"
            description = "d"
            supported_media_types = [MediaType.MOVIE, MediaType.TV_SERIES, MediaType.TV_EPISODE]
            default_language = "zh-CN"
            priority = 100
            captured_language: Optional[str] = None

            def configure(self, config: dict) -> bool:
                return True

            async def test_connection(self) -> bool:
                return True

            async def get_movie_details(self, movie_id: str, language: str = "zh-CN") -> Optional[ScraperMovieDetail]:
                self.captured_language = language
                return ScraperMovieDetail(movie_id="m1", title="t1", provider="tmdb")

            async def get_series_details(self, series_id: str, language: str = "zh-CN"):
                return None

            async def get_season_details(self, series_id: str, season_number: int, language: str = "zh-CN"):
                return None

            async def get_episode_details(self, series_id: str, season_number: int, episode_number: int, language: str = "zh-CN"):
                return None

        plugin = DummyPlugin()
        scraper_manager._plugins["tmdb"] = plugin  # type: ignore

        class StubQueue:
            async def connect(self) -> bool:
                return True

            async def enqueue_task(self, task: Task) -> bool:
                return True

        import services.task as task_pkg
        def get_tq():
            return StubQueue()
        task_pkg.get_task_queue_service = get_tq  # type: ignore

        ok = await metadata_enricher.enrich_media_file(file_id, preferred_language="en-US", storage_id=None)
        assert ok
        assert plugin.captured_language == "en-US"

    asyncio.run(_run())


def test_combined_task_candidate_selection_from_encountered_paths():
    async def _run():
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)

        import core.db as core_db
        core_db.engine = engine

        def get_session_override():
            with Session(engine) as s:
                yield s

        core_db.get_session = get_session_override  # type: ignore

        with Session(engine) as session:
            u = User(email="user2@example.com", hashed_password="x")
            session.add(u)
            session.flush()
            fa = FileAsset(user_id=u.id, storage_id=2, full_path="/tmp/movie2.mkv", filename="movie2.mkv", relative_path="movie2.mkv", size=200)
            session.add(fa)
            session.commit()
            file_id = fa.id

        scheduler = UnifiedTaskScheduler()
        scheduler._initialized = True
        captured: Dict[str, Optional[object]] = {"file_ids": None}

        async def fake_create_metadata_task(storage_id: int, file_ids: List[int], user_id: int = 1, language: str = "zh-CN", priority: TaskPriority = TaskPriority.NORMAL, batch_size: int = 20):
            captured["file_ids"] = list(file_ids)
            return ["t1"]

        scheduler.create_metadata_task = fake_create_metadata_task  # type: ignore

        async def fake_scan(task: Task) -> TaskExecutionResult:
            return TaskExecutionResult(success=True, data={"new_file_ids": [], "scan_result": {"encountered_media_paths": ["/tmp/movie2.mkv"]}})

        scheduler._execute_scan_task = fake_scan  # type: ignore

        t = Task(task_type=TaskType.COMBINED_SCAN, priority=TaskPriority.NORMAL, params={"storage_id": 2, "user_id": 1, "language": "en-US"})
        await scheduler._execute_combined_task(t)
        assert captured["file_ids"] == [file_id]

    asyncio.run(_run())

