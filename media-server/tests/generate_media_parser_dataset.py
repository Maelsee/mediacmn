import argparse
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class FileAssetRow:
    id: int
    user_id: int
    full_path: str
    core_id: Optional[int]


@dataclass(frozen=True)
class MediaCoreRow:
    id: int
    user_id: int
    kind: str
    title: Optional[str]
    original_title: Optional[str]
    year: Optional[int]
    parent_id: Optional[int]


@dataclass(frozen=True)
class EpisodeExtRow:
    core_id: int
    user_id: int
    season_number: Optional[int]
    episode_number: Optional[int]


@dataclass(frozen=True)
class SeasonExtRow:
    core_id: int
    user_id: int
    season_number: Optional[int]


def _iter_copy_rows(sql_path: Path, table_name: str) -> Iterator[str]:
    copy_header = f"COPY public.{table_name} "
    in_copy = False
    with sql_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not in_copy:
                if line.startswith(copy_header):
                    in_copy = True
                continue

            if line.startswith("\\."):
                break

            yield line.rstrip("\n")


def _parse_nullable_int(value: str) -> Optional[int]:
    if value == "\\N" or value == "":
        return None
    return int(value)


def _reservoir_sample(items: Iterable[FileAssetRow], k: int, seed: int) -> List[FileAssetRow]:
    rng = random.Random(seed)
    sample: List[FileAssetRow] = []
    for i, it in enumerate(items, start=1):
        if len(sample) < k:
            sample.append(it)
            continue
        j = rng.randrange(1, i + 1)
        if j <= k:
            sample[j - 1] = it
    return sample


def _load_media_core_map(sql_path: Path) -> Dict[Tuple[int, int], MediaCoreRow]:
    cores: Dict[Tuple[int, int], MediaCoreRow] = {}
    for row in _iter_copy_rows(sql_path, "media_core"):
        cols = row.split("\t")
        if len(cols) < 7:
            continue
        core_id = int(cols[0])
        user_id = int(cols[1])
        kind = cols[2]
        title = cols[4] if cols[4] != "\\N" else None
        original_title = cols[5] if cols[5] != "\\N" else None
        year = _parse_nullable_int(cols[6])
        parent_id = _parse_nullable_int(cols[12])
        cores[(user_id, core_id)] = MediaCoreRow(
            id=core_id,
            user_id=user_id,
            kind=kind,
            title=title,
            original_title=original_title,
            year=year,
            parent_id=parent_id,
        )
    return cores


def _load_episode_ext_map(sql_path: Path) -> Dict[Tuple[int, int], EpisodeExtRow]:
    eps: Dict[Tuple[int, int], EpisodeExtRow] = {}
    for row in _iter_copy_rows(sql_path, "episode_ext"):
        cols = row.split("\t")
        if len(cols) < 8:
            continue
        user_id = int(cols[1])
        core_id = int(cols[2])
        episode_number = _parse_nullable_int(cols[6])
        season_number = _parse_nullable_int(cols[7])
        eps[(user_id, core_id)] = EpisodeExtRow(
            core_id=core_id,
            user_id=user_id,
            season_number=season_number,
            episode_number=episode_number,
        )
    return eps


def _load_season_ext_map(sql_path: Path) -> Dict[Tuple[int, int], SeasonExtRow]:
    seasons: Dict[Tuple[int, int], SeasonExtRow] = {}
    for row in _iter_copy_rows(sql_path, "season_ext"):
        cols = row.split("\t")
        if len(cols) < 6:
            continue
        user_id = int(cols[1])
        core_id = int(cols[2])
        season_number = _parse_nullable_int(cols[5])
        seasons[(user_id, core_id)] = SeasonExtRow(
            core_id=core_id,
            user_id=user_id,
            season_number=season_number,
        )
    return seasons


def _load_media_version_core_map(sql_path: Path) -> Dict[Tuple[int, int], int]:
    version_to_core: Dict[Tuple[int, int], int] = {}
    for row in _iter_copy_rows(sql_path, "media_version"):
        cols = row.split("\t")
        if len(cols) < 3:
            continue
        version_id = int(cols[0])
        user_id = int(cols[1])
        core_id = _parse_nullable_int(cols[2])
        if core_id is None:
            continue
        version_to_core[(user_id, version_id)] = core_id
    return version_to_core


def _iter_labelable_file_assets(sql_path: Path, version_to_core: Dict[Tuple[int, int], int]) -> Iterator[FileAssetRow]:
    for row in _iter_copy_rows(sql_path, "file_asset"):
        cols = row.split("\t")
        if len(cols) < 7:
            continue
        asset_id = int(cols[0])
        user_id = int(cols[1])
        full_path = cols[3]
        core_id = _parse_nullable_int(cols[6])
        if core_id is None and len(cols) >= 8:
            version_id = _parse_nullable_int(cols[7])
            if version_id is not None:
                core_id = version_to_core.get((user_id, version_id))
        if core_id is None and len(cols) >= 9:
            season_version_id = _parse_nullable_int(cols[8])
            if season_version_id is not None:
                core_id = version_to_core.get((user_id, season_version_id))
        if core_id is None:
            yield FileAssetRow(id=asset_id, user_id=user_id, full_path=full_path, core_id=None)
            continue
        yield FileAssetRow(id=asset_id, user_id=user_id, full_path=full_path, core_id=core_id)


def _guess_type_from_path(full_path: str) -> str:
    s = str(full_path)
    if any(seg in s for seg in ("动画", "综艺", "剧集", "电视剧")):
        return "episode"
    if re.search(r"S\d{1,2}E\d{1,4}", s, flags=re.IGNORECASE):
        return "episode"
    if re.search(r"第\s*\d+\s*[话集]", s):
        return "episode"
    if re.search(r"\bE\d{1,4}\b", s, flags=re.IGNORECASE):
        return "episode"
    return "movie"


def _extract_year_from_path(full_path: str) -> Optional[int]:
    s = str(full_path)
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", s)]
    years = [y for y in years if y not in (1080, 2160, 720)]
    if not years:
        return None
    return years[0]


def _extract_season_episode_from_path(full_path: str) -> Tuple[Optional[int], Optional[int]]:
    s = str(full_path)
    m = re.search(r"S(?P<s>\d{1,2})E(?P<e>\d{1,4})", s, flags=re.IGNORECASE)
    if m:
        return int(m.group("s")), int(m.group("e"))

    m = re.search(r"第\s*(?P<s>\d+)\s*季", s)
    season = int(m.group("s")) if m else None

    m = re.search(r"第\s*(?P<e>\d+)\s*[话集]", s)
    episode = int(m.group("e")) if m else None
    if episode is None:
        m = re.search(r"\bE(?P<e>\d{1,4})\b", s, flags=re.IGNORECASE)
        if m:
            episode = int(m.group("e"))

    return season, episode


def _is_ignorable_segment(segment: str) -> bool:
    if not segment:
        return True
    s = segment.strip()
    if not s:
        return True
    if s in {"dav", "综艺", "动画", "电影", "剧集", "电视剧", "外语", "华语"}:
        return True
    if re.fullmatch(r"\d+", s):
        return True
    if re.fullmatch(r"\d+~\d+", s):
        return True
    if re.fullmatch(r"S\d{1,2}", s, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"Season\s*\d+", s, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"第\s*\d+\s*季", s):
        return True
    if re.fullmatch(r"\d{3,4}p", s, flags=re.IGNORECASE):
        return True
    return False


def _extract_title_from_path(full_path: str) -> Optional[str]:
    parts = [p for p in re.split(r"[\\/]+", str(full_path)) if p]
    if len(parts) >= 2:
        for seg in reversed(parts[:-1]):
            if _is_ignorable_segment(seg):
                continue
            if re.search(r"[\u4e00-\u9fff]", seg) or (re.search(r"[A-Za-z]", seg) and len(seg) >= 2):
                return seg.strip() or None

    filename = os.path.basename(str(full_path))
    base = re.sub(r"\.[^.]+$", "", filename)
    candidates = re.findall(r"[\u4e00-\u9fff]{2,}", base)
    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]
    return None


def _resolve_series_core(user_id: int, core_id: int, media_core_map: Dict[Tuple[int, int], MediaCoreRow]) -> Optional[MediaCoreRow]:
    seen: set[int] = set()
    current = media_core_map.get((user_id, core_id))
    while current and current.parent_id is not None and current.id not in seen:
        if current.kind == "series":
            return current
        seen.add(current.id)
        current = media_core_map.get((user_id, current.parent_id))
    if current and current.kind == "series":
        return current
    return None


def _build_labels(
    assets: List[FileAssetRow],
    media_core_map: Dict[Tuple[int, int], MediaCoreRow],
    episode_ext_map: Dict[Tuple[int, int], EpisodeExtRow],
    season_ext_map: Dict[Tuple[int, int], SeasonExtRow],
) -> Tuple[List[FileAssetRow], Dict[int, Dict[str, Any]]]:
    keep_assets: List[FileAssetRow] = []
    labels_by_asset_id: Dict[int, Dict[str, Any]] = {}

    for a in assets:
        expected_type: Optional[str] = None
        expected_title: Optional[str] = None
        expected_year: Optional[int] = None
        expected_season: Optional[int] = None
        expected_episode: Optional[int] = None
        label_source = "heuristic"

        core: Optional[MediaCoreRow] = None
        if a.core_id is not None:
            core = media_core_map.get((a.user_id, a.core_id))

        if core:
            label_source = "db"
            expected_type = "movie" if core.kind == "movie" else "episode"
            if core.kind in {"episode", "season"}:
                series_core = _resolve_series_core(a.user_id, a.core_id, media_core_map)
                base_core = series_core or core
            else:
                base_core = core

            title_candidates = [base_core.title, base_core.original_title]
            title_candidates = [t for t in title_candidates if t]
            expected_title = title_candidates or None
            expected_year = base_core.year

            if core.kind == "episode":
                ep = episode_ext_map.get((a.user_id, a.core_id))
                if ep:
                    expected_season = ep.season_number
                    expected_episode = ep.episode_number
            elif core.kind == "season":
                se = season_ext_map.get((a.user_id, a.core_id))
                if se:
                    expected_season = se.season_number
        else:
            expected_type = _guess_type_from_path(a.full_path)
            ht = _extract_title_from_path(a.full_path)
            expected_title = [ht] if ht else None
            expected_year = _extract_year_from_path(a.full_path)
            if expected_type == "episode":
                expected_season, expected_episode = _extract_season_episode_from_path(a.full_path)

        keep_assets.append(a)
        labels_by_asset_id[a.id] = {
            "asset_id": a.id,
            "user_id": a.user_id,
            "core_id": a.core_id,
            "label_source": label_source,
            "expected": {
                "type": expected_type,
                "title": expected_title,
                "year": expected_year,
                "season": expected_season,
                "episode": expected_episode,
            },
        }

    return keep_assets, labels_by_asset_id


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sql",
        dest="sql_path",
        default="/home/meal/mediacmn/mediacmn_backup.sql",
    )
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parent / "data"),
    )
    args = parser.parse_args()

    sql_path = Path(args.sql_path)
    out_dir = Path(args.out_dir)
    out_paths = out_dir / "media_parser_dataset_paths.jsonl"
    out_labels = out_dir / "media_parser_dataset_labels.jsonl"

    media_core_map = _load_media_core_map(sql_path)
    episode_ext_map = _load_episode_ext_map(sql_path)
    season_ext_map = _load_season_ext_map(sql_path)

    version_to_core = _load_media_version_core_map(sql_path)

    all_assets = list(_iter_labelable_file_assets(sql_path, version_to_core))
    db_assets: List[FileAssetRow] = []
    other_assets: List[FileAssetRow] = []
    for a in all_assets:
        if a.core_id is not None and (a.user_id, a.core_id) in media_core_map:
            db_assets.append(a)
        else:
            other_assets.append(a)

    rng = random.Random(args.seed)
    rng.shuffle(db_assets)
    rng.shuffle(other_assets)

    selected: List[FileAssetRow] = []
    selected.extend(db_assets)
    if len(selected) < args.count:
        selected.extend(other_assets[: args.count - len(selected)])
    selected = selected[: args.count]
    rng.shuffle(selected)

    labelable, labels_by_asset_id = _build_labels(selected, media_core_map, episode_ext_map, season_ext_map)

    labelable = labelable[: args.count]
    labels_by_asset_id = {a.id: labels_by_asset_id[a.id] for a in labelable}

    _write_jsonl(
        out_paths,
        (
            {
                "asset_id": a.id,
                "user_id": a.user_id,
                "core_id": a.core_id,
                "full_path": a.full_path,
            }
            for a in labelable
        ),
    )

    _write_jsonl(out_labels, (labels_by_asset_id[a.id] for a in labelable))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
