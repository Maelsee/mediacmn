import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from utils.media_parser import MediaParser


@dataclass(frozen=True)
class EvalItem:
    asset_id: int
    full_path: str
    expected: Dict[str, Any]
    label_source: str


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _normalize_title_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _normalize_title_candidates(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for v in value:
            nv = _normalize_title_text(v)
            if nv:
                out.append(nv)
        return out
    nv = _normalize_title_text(value)
    return [nv] if nv else []


def _normalize_for_match(value: str) -> str:
    s = value.lower().strip()
    s = "".join(ch for ch in s if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))
    return s


def _title_matches(expected_title: str, got_title: str) -> bool:
    a = _normalize_for_match(expected_title)
    b = _normalize_for_match(got_title)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 2 and a in b:
        return True
    if len(b) >= 2 and b in a:
        return True
    return False


def _compare_one(expected: Dict[str, Any], got: Dict[str, Any]) -> Tuple[bool, Dict[str, bool]]:
    field_ok: Dict[str, bool] = {}

    exp_type = expected.get("type")
    if exp_type is not None:
        field_ok["type"] = got.get("type") == exp_type

    exp_titles = _normalize_title_candidates(expected.get("title"))
    got_title = _normalize_title_text(got.get("title"))
    if exp_titles and got_title:
        field_ok["title"] = any(_title_matches(et, got_title) for et in exp_titles)

    exp_year = expected.get("year")
    if exp_year is not None:
        field_ok["year"] = got.get("year") == exp_year

    exp_season = expected.get("season")
    if exp_season is not None:
        field_ok["season"] = got.get("season") == exp_season

    exp_episode = expected.get("episode")
    if exp_episode is not None:
        field_ok["episode"] = got.get("episode") == exp_episode

    if not field_ok:
        return False, {}

    overall = all(field_ok.values())
    return overall, field_ok


def evaluate(items: Iterable[EvalItem], strict_episode_from_path: bool) -> Dict[str, Any]:
    items_list = list(items)
    parser = MediaParser()
    totals = Counter()
    correct = Counter()
    evaluated_items = 0
    overall_ok = 0
    per_type_counts = Counter()
    per_type_ok = Counter()
    per_source_counts = Counter()
    per_source_ok = Counter()
    failures_by_reason = Counter()
    sample_failures: List[Dict[str, Any]] = []

    for it in items_list:
        strict_episode = strict_episode_from_path and parser.should_force_episode(it.full_path)
        got = parser.parse(it.full_path, strict_episode=strict_episode)

        ok, field_ok = _compare_one(it.expected, got)
        if not field_ok:
            continue

        evaluated_items += 1
        totals.update(field_ok.keys())
        correct.update([k for k, v in field_ok.items() if v])
        if ok:
            overall_ok += 1

        exp_type = it.expected.get("type")
        if exp_type:
            per_type_counts[exp_type] += 1
            if ok:
                per_type_ok[exp_type] += 1

        per_source_counts[it.label_source] += 1
        if ok:
            per_source_ok[it.label_source] += 1

        if not ok:
            reasons = [k for k, v in field_ok.items() if not v]
            failures_by_reason.update(reasons)
            if len(sample_failures) < 200:
                sample_failures.append(
                    {
                        "asset_id": it.asset_id,
                        "full_path": it.full_path,
                        "label_source": it.label_source,
                        "expected": it.expected,
                        "got": got,
                        "failed_fields": reasons,
                    }
                )

    total_items = len(items_list)
    report: Dict[str, Any] = {
        "total": total_items,
        "evaluated": evaluated_items,
        "overall_accuracy": (overall_ok / evaluated_items) if evaluated_items else 0.0,
        "field_accuracy": {k: (correct[k] / totals[k]) if totals[k] else 0.0 for k in totals},
        "per_type": {
            t: {
                "count": per_type_counts[t],
                "overall_accuracy": (per_type_ok[t] / per_type_counts[t]) if per_type_counts[t] else 0.0,
            }
            for t in per_type_counts
        },
        "per_label_source": {
            s: {
                "count": per_source_counts[s],
                "overall_accuracy": (per_source_ok[s] / per_source_counts[s]) if per_source_counts[s] else 0.0,
            }
            for s in per_source_counts
        },
        "failures_by_field": dict(failures_by_reason),
        "sample_failures": sample_failures,
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parent / "data"),
    )
    ap.add_argument(
        "--strict-episode-from-path",
        action="store_true",
        default=True,
    )
    ap.add_argument("--out-report", default=None)
    ap.add_argument("--out-results", default=None)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    paths_file = data_dir / "media_parser_dataset_paths.jsonl"
    labels_file = data_dir / "media_parser_dataset_labels.jsonl"

    paths = {r["asset_id"]: r for r in _read_jsonl(paths_file)}
    labels = {r["asset_id"]: r for r in _read_jsonl(labels_file)}

    items: List[EvalItem] = []
    for asset_id, p in paths.items():
        lab = labels.get(asset_id)
        if not lab:
            continue
        
        expected = lab.get("expected")
        if expected is None:
            # Fallback for flat structure
            expected = {k: v for k, v in lab.items() if k not in ("asset_id", "label_source")}
            
        items.append(
            EvalItem(
                asset_id=asset_id,
                full_path=p["full_path"],
                expected=expected,
                label_source=lab.get("label_source", "manual"),
            )
        )

    report = evaluate(items, strict_episode_from_path=args.strict_episode_from_path)

    out_report = Path(args.out_report) if args.out_report else (data_dir / "media_parser_eval_report.json")
    out_results = Path(args.out_results) if args.out_results else (data_dir / "media_parser_eval_results.jsonl")
    out_report.parent.mkdir(parents=True, exist_ok=True)

    with out_report.open("w", encoding="utf-8") as f:
        def _default(o: Any):
            try:
                return str(o)
            except Exception:
                return repr(o)

        json.dump(report, f, ensure_ascii=False, indent=2, default=_default)

    with out_results.open("w", encoding="utf-8") as f:
        for row in report.get("sample_failures", []):
            f.write(json.dumps(row, ensure_ascii=False, default=_default))
            f.write("\n")

    print(json.dumps({"report": str(out_report), "results": str(out_results), "total": report["total"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
