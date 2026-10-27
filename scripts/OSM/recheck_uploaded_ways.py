#!/usr/bin/env python3
"""Recheck uploaded OSM smoothness tags with stricter ride evidence.

Reruns the Tallinn way-evidence match for every pushed way in the upload
ledgers, with two fixes over the August coverage analysis:

- rides are identified by telemetry file hash, so a duplicated file counts once
- stationary sections (parked scooter) are dropped, and a ride only counts for
  a way when its own moving evidence covers enough of that way

Read-only: writes a local CSV report, never touches OSM.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from shapely import STRtree
from shapely.geometry import LineString
from shapely.ops import transform, unary_union

PROJECT_ROOT = Path(__file__).parent.parent.parent
COVERAGE_DIR = PROJECT_ROOT / "output" / "tallinn-coverage"
PENDING = PROJECT_ROOT / "pending_upload"

MATCH_DISTANCE_M = 8
BUFFER_M = 8
MIN_MOVING_M_PER_POINT = 0.3  # sections are resampled to ~1 m per point; far below that means no movement
MIN_RIDE_COVERAGE = 0.30
MIN_WAY_COVERAGE = 0.70
MIN_DISTINCT_RIDES = 2


def load_analyze(path: Path):
    spec = importlib.util.spec_from_file_location("tallinn_analyze", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pushed_ways(pending: Path) -> dict[int, dict]:
    """Latest pushed value per way across all ledgers, minus withdrawn ways."""
    row = re.compile(r"way/(\d+)\)\s*\|\s*(\w+)\s*\|\s*`(\w+)`\s*\|\s*(\d+)\s*\|\s*([\d.]+)%.*\|\s*pushed\s*\|")
    ways: dict[int, dict] = {}
    withdrawn: set[int] = set()
    for ledger in sorted(pending.glob("*/upload_ledger.md")):
        text = ledger.read_text(encoding="utf-8")
        for match in row.finditer(text):
            way_id = int(match.group(1))
            ways[way_id] = {
                "highway": match.group(2),
                "uploaded_value": match.group(3),
                "ledger_rides": int(match.group(4)),
                "ledger_coverage_pct": float(match.group(5)),
            }
        for section in re.findall(r"## Withdrawn[^\n]*\n(.*?)(?=\n## |\Z)", text, re.S):
            withdrawn.update(int(w) for w in re.findall(r"ways? (\d{6,})", section))
            withdrawn.update(int(w) for w in re.findall(r"and (\d{6,})", section))
    return {way_id: info for way_id, info in ways.items() if way_id not in withdrawn}


def ride_keys(telemetry_dir: Path | None) -> dict[str, str]:
    if not telemetry_dir:
        return {}
    keys = {}
    for path in telemetry_dir.glob("*.json"):
        keys[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return keys


def trace_records(an, sections: dict, keys: dict[str, str]) -> tuple[list[dict], Counter]:
    records, dropped = [], Counter()
    for feature in sections["features"]:
        props = feature.get("properties") or {}
        if props.get("primary") is True or props.get("cls") not in an.CLASSES:
            continue
        line = an.line_from_feature(feature)
        if line is None:
            continue
        geom = transform(an.TO_METERS, line)
        points = max(int(props.get("point_count") or len(feature["geometry"]["coordinates"])), 2)
        source = props["source_file"]
        records.append(
            {
                "legacy_ride_id": f"{source}::{props['path_id']}",
                "ride_id": keys.get(source, source),
                "class_name": props["cls"],
                "geom_m": geom,
                "length_m": geom.length,
                "moving": geom.length / (points - 1) >= MIN_MOVING_M_PER_POINT,
            }
        )
        if not records[-1]["moving"]:
            dropped["stationary_sections"] += 1
    return records, dropped


def network(an, tallinn) -> list[dict]:
    osm = an.read_json(COVERAGE_DIR / "osm-highways.json")
    ways = []
    for element in osm.get("elements", []):
        tags = element.get("tags") or {}
        if tags.get("highway") not in an.ELIGIBLE_HIGHWAYS:
            continue
        coords = [[p["lon"], p["lat"]] for p in element.get("geometry", []) if "lon" in p]
        if len(coords) < 2:
            continue
        lines = an.explode_lines(transform(an.TO_METERS, LineString(coords)).intersection(tallinn))
        if not lines:
            continue
        geom = unary_union(lines)
        if geom.length > 0:
            ways.append({"way_id": int(element["id"]), "geom_m": geom, "length_m": geom.length})
    return ways


def evidence(an, way: dict, traces: list[dict], ride_field: str, moving_only: bool, min_ride_coverage: float = MIN_RIDE_COVERAGE) -> dict:
    traces = [t for t in traces if t["moving"] or not moving_only]
    if not traces:
        return {"coverage": 0.0, "rides": 0, "proposed": None, "ride_coverage": {}}
    geom, length = way["geom_m"], way["length_m"]
    by_ride = defaultdict(list)
    for trace in traces:
        by_ride[trace[ride_field]].append(trace)
    ride_coverage = {
        ride: geom.intersection(unary_union([t["geom_m"].buffer(BUFFER_M) for t in group])).length / length
        for ride, group in by_ride.items()
    }
    counted = {ride for ride, cov in ride_coverage.items() if cov >= min_ride_coverage} if moving_only else set(by_ride)
    used = [t for t in traces if t[ride_field] in counted]
    if not used:
        return {"coverage": 0.0, "rides": 0, "proposed": None, "ride_coverage": ride_coverage}
    coverage = min(1.0, geom.intersection(unary_union([t["geom_m"].buffer(BUFFER_M) for t in used])).length / length)
    classes = Counter()
    for trace in used:
        classes[trace["class_name"]] += trace["length_m"]
    total = sum(classes.values())
    non_bad = sum(classes[c] for c in ("excellent", "good", "intermediate")) / total if total else 0.0
    bad = [t["geom_m"].buffer(BUFFER_M) for t in used if t["class_name"] in {"bad", "very_bad"}]
    bad_run = max((p.length for p in an.explode_lines(geom.intersection(unary_union(bad)))), default=0.0) if bad else 0.0
    proposed = "bad" if bad_run >= 30 else "intermediate" if non_bad >= 0.70 else None
    return {
        "coverage": coverage,
        "rides": len(counted),
        "proposed": proposed,
        "bad_run_m": bad_run,
        "non_bad_share": non_bad,
        "ride_coverage": ride_coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sections", type=Path, required=True, help="gps_paths_colored.json used for the uploads")
    parser.add_argument("--telemetry-dir", type=Path, help="raw ride telemetry, used to hash rides")
    parser.add_argument("--analyze", type=Path, default=COVERAGE_DIR / "analyze.py")
    parser.add_argument("--min-ride-coverage", type=float, default=MIN_RIDE_COVERAGE,
                        help="share of the way a ride must cover on its own to count (default: 0.30)")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output" / "osm-upload-recheck.csv")
    args = parser.parse_args()

    an = load_analyze(args.analyze)
    uploaded = pushed_ways(PENDING)
    sections = json.loads(args.sections.read_text(encoding="utf-8"))
    traces, dropped = trace_records(an, sections, ride_keys(args.telemetry_dir))
    tallinn = unary_union([an.metric_shape(f) for f in an.read_json(COVERAGE_DIR / "districts.geojson")["features"]])
    ways = network(an, tallinn)

    tree = STRtree([w["geom_m"] for w in ways])
    nearest = tree.query_nearest([t["geom_m"] for t in traces], max_distance=MATCH_DISTANCE_M, all_matches=False)
    traces_by_way = defaultdict(list)
    for trace_index, way_index in zip(nearest[0], nearest[1]):
        traces_by_way[ways[int(way_index)]["way_id"]].append(traces[int(trace_index)])
    way_by_id = {w["way_id"]: w for w in ways}

    rows = []
    for way_id, info in sorted(uploaded.items()):
        way = way_by_id.get(way_id)
        if way is None:
            rows.append({"way_id": way_id, **info, "verdict": "not_in_snapshot"})
            continue
        legacy = evidence(an, way, traces_by_way[way_id], "legacy_ride_id", moving_only=False)
        strict = evidence(an, way, traces_by_way[way_id], "ride_id", moving_only=True, min_ride_coverage=args.min_ride_coverage)
        holds = (
            strict["coverage"] >= MIN_WAY_COVERAGE
            and strict["rides"] >= MIN_DISTINCT_RIDES
            and strict["proposed"] == info["uploaded_value"]
        )
        reasons = []
        if strict["rides"] < MIN_DISTINCT_RIDES:
            reasons.append(f"{strict['rides']} counted ride(s)")
        if strict["coverage"] < MIN_WAY_COVERAGE:
            reasons.append(f"coverage {strict['coverage']:.0%}")
        if strict["proposed"] != info["uploaded_value"]:
            reasons.append(f"now proposes {strict['proposed']}")
        rows.append(
            {
                "way_id": way_id,
                **info,
                "legacy_rides": legacy["rides"],
                "legacy_coverage_pct": round(100 * legacy["coverage"], 1),
                "legacy_proposed": legacy["proposed"],
                "strict_rides": strict["rides"],
                "strict_coverage_pct": round(100 * strict["coverage"], 1),
                "strict_proposed": strict["proposed"],
                "ride_coverage_pct": ";".join(
                    f"{ride}:{100 * cov:.0f}" for ride, cov in sorted(strict["ride_coverage"].items(), key=lambda x: -x[1])
                ),
                "verdict": "holds" if holds else "fails",
                "reason": ", ".join(reasons),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    verdicts = Counter(row["verdict"] for row in rows)
    reproduced = sum(
        1 for row in rows if row.get("legacy_rides") == row["ledger_rides"] and row.get("legacy_proposed") == row["uploaded_value"]
    )
    print(f"uploaded ways checked: {len(rows)}; stationary sections dropped: {dropped['stationary_sections']}")
    print(f"legacy rule reproduces ledger rides and value for {reproduced}/{len(rows)} ways")
    print(f"verdicts: {dict(verdicts)}")
    for row in rows:
        if row["verdict"] != "holds":
            print(f"  {row['way_id']} {row['uploaded_value']}: {row.get('reason', row['verdict'])}")
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
