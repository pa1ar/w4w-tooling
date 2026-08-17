#!/usr/bin/env python3
"""Prepare the active 124-way conservative pathway publication ledger.

This command performs read-only OSM checks. It copies the verified first batch
and exposes only ranks 101-124 as the next dashboard review batch.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare_upload_batches import fetch_live_way_state


PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "pending_upload" / "osm-broad-2026-08"
DEFAULT_OUTPUT = PROJECT_ROOT / "pending_upload" / "osm-publication-threshold-2026-08"
PATHWAY_TYPES = {"cycleway", "footway", "path", "pedestrian"}
FIRST_UNPUBLISHED_RANK = 101
FINAL_PUBLICATION_RANK = 124


def load_source_items(source_dir: Path) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    manifests: dict[int, dict[str, Any]] = {}
    for path in sorted(source_dir.glob("batch-*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifests[int(manifest["batch"])] = manifest
        items.extend(manifest["items"])
    ranks = [int(item["rank"]) for item in items]
    way_ids = [int(item["way_id"]) for item in items]
    if len(ranks) != len(set(ranks)) or len(way_ids) != len(set(way_ids)):
        raise ValueError("source manifests contain duplicate ranks or ways")
    return sorted(items, key=lambda item: int(item["rank"])), manifests


def select_active_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    published = [deepcopy(item) for item in items if int(item["rank"]) < FIRST_UNPUBLISHED_RANK]
    next_items = [
        deepcopy(item)
        for item in items
        if FIRST_UNPUBLISHED_RANK <= int(item["rank"]) <= FINAL_PUBLICATION_RANK
    ]
    if len(published) != 100 or not all(item.get("status") == "pushed" for item in published):
        raise ValueError("expected ranks 1-100 to be the verified pushed batch")
    if [int(item["rank"]) for item in next_items] != list(
        range(FIRST_UNPUBLISHED_RANK, FINAL_PUBLICATION_RANK + 1)
    ):
        raise ValueError("expected a complete rank 101-124 candidate range")
    for item in next_items:
        if item.get("confidence_tier") != "high_confidence":
            raise ValueError(f"rank {item['rank']} is outside the stronger evidence tier")
        if item.get("highway") not in PATHWAY_TYPES:
            raise ValueError(f"rank {item['rank']} is not a pedestrian or cycling pathway")
        if float(item.get("coverage_pct", 0)) < 70 or int(item.get("rides", 0)) < 2:
            raise ValueError(f"rank {item['rank']} does not meet the evidence threshold")
    return published, next_items


def refresh_unpublished_items(
    items: list[dict[str, Any]], live: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    for item in items:
        way_id = int(item["way_id"])
        state = live.get(way_id)
        if state is None:
            raise ValueError(f"OSM way {way_id} is missing")
        tags = state.get("tags") or {}
        if tags.get("smoothness") is not None:
            raise ValueError(f"OSM way {way_id} already has smoothness={tags['smoothness']}")
        refreshed.append(
            {
                **item,
                "observed_version": int(state["version"]),
                "observed_changeset_id": state.get("changeset"),
                "observed_timestamp": state.get("timestamp"),
                "observed_smoothness": None,
                "observed_tags": tags,
                "status": "needs_pipeline_validation",
                "upload_allowed": False,
                "uploaded_at": None,
                "changeset_id": None,
                "changeset_url": None,
            }
        )
    return refreshed


def load_geometries(source_dir: Path) -> dict[int, dict[str, Any]]:
    features: dict[int, dict[str, Any]] = {}
    for path in sorted(source_dir.glob("batch-*.geojson")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            features[int(feature["properties"]["way_id"])] = feature
    return features


def render_ledger(batches: list[dict[str, Any]]) -> str:
    lines = [
        "# W4W conservative pathway publication ledger",
        "",
        "The active scope stops at rank 124. Rows marked `pushed` include their OSM changeset.",
        "",
        "| Batch | Review date | Rank | Tier | OSM way | Highway | Proposal | Rides | Coverage | Version | Status | Changeset |",
        "|---:|:---|---:|:---|:---|:---|:---|---:|---:|---:|:---|:---|",
    ]
    for manifest in batches:
        for item in manifest["items"]:
            changeset_id = item.get("changeset_id")
            changeset_url = item.get("changeset_url")
            changeset = (
                f"[{changeset_id}]({changeset_url})" if changeset_id and changeset_url else "-"
            )
            after_version = item.get("after_version")
            version = (
                f"{item['observed_version']} -> {after_version}"
                if after_version is not None
                else str(item["observed_version"])
            )
            lines.append(
                f"| {manifest['batch']} | {manifest['planned_review_date']} | {item['rank']} | "
                f"{item['confidence_tier']} | [{item['way_id']}](https://www.openstreetmap.org/way/{item['way_id']}) | "
                f"{item['highway']} | `{item['proposed_value']}` | {item['rides']} | "
                f"{float(item['coverage_pct']):.1f}% | {version} | {item['status']} | {changeset} |"
            )
    return "\n".join(lines) + "\n"


def write_active_ledger(
    output_dir: Path,
    source_manifests: dict[int, dict[str, Any]],
    published: list[dict[str, Any]],
    next_items: list[dict[str, Any]],
    geometries: dict[int, dict[str, Any]],
    generated_at: str,
    review_date: str,
) -> None:
    if output_dir.exists():
        raise FileExistsError(f"active ledger already exists: {output_dir}")
    temporary = output_dir.with_name(f".{output_dir.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    temporary.mkdir(parents=True)

    batch_one = deepcopy(source_manifests[1])
    batch_one["items"] = published
    batch_one["pushed_count"] = 100
    batch_one["remaining_count"] = 0

    batch_two = deepcopy(source_manifests[2])
    batch_two.update(
        {
            "batch": 2,
            "planned_review_date": review_date,
            "generated_at": generated_at,
            "status": "ready_for_manual_review",
            "approval_status": "manual_review_required",
            "upload_allowed": False,
            "items": next_items,
            "pushed_count": 0,
            "remaining_count": len(next_items),
        }
    )
    batches = [batch_one, batch_two]
    for manifest in batches:
        date = manifest["planned_review_date"]
        batch = int(manifest["batch"])
        (temporary / f"batch-{batch:02d}-{date}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        selected_ids = {int(item["way_id"]) for item in manifest["items"]}
        selected_features = [geometries[way_id] for way_id in selected_ids if way_id in geometries]
        if len(selected_features) != len(selected_ids):
            missing = sorted(selected_ids - geometries.keys())
            raise ValueError(f"missing review geometry for ways: {missing}")
        (temporary / f"batch-{batch:02d}-{date}.geojson").write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": selected_features},
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

    summary = {
        "generated_at": generated_at,
        "status": "active_publication_threshold",
        "threshold": {
            "final_rank": FINAL_PUBLICATION_RANK,
            "highway_types": sorted(PATHWAY_TYPES),
            "minimum_coverage_pct": 70,
            "minimum_distinct_rides": 2,
        },
        "active_candidates": 124,
        "pushed_candidates": 100,
        "remaining_candidates": 24,
        "deferred_broad_candidates": 2274,
        "schedule": [
            {"batch": 1, "planned_review_date": batch_one["planned_review_date"], "count": 100},
            {"batch": 2, "planned_review_date": review_date, "count": 24},
        ],
    }
    (temporary / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (temporary / "upload_ledger.md").write_text(render_ledger(batches), encoding="utf-8")
    temporary.replace(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare the active 24-way follow-up batch without writing to OSM"
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-date", default=datetime.now().date().isoformat())
    args = parser.parse_args()

    items, manifests = load_source_items(args.source_dir)
    published, next_items = select_active_items(items)
    live = fetch_live_way_state([int(item["way_id"]) for item in next_items])
    refreshed = refresh_unpublished_items(next_items, live)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_active_ledger(
        args.output_dir,
        manifests,
        published,
        refreshed,
        load_geometries(args.source_dir),
        generated_at,
        args.review_date,
    )
    print(f"Prepared {len(refreshed)} reviewed candidates in {args.output_dir}")
    print("No OSM writes were made.")


if __name__ == "__main__":
    main()
