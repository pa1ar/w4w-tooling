#!/usr/bin/env python3
"""
select telemetry rides that intersect a geographic bounding box.
writes output/selected_rides.json with top-N rides ranked by in-bbox point count.

filename convention: telemetry_json/<ride_id>-<path_id>.json
each record has gpsPos.gpsLat / gpsPos.gpsLon (wgs84) when gpsFix is true.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from constants import TALLINN_BBOX, TALLINN_CENTER_BBOX, bbox_contains

PROJECT_ROOT = SCRIPT_DIR.parent.parent
TELEMETRY_DIR = PROJECT_ROOT / "telemetry_json"
OUTPUT_DIR = PROJECT_ROOT / "output"

BBOX_PRESETS = {
    "tallinn-center": TALLINN_CENTER_BBOX,
    "tallinn-full": TALLINN_BBOX,
}


def parse_filename(path: Path) -> tuple[str, str]:
    """return (ride_id, path_id) from <ride_id>-<path_id>.json filename."""
    stem = path.stem
    if "-" in stem:
        ride_id, _, path_id = stem.partition("-")
        return ride_id, path_id
    return stem, ""


def scan_ride(path: Path, bbox) -> dict | None:
    """count gps points inside bbox. returns summary dict or none on parse failure."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"skip {path.name}: {exc}", file=sys.stderr)
        return None

    records = data.get("rideData") or []
    total = 0
    in_bbox = 0
    first_gps = None
    last_gps = None
    for rec in records:
        gps = rec.get("gpsPos") or {}
        if not gps.get("gpsFix"):
            continue
        lat = gps.get("gpsLat")
        lon = gps.get("gpsLon")
        if lat is None or lon is None:
            continue
        total += 1
        if first_gps is None:
            first_gps = [lat, lon]
        last_gps = [lat, lon]
        if bbox_contains(bbox, lat, lon):
            in_bbox += 1

    ride_id, path_id = parse_filename(path)
    return {
        "ride_id": ride_id,
        "path_id": path_id,
        "file": str(path.relative_to(PROJECT_ROOT)),
        "total_gps_points": total,
        "points_in_bbox": in_bbox,
        "first_gps": first_gps,
        "last_gps": last_gps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="select telemetry rides by bbox overlap")
    parser.add_argument("--bbox", default="tallinn-center",
                        choices=list(BBOX_PRESETS.keys()),
                        help="named bbox preset (default: tallinn-center)")
    parser.add_argument("--top-n", type=int, default=10,
                        help="number of rides to pick (default: 10)")
    parser.add_argument("--min-points", type=int, default=50,
                        help="drop rides with fewer in-bbox gps points (default: 50)")
    parser.add_argument("--out", default=str(OUTPUT_DIR / "selected_rides.json"),
                        help="output manifest path")
    args = parser.parse_args()

    bbox = BBOX_PRESETS[args.bbox]
    files = sorted(TELEMETRY_DIR.glob("*.json"))
    if not files:
        print(f"no telemetry files found in {TELEMETRY_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"scanning {len(files)} ride files against bbox {args.bbox}={bbox}...")
    all_summaries = []
    for i, path in enumerate(files, 1):
        summary = scan_ride(path, bbox)
        if summary is None:
            continue
        all_summaries.append(summary)
        if i % 20 == 0 or i == len(files):
            print(f"  scanned {i}/{len(files)}")

    qualified = [s for s in all_summaries if s["points_in_bbox"] >= args.min_points]
    qualified.sort(key=lambda s: s["points_in_bbox"], reverse=True)
    selected = qualified[: args.top_n]

    manifest = {
        "bbox_name": args.bbox,
        "bbox": list(bbox),
        "min_points": args.min_points,
        "top_n": args.top_n,
        "candidates_scanned": len(all_summaries),
        "qualified": len(qualified),
        "selected": selected,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nwrote {out_path}")
    print(f"  scanned: {len(all_summaries)}  qualified: {len(qualified)}  selected: {len(selected)}")
    for s in selected:
        print(f"  - {s['ride_id']} ({s['path_id']}): {s['points_in_bbox']} in-bbox / {s['total_gps_points']} total")


if __name__ == "__main__":
    main()
