from __future__ import annotations

from typing import Any, Dict, List

import logging

from core.db import AsyncSessionLocal
from models.media_models import FileAsset
from .metadata_persistence_service import MetadataPersistenceService


logger = logging.getLogger(__name__)


class MetadataPersistenceAsyncService:
    def __init__(self) -> None:
        self._svc = MetadataPersistenceService()

    async def apply_metadata_single(self, item: Dict[str, Any]) -> bool:
        async with AsyncSessionLocal() as async_session:
            def _run(sync_session) -> bool:
                file_id = item.get("file_id")
                contract_type = item.get("contract_type")
                metadata = item.get("contract_payload") or {}
                path_info = item.get("path_info") or {}
                if not file_id or not contract_type or not metadata:
                    return False
                media_file = sync_session.get(FileAsset, file_id)
                if not media_file:
                    return False
                ok = self._svc.apply_metadata(
                    sync_session,
                    media_file,
                    metadata=metadata,
                    metadata_type=contract_type,
                    path_info=path_info,
                )
                if ok:
                    sync_session.commit()
                else:
                    sync_session.rollback()
                return ok

            return await async_session.run_sync(_run)

    async def apply_metadata_batch(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not items:
            return {"processed": 0, "succeeded": 0, "errors": []}

        async with AsyncSessionLocal() as async_session:
            def _run(sync_session) -> Dict[str, Any]:
                processed = 0
                succeeded = 0
                errors: List[Dict[str, Any]] = []
                for item in items:
                    file_id = item.get("file_id")
                    contract_type = item.get("contract_type")
                    metadata = item.get("contract_payload") or {}
                    path_info = item.get("path_info") or {}
                    if not file_id or not contract_type or not metadata:
                        errors.append({"file_id": file_id, "error": "missing_params"})
                        continue
                    media_file = sync_session.get(FileAsset, file_id)
                    if not media_file:
                        errors.append({"file_id": file_id, "error": "file_not_found"})
                        continue
                    ok = self._svc.apply_metadata(
                        sync_session,
                        media_file,
                        metadata=metadata,
                        metadata_type=contract_type,
                        path_info=path_info,
                    )
                    processed += 1
                    if ok:
                        succeeded += 1
                    else:
                        errors.append({"file_id": file_id, "error": "apply_failed"})
                sync_session.commit()
                return {"processed": processed, "succeeded": succeeded, "errors": errors}

            return await async_session.run_sync(_run)

