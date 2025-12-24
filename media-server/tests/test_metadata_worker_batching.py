import asyncio
from typing import Any, Dict, List


class DummyStore:
    def __init__(self) -> None:
        self.updates = []

    async def update_status(self, task_id: str, status: Any, **kwargs: Any) -> None:
        self.updates.append((task_id, status, kwargs))


class DummySettings:
    SIDE_CAR_LOCALIZATION_ENABLED = True


class DummyScraperManager:
    def __init__(self) -> None:
        self.is_running = True

    async def startup(self) -> None:
        return None


class Recorder:
    def __init__(self) -> None:
        self.enrich_calls: List[List[int]] = []
        self.persist_calls: List[Dict[str, Any]] = []
        self.localize_calls: List[Dict[str, Any]] = []


async def _run_metadata_worker(monkeypatch, total_files: int, batch_size: int) -> Recorder:
    from services.task import consumers
    from services.media import metadata_enricher as me_module
    from services.scraper import manager as scraper_manager_module
    from services.task import producer as producer_module

    rec = Recorder()

    async def fake_enrich_multiple_files(file_ids: List[int], user_id: int, max_concurrency: int = 20):
        rec.enrich_calls.append(list(file_ids))
        results = []
        for fid in file_ids:
            results.append(
                {
                    "user_id": user_id,
                    "file_id": fid,
                    "contract_type": "movie",
                    "contract_payload": {"id": fid},
                    "path_info": {},
                    "success": True,
                    "error_msg": "",
                }
            )
        return results

    async def fake_create_persist_task(
        user_id: int,
        file_id: int,
        contract_type: str,
        contract_payload: Dict[str, Any],
        path_info: Dict[str, Any],
        idempotency_key: str,
    ) -> None:
        rec.persist_calls.append(
            {
                "user_id": user_id,
                "file_id": file_id,
                "contract_type": contract_type,
                "contract_payload": contract_payload,
                "path_info": path_info,
                "idempotency_key": idempotency_key,
            }
        )

    async def fake_create_localize_task(
        user_id: int,
        file_id: int,
        storage_id: int,
        idempotency_key: str,
    ) -> None:
        rec.localize_calls.append(
            {
                "user_id": user_id,
                "file_id": file_id,
                "storage_id": storage_id,
                "idempotency_key": idempotency_key,
            }
        )

    dummy_store = DummyStore()

    monkeypatch.setattr(consumers, "get_state_store", lambda: dummy_store)
    monkeypatch.setattr("services.task.consumers.get_settings", lambda: DummySettings())
    monkeypatch.setattr(me_module.metadata_enricher, "enrich_multiple_files", fake_enrich_multiple_files)
    monkeypatch.setattr(scraper_manager_module, "scraper_manager", DummyScraperManager())
    monkeypatch.setattr(producer_module, "create_persist_task", fake_create_persist_task)
    monkeypatch.setattr(producer_module, "create_localize_task", fake_create_localize_task)

    payload = {
        "user_id": 1,
        "file_ids": list(range(total_files)),
        "storage_id": 10,
    }

    original_batch_size = 200
    try:
        from services.task.consumers import metadata_worker

        await metadata_worker("task-1", payload)
    finally:
        consumers.metadata_worker.__globals__["batch_size"] = original_batch_size

    return rec


def test_metadata_worker_creates_tasks_in_batches(monkeypatch):
    total_files = 450
    rec = asyncio.run(_run_metadata_worker(monkeypatch, total_files, batch_size=200))
    assert sum(len(c) for c in rec.enrich_calls) == total_files
    assert len(rec.persist_calls) == total_files
    assert len(rec.localize_calls) == total_files

