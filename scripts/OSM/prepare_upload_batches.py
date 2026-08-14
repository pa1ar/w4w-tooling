#!/usr/bin/env python3
"""Prepare broad OSM smoothness candidates as prioritized local review batches.

This command is read-only with respect to OSM. Generated manifests are explicitly
blocked from upload until ride-level validation and community-process gates pass.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "output" / "tallinn-coverage" / "osm-way-estimates.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "pending_upload" / "osm-broad-2026-08"
DEFAULT_DATES = (
    "2026-08-14",
    "2026-08-17",
    "2026-08-18",
    "2026-08-19",
    "2026-08-20",
    "2026-08-21",
    "2026-08-24",
    "2026-08-25",
)
PATHWAY_TYPES = {"cycleway", "footway", "path", "pedestrian"}
UPLOAD_GATES = (
    "candidate_level_pipeline_validation",
    "source_license_confirmation",
    "osm_community_process_complete",
    "regional_changeset_uploader_and_metadata_ready",
    "fresh_live_create_only_check",
)
OPERATOR_APPROVAL = {
    "approved": True,
    "approved_by": "Pavel",
    "approved_at": "2026-08-14",
    "scope": "all eligible ways from the 2,399-row broad gap-only source pool",
    "automatic_processing": True,
    "external_gates_still_required": True,
}
USER_AGENT = "W4W-Tooling/0.1 batch-preflight (read-only OSM state refresh)"


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _integer(value: Any) -> int:
    return int(float(value or 0))


def _number(value: Any) -> float:
    return float(value or 0)


def load_candidates(path: Path, scope: str = "potential") -> list[dict[str, Any]]:
    if scope not in {"potential", "conservative"}:
        raise ValueError(f"unsupported candidate scope: {scope}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not _truthy(row.get(scope)):
            continue
        if (row.get("existing_smoothness") or "").strip():
            continue
        proposed_value = (row.get("proposed_value") or "").strip()
        if proposed_value not in {"intermediate", "bad"}:
            continue
        candidates.append(
            {
                "way_id": _integer(row.get("way_id")),
                "highway": (row.get("highway") or "unknown").strip(),
                "proposed_value": proposed_value,
                "confidence_tier": (
                    "high_confidence" if _truthy(row.get("conservative")) else "broad"
                ),
                "source_snapshot_smoothness_absent": not bool(
                    (row.get("existing_smoothness") or "").strip()
                ),
                "coverage_pct": _number(row.get("coverage_pct")),
                "rides": _integer(row.get("rides")),
                "dominant_class": (row.get("dominant_class") or "").strip(),
                "dominant_share_pct": _number(row.get("dominant_share_pct")),
                "bad_run_m": _number(row.get("bad_run_m")),
                "mean_match_distance_m": _number(row.get("mean_match_distance_m")),
            }
        )
    return candidates


def _chunks(items: list[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def fetch_live_way_state(
    way_ids: list[int], base_url: str = "https://api.openstreetmap.org", batch_size: int = 50
) -> dict[int, dict[str, Any]]:
    """Fetch public, current way metadata without using the OAuth write token."""
    live: dict[int, dict[str, Any]] = {}
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    for batch in _chunks(way_ids, batch_size):
        response = session.get(
            f"{base_url.rstrip('/')}/api/0.6/ways.json",
            params={"ways": ",".join(str(way_id) for way_id in batch)},
            timeout=30,
        )
        response.raise_for_status()
        for element in response.json().get("elements", []):
            if element.get("type") != "way":
                continue
            live[int(element["id"])] = {
                "id": int(element["id"]),
                "version": int(element["version"]),
                "changeset": int(element["changeset"]),
                "timestamp": element.get("timestamp"),
                "tags": element.get("tags") or {},
            }
    return live


def load_live_way_state(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    elements = payload.get("elements", payload.get("ways", payload)) if isinstance(payload, dict) else payload
    live: dict[int, dict[str, Any]] = {}
    for element in elements:
        way_id = int(element.get("id", element.get("way_id")))
        live[way_id] = {
            "id": way_id,
            "version": int(element.get("version", 0)),
            "changeset": element.get("changeset", element.get("changeset_id")),
            "timestamp": element.get("timestamp"),
            "tags": element.get("tags") or {},
        }
    return live


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if candidate["confidence_tier"] == "high_confidence" else 1,
        0 if candidate["highway"] in PATHWAY_TYPES else 1,
        0 if candidate["proposed_value"] == "intermediate" else 1,
        -candidate["rides"],
        -candidate["coverage_pct"],
        -candidate["dominant_share_pct"],
        candidate["mean_match_distance_m"],
        candidate["way_id"],
    )


def select_live_gaps(
    candidates: list[dict[str, Any]], live: dict[int, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[int]]:
    eligible: list[dict[str, Any]] = []
    already_tagged: list[dict[str, Any]] = []
    missing: list[int] = []
    for candidate in candidates:
        state = live.get(candidate["way_id"])
        if state is None:
            missing.append(candidate["way_id"])
            continue
        smoothness = state["tags"].get("smoothness")
        if smoothness is not None:
            already_tagged.append(
                {
                    "way_id": candidate["way_id"],
                    "smoothness": smoothness,
                    "version": state["version"],
                }
            )
            continue
        eligible.append(
            {
                **candidate,
                "observed_version": state["version"],
                "observed_changeset_id": state["changeset"],
                "observed_timestamp": state["timestamp"],
                "observed_smoothness": None,
                "status": "needs_pipeline_validation",
                "upload_allowed": False,
                "operator_automation_approved": True,
                "uploaded_at": None,
                "changeset_id": None,
                "changeset_url": None,
            }
        )
    eligible.sort(key=candidate_sort_key)
    return eligible, already_tagged, missing


def split_schedule(
    candidates: list[dict[str, Any]], dates: tuple[str, ...], first_batch_size: int
) -> list[tuple[str, list[dict[str, Any]]]]:
    if not dates:
        raise ValueError("at least one review date is required")
    first_size = min(max(first_batch_size, 0), len(candidates))
    sizes = [first_size]
    remaining = len(candidates) - first_size
    remaining_slots = len(dates) - 1
    if remaining_slots:
        quotient, extra = divmod(remaining, remaining_slots)
        sizes.extend(quotient + (1 if index < extra else 0) for index in range(remaining_slots))
    elif remaining:
        sizes[0] += remaining

    result: list[tuple[str, list[dict[str, Any]]]] = []
    cursor = 0
    for date, size in zip(dates, sizes, strict=True):
        result.append((date, candidates[cursor : cursor + size]))
        cursor += size
    return result


def write_outputs(
    output_dir: Path,
    source_csv: Path,
    observed_at: str,
    source_scope: str,
    source_count: int,
    source_high_confidence_count: int,
    batches: list[tuple[str, list[dict[str, Any]]]],
    already_tagged: list[dict[str, Any]],
    missing: list[int],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scheduled = sum(len(items) for _, items in batches)
    summary = {
        "generated_at": observed_at,
        "source_csv": str(source_csv),
        "source_scope": source_scope,
        "source_candidates": source_count,
        "source_high_confidence_candidates": source_high_confidence_count,
        "live_untagged_preflight_candidates": scheduled,
        "live_high_confidence_candidates": sum(
            item["confidence_tier"] == "high_confidence"
            for _, items in batches
            for item in items
        ),
        "live_broad_candidates": sum(
            item["confidence_tier"] == "broad"
            for _, items in batches
            for item in items
        ),
        "excluded_existing_smoothness": already_tagged,
        "missing_live_way_ids": missing,
        "status": "preflight_only",
        "upload_allowed": False,
        "operator_automation_approval": OPERATOR_APPROVAL,
        "required_gates": list(UPLOAD_GATES),
        "proposal_counts": dict(
            Counter(item["proposed_value"] for _, items in batches for item in items)
        ),
        "pathway_type_candidates": sum(
            item["highway"] in PATHWAY_TYPES for _, items in batches for item in items
        ),
        "schedule": [
            {"batch": index, "planned_review_date": date, "count": len(items)}
            for index, (date, items) in enumerate(batches, 1)
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    ledger_lines = [
        "# W4W broad OSM preflight ledger",
        "",
        f"Generated: `{observed_at}`",
        "",
        "Pavel approved automatic processing of the full eligible pool. `upload_allowed=false` until every external gate passes.",
        "",
        "| Batch | Review date | Rank | Tier | OSM way | Highway | Proposal | Rides | Coverage | Version | Status | Changeset |",
        "|---:|:---|---:|:---|:---|:---|:---|---:|---:|---:|:---|:---|",
    ]
    rank = 0
    for batch_index, (date, items) in enumerate(batches, 1):
        manifest_items: list[dict[str, Any]] = []
        for item in items:
            rank += 1
            manifest_item = {"rank": rank, **item}
            manifest_items.append(manifest_item)
            ledger_lines.append(
                f"| {batch_index} | {date} | {rank} | {item['confidence_tier']} | "
                f"[{item['way_id']}](https://www.openstreetmap.org/way/{item['way_id']}) | "
                f"{item['highway']} | `{item['proposed_value']}` | {item['rides']} | "
                f"{item['coverage_pct']:.1f}% | {item['observed_version']} | {item['status']} | - |"
            )
        manifest = {
            "batch": batch_index,
            "planned_review_date": date,
            "generated_at": observed_at,
            "status": "preflight_only",
            "approval_status": "operator_approved_external_gates_pending",
            "operator_automation_approval": OPERATOR_APPROVAL,
            "upload_allowed": False,
            "required_gates": list(UPLOAD_GATES),
            "items": manifest_items,
        }
        (output_dir / f"batch-{batch_index:02d}-{date}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    (output_dir / "upload_ledger.md").write_text(
        "\n".join(ledger_lines) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare read-only prioritized OSM review batches"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--live-state-file", type=Path)
    parser.add_argument("--osm-base-url", default="https://api.openstreetmap.org")
    parser.add_argument("--first-batch-size", type=int, default=100)
    parser.add_argument("--dates", nargs="+", default=list(DEFAULT_DATES))
    parser.add_argument(
        "--scope",
        choices=("potential", "conservative"),
        default="potential",
        help="Source candidate scope; potential is the 2,399-row broad pool",
    )
    args = parser.parse_args()

    candidates = load_candidates(args.input, args.scope)
    live = (
        load_live_way_state(args.live_state_file)
        if args.live_state_file
        else fetch_live_way_state([row["way_id"] for row in candidates], args.osm_base_url)
    )
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    eligible, already_tagged, missing = select_live_gaps(candidates, live)
    batches = split_schedule(eligible, tuple(args.dates), args.first_batch_size)
    summary = write_outputs(
        args.output_dir,
        args.input,
        observed_at,
        args.scope,
        len(candidates),
        sum(row["confidence_tier"] == "high_confidence" for row in candidates),
        batches,
        already_tagged,
        missing,
    )
    print(json.dumps(summary, indent=2))
    print(f"Local ledger: {args.output_dir / 'upload_ledger.md'}")
    print("No OSM writes were made. All manifests remain preflight-only.")


if __name__ == "__main__":
    main()
