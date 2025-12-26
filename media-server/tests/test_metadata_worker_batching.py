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
        self.enrich_ids: List[int] = []
        self.persist_calls: List[Dict[str, Any]] = []
        self.localize_calls: List[Dict[str, Any]] = []


async def _run_metadata_worker(monkeypatch, total_files: int) -> Recorder:
    from services.task import consumers
    from services.media import metadata_enricher as me_module
    from services.scraper import manager as scraper_manager_module
    from services.task import producer as producer_module

    rec = Recorder()

    async def fake_iter_enrich_multiple_files(file_ids: List[int], user_id: int, max_concurrency: int = 20):
        for fid in file_ids:
            rec.enrich_ids.append(fid)
            yield {
                "user_id": user_id,
                "file_id": fid,
                "contract_type": "movie",
                "contract_payload": {"id": fid},
                "path_info": {},
                "success": True,
                "error_msg": "",
            }

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
    monkeypatch.setattr(me_module.metadata_enricher, "iter_enrich_multiple_files", fake_iter_enrich_multiple_files)
    monkeypatch.setattr(scraper_manager_module, "scraper_manager", DummyScraperManager())
    monkeypatch.setattr(producer_module, "create_persist_task", fake_create_persist_task)
    monkeypatch.setattr(producer_module, "create_localize_task", fake_create_localize_task)

    payload = {
        "user_id": 1,
        "file_ids": list(range(total_files)),
        "storage_id": 10,
    }

    from services.task.consumers import metadata_worker
    await metadata_worker("task-1", payload)

    return rec


def test_metadata_worker_streaming_creates_tasks(monkeypatch):
    total_files = 450
    rec = asyncio.run(_run_metadata_worker(monkeypatch, total_files))
    assert len(rec.enrich_ids) == total_files
    assert len(rec.persist_calls) == total_files
    assert len(rec.localize_calls) == total_files


def test_persist_batch_worker_uses_batch_service(monkeypatch):
    from services.task import consumers
    from services.media import metadata_persistence_async_service as async_module

    dummy_store = DummyStore()

    class DummyBatchService:
        def __init__(self) -> None:
            self.calls: List[List[Dict[str, Any]]] = []

        async def apply_metadata_batch(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
            self.calls.append(items)
            return {"processed": len(items), "succeeded": len(items), "errors": []}

    svc = DummyBatchService()

    monkeypatch.setattr(consumers, "get_state_store", lambda: dummy_store)
    monkeypatch.setattr(async_module, "MetadataPersistenceAsyncService", lambda: svc)

    payload = {
        "user_id": 1,
        "items": [
            {"file_id": 1, "contract_type": "movie", "contract_payload": {"id": 1}, "path_info": {}},
            {"file_id": 2, "contract_type": "movie", "contract_payload": {"id": 2}, "path_info": {}},
        ],
    }

    from services.task.consumers import persist_batch_worker

    asyncio.run(persist_batch_worker("batch-1", payload))

    assert len(svc.calls) == 1
    assert len(svc.calls[0]) == 2
    assert any(u[1] == consumers.TaskStatus.SUCCESS for u in dummy_store.updates)
