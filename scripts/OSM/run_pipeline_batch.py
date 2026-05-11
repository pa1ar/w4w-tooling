#!/usr/bin/env python3
"""
run the smoothness workflow pipeline for each ride in selected_rides.json.
idempotent: skips rides whose per-ride artifacts already exist.
writes output/batch_manifest.json summarizing per-ride state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
WORKFLOW = SCRIPT_DIR / "OSM_smoothness_workflow.py"


def artifacts_for(ride_id: str) -> dict:
    geojson_dir = OUTPUT_DIR / "proposals_geojson"
    return {
        "csv": OUTPUT_DIR / f"smoothness_proposals_{ride_id}.csv",
        "html": OUTPUT_DIR / f"smoothness_proposals_{ride_id}.html",
        "raw_html": OUTPUT_DIR / f"raw_map_{ride_id}.html",
        "ride_geojson": geojson_dir / f"{ride_id}-*.geojson",
        "ways_geojson_dir": geojson_dir,
    }


def all_artifacts_present(ride_id: str) -> bool:
    a = artifacts_for(ride_id)
    return a["csv"].exists() and a["html"].exists()


def count_csv_rows(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {"rows": 0, "proposed": 0, "new": 0, "override": 0}
    import csv
    rows = 0
    proposed = 0
    new_tag = 0
    override = 0
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows += 1
            value = (row.get("proposed_value") or "").strip()
            if not value:
                continue
            proposed += 1
            if (row.get("existing_smoothness") or "").strip():
                override += 1
            else:
                new_tag += 1
    return {"rows": rows, "proposed": proposed, "new": new_tag, "override": override}


def run_ride(ride: dict, force: bool) -> dict:
    ride_id = ride["ride_id"]
    path_id = ride.get("path_id")
    input_file = PROJECT_ROOT / ride["file"]

    csv_path = OUTPUT_DIR / f"smoothness_proposals_{ride_id}.csv"
    html_path = OUTPUT_DIR / f"smoothness_proposals_{ride_id}.html"
    raw_html = OUTPUT_DIR / f"raw_map_{ride_id}.html"

    if not force and all_artifacts_present(ride_id):
        stats = count_csv_rows(csv_path)
        return {
            "ride_id": ride_id,
            "path_id": path_id,
            "status": "skipped-cached",
            "csv": str(csv_path.relative_to(PROJECT_ROOT)),
            "html": str(html_path.relative_to(PROJECT_ROOT)),
            "raw_html": str(raw_html.relative_to(PROJECT_ROOT)) if raw_html.exists() else None,
            **stats,
        }

    cmd = [
        sys.executable,
        str(WORKFLOW),
        "--input", str(input_file),
        "--out-csv", str(csv_path),
        "--out-map", str(html_path),
        "--raw-map-html", str(raw_html),
        "--no-plots",
    ]
    if path_id:
        cmd += ["--path-id", str(path_id)]

    print(f"[{ride_id}] running workflow...")
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        return {"ride_id": ride_id, "path_id": path_id, "status": "timeout",
                "duration_s": 1200, "csv": None, "html": None,
                "rows": 0, "proposed": 0, "new": 0, "override": 0}

    duration_s = round(time.monotonic() - start, 1)

    if result.returncode != 0:
        err_tail = (result.stderr or "").splitlines()[-5:]
        return {
            "ride_id": ride_id,
            "path_id": path_id,
            "status": "failed",
            "returncode": result.returncode,
            "stderr_tail": err_tail,
            "duration_s": duration_s,
            "csv": None,
            "html": None,
            "rows": 0, "proposed": 0, "new": 0, "override": 0,
        }

    stats = count_csv_rows(csv_path)
    return {
        "ride_id": ride_id,
        "path_id": path_id,
        "status": "ok",
        "duration_s": duration_s,
        "csv": str(csv_path.relative_to(PROJECT_ROOT)),
        "html": str(html_path.relative_to(PROJECT_ROOT)),
        "raw_html": str(raw_html.relative_to(PROJECT_ROOT)) if raw_html.exists() else None,
        **stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="run smoothness pipeline for all selected rides")
    parser.add_argument("--selected", default=str(OUTPUT_DIR / "selected_rides.json"),
                        help="input selected-rides manifest (from select_rides.py)")
    parser.add_argument("--out", default=str(OUTPUT_DIR / "batch_manifest.json"),
                        help="output batch manifest path")
    parser.add_argument("--force", action="store_true",
                        help="re-run even if per-ride artifacts already exist")
    args = parser.parse_args()

    selected_path = Path(args.selected)
    if not selected_path.exists():
        print(f"missing {selected_path}. run select_rides.py first.", file=sys.stderr)
        sys.exit(1)

    with open(selected_path) as f:
        sel = json.load(f)

    rides = sel.get("selected") or []
    if not rides:
        print("no selected rides in manifest.", file=sys.stderr)
        sys.exit(1)

    print(f"running pipeline for {len(rides)} rides (force={args.force})...")
    results = []
    for ride in rides:
        res = run_ride(ride, force=args.force)
        results.append({**ride, **res})
        print(f"  [{res['ride_id']}] {res['status']} (proposed={res.get('proposed', 0)})")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bbox_name": sel.get("bbox_name"),
        "bbox": sel.get("bbox"),
        "rides": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    ok = sum(1 for r in results if r["status"] in ("ok", "skipped-cached"))
    failed = sum(1 for r in results if r["status"] in ("failed", "timeout"))
    print(f"\nwrote {out_path}")
    print(f"  ok: {ok}  failed: {failed}")


if __name__ == "__main__":
    main()
