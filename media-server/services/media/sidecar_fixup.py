# import logging
# from typing import Dict, Any, List, Optional, Tuple

# from sqlmodel import select

# from core.db import get_session as get_db_session
# from models.media_models import MediaCore, FileAsset, Artwork
# from services.storage.storage_service import StorageService

# logger = logging.getLogger(__name__)


# async def scan_and_fix(storage_id: int, root_path: str = "/", dry_run: bool = False) -> Dict[str, Any]:
#     try:
#         storage_service = StorageService()
#         storage_client = await storage_service.get_client(storage_id)
#         if not storage_client:
#             return {"success": False, "error": "storage_client_not_available"}

#         with next(get_db_session()) as session:
#             from models.storage_models import StorageConfig
#             storage_config = session.exec(select(StorageConfig).where(StorageConfig.id == storage_id)).first()
#             if not storage_config:
#                 return {"success": False, "error": "storage_config_not_found"}
#             user_id = storage_config.user_id

#             queue: List[str] = [root_path if root_path else "/"]
#             visited: set = set()
#             added: int = 0
#             updated: int = 0
#             checked: int = 0
#             errors: List[str] = []

#             async def list_once(path: str) -> Tuple[List[str], List[str]]:
#                 try:
#                     entries = await storage_client.list_dir(path, depth=1)
#                     dirs: List[str] = []
#                     files: List[str] = []
#                     for e in entries:
#                         if e.is_dir:
#                             dirs.append(e.path)
#                         else:
#                             files.append(e.path)
#                     return dirs, files
#                 except Exception as e:
#                     errors.append(f"list_error:{path}:{e}")
#                     return [], []

#             async def detect_sidecars(files: List[str]) -> Dict[str, str]:
#                 m: Dict[str, str] = {}
#                 for p in files:
#                     lp = p.lower()
#                     if lp.endswith(".nfo"):
#                         m["nfo"] = p
#                     elif lp.endswith("poster.jpg") or lp.endswith("poster.jpeg"):
#                         m["poster"] = p
#                     elif lp.endswith("fanart.jpg") or lp.endswith("fanart.jpeg") or lp.endswith("backdrop.jpg"):
#                         m["fanart"] = p
#                     elif lp.endswith("folder.jpg"):
#                         m.setdefault("poster", p)
#                     elif lp.endswith("banner.jpg"):
#                         m.setdefault("fanart", p)
#                 return m

#             async def find_core_id(dir_path: str) -> Optional[int]:
#                 try:
#                     stmt = select(FileAsset).where(
#                         FileAsset.user_id == user_id,
#                         FileAsset.storage_id == storage_id,
#                         FileAsset.full_path.like(f"{dir_path}/%"),
#                         FileAsset.core_id.is_not(None),
#                     )
#                     fa = session.exec(stmt).first()
#                     if fa and fa.core_id:
#                         return fa.core_id
#                     return None
#                 except Exception as e:
#                     errors.append(f"core_map_error:{dir_path}:{e}")
#                     return None

#             while queue:
#                 cur = queue.pop(0)
#                 if cur in visited:
#                     continue
#                 visited.add(cur)
#                 dirs, files = await list_once(cur)
#                 sidecars = await detect_sidecars(files)
#                 checked += 1
#                 if sidecars:
#                     core_id = await find_core_id(cur)
#                     if core_id:
#                         try:
#                             core = session.exec(select(MediaCore).where(MediaCore.id == core_id)).first()
#                             if core:
#                                 if sidecars.get("nfo"):
#                                     if not dry_run:
#                                         core.nfo_exists = True
#                                         core.nfo_path = sidecars["nfo"]
#                                     updated += 1
#                                 if sidecars.get("poster"):
#                                     poster_path = sidecars["poster"]
#                                     row = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == core.id, Artwork.type == "poster")).first()
#                                     if row:
#                                         if not dry_run:
#                                             row.local_path = poster_path
#                                             row.exists_local = True
#                                             row.preferred = True or row.preferred
#                                         updated += 1
#                                     else:
#                                         if not dry_run:
#                                             session.add(Artwork(user_id=user_id, core_id=core.id, type="poster", local_path=poster_path, preferred=True, exists_local=True, exists_remote=False))
#                                         added += 1
#                                 if sidecars.get("fanart"):
#                                     fanart_path = sidecars["fanart"]
#                                     row2 = session.exec(select(Artwork).where(Artwork.user_id == user_id, Artwork.core_id == core.id, Artwork.type.in_(["backdrop", "fanart"]))).first()
#                                     if row2:
#                                         if not dry_run:
#                                             row2.local_path = fanart_path
#                                             row2.exists_local = True
#                                             row2.preferred = True or row2.preferred
#                                         updated += 1
#                                     else:
#                                         if not dry_run:
#                                             session.add(Artwork(user_id=user_id, core_id=core.id, type="backdrop", local_path=fanart_path, preferred=True, exists_local=True, exists_remote=False))
#                                         added += 1
#                                 if not dry_run:
#                                     session.commit()
#                         except Exception as e:
#                             errors.append(f"fix_error:{cur}:{e}")
#                 for d in dirs:
#                     queue.append(d)

#             return {
#                 "success": True,
#                 "checked_dirs": checked,
#                 "added": added,
#                 "updated": updated,
#                 "errors": errors,
#             }
#     except Exception as e:
#         return {"success": False, "error": str(e)}