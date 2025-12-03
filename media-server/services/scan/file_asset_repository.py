from typing import Optional, Dict, List
from datetime import datetime

from core.db import get_session as get_db_session
from models.media_models import FileAsset
from services.storage.storage_client import StorageEntry
from sqlmodel import select
from sqlmodel import select



class SqlFileAssetRepository:
    def find_existing_file(self, user_id: int, storage_id: int, file_path: str) -> Optional[FileAsset]:
        with next(get_db_session()) as session:
            return session.exec(
                select(FileAsset).where(
                    (FileAsset.user_id == user_id) &
                    (FileAsset.storage_id == storage_id) &
                    (FileAsset.full_path == file_path)
                )
            ).first()

    def find_existing_files_bulk(self, user_id: int, storage_id: int, file_paths: List[str]) -> Dict[str, FileAsset]:
        if not file_paths:
            return {}
        with next(get_db_session()) as session:
            rows = session.exec(
                select(FileAsset).where(
                    (FileAsset.user_id == user_id) &
                    (FileAsset.storage_id == storage_id) &
                    (FileAsset.full_path.in_(file_paths))
                )
            ).all()
            return {r.full_path: r for r in rows}

    def update_file_info(self, file_record: FileAsset, entry: StorageEntry) -> bool:
        with next(get_db_session()) as session:
            try:
                changed = False
                if entry.size is not None and file_record.size != entry.size:
                    file_record.size = entry.size
                    changed = True
                if entry.etag and file_record.etag != entry.etag:
                    file_record.etag = entry.etag
                    changed = True
                if changed:
                    file_record.updated_at = datetime.now()
                    session.add(file_record)
                    session.commit()
                    return True
                return False
            except Exception:
                session.rollback()
                return False

    def bulk_update_file_info(self, file_records: List[FileAsset]) -> int:
        if not file_records:
            return 0
        with next(get_db_session()) as session:
            try:
                for fr in file_records:
                    fr.updated_at = datetime.now()
                    session.add(fr)
                session.commit()
                return len(file_records)
            except Exception:
                session.rollback()
                return 0

    def create_file_record(self, storage_id: int, entry: StorageEntry, file_info: Dict, user_id: int) -> Optional[FileAsset]:
        import mimetypes
        from pathlib import Path
        with next(get_db_session()) as session:
            try:
                path_parts = Path(entry.path).parts
                if len(path_parts) > 1:
                    relative_path = str(Path(*path_parts[1:]))
                else:
                    relative_path = "."
                media_file = FileAsset(
                    user_id=user_id,
                    storage_id=storage_id,
                    full_path=entry.path,
                    filename=entry.name,
                    relative_path=relative_path,
                    size=entry.size or 0,
                    mimetype=mimetypes.guess_type(entry.path)[0],
                    resolution=file_info.get("resolution"),
                    etag=entry.etag,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                session.add(media_file)
                session.commit()
                return media_file
            except Exception:
                session.rollback()
                return None

    def bulk_create_file_records(self, storage_id: int, entries: List[StorageEntry], file_info_map: Dict[str, Dict], user_id: int) -> List[FileAsset]:
        if not entries:
            return []
        import mimetypes
        from pathlib import Path
        created: List[FileAsset] = []
        with next(get_db_session()) as session:
            try:
                for entry in entries:
                    path_parts = Path(entry.path).parts
                    if len(path_parts) > 1:
                        relative_path = str(Path(*path_parts[1:]))
                    else:
                        relative_path = "."
                    fi = file_info_map.get(entry.path, {})
                    media_file = FileAsset(
                        user_id=user_id,
                        storage_id=storage_id,
                        full_path=entry.path,
                        filename=entry.name,
                        relative_path=relative_path,
                        size=entry.size or 0,
                        mimetype=mimetypes.guess_type(entry.path)[0],
                        resolution=fi.get("resolution"),
                        etag=entry.etag,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(media_file)
                    created.append(media_file)
                session.commit()
                for mf in created:
                    session.refresh(mf)
                return created
            except Exception:
                session.rollback()
                return []
