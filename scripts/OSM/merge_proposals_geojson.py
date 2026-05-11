#!/usr/bin/env python3
"""
Merge per-ride proposal GeoJSON files into a single FeatureCollection that
the webapp can consume for highlighting OSM ways.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def guess_w4w_root() -> Path:
    """Best-effort resolution of the sibling w4w/ directory."""
    scripts_dir = Path(__file__).resolve().parent
    candidates = [
        scripts_dir.parent.parent / "w4w",
        scripts_dir.parent.parent.parent / "w4w",
        scripts_dir.parent.parent.parent.parent / "w4w",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_path_mapping(progress_path: Path) -> Dict[str, int]:
    """Map telemetry source_file -> path_id using gps_paths_progress.json."""
    if not progress_path.exists():
        raise FileNotFoundError(f"gps_paths_progress.json not found: {progress_path}")
    with open(progress_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    mapping: Dict[str, int] = {}
    for entry in data:
        source = entry.get("source_file")
        path_id = entry.get("path_id")
        if source is None or path_id is None:
            continue
        if source in mapping and mapping[source] != path_id:
            raise ValueError(f"Multiple path_ids for source_file={source}")
        mapping[source] = int(path_id)
    return mapping


def iter_geojson_files(inputs: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for item in inputs:
        if item.is_dir():
            files.extend(sorted(item.glob("*.geojson")))
        elif item.is_file():
            files.append(item)
    return files


def merge_features(
    geojson_files: Iterable[Path],
    path_mapping: Dict[str, int],
) -> List[Dict]:
    features: List[Dict] = []
    seen: Dict[Tuple[str, int], Dict] = {}
    for gj_path in geojson_files:
        with open(gj_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            way_id = props.get("way_id")
            source_file = props.get("source_file")
            if source_file is None or way_id is None:
                continue
            key = (source_file, int(way_id))
            props["path_id"] = props.get("path_id")
            if props["path_id"] is None:
                props["path_id"] = path_mapping.get(source_file)
            seen[key] = {
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": props,
            }
    features.extend(seen.values())
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge proposal GeoJSON files for Mapbox consumption.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="GeoJSON files or directories containing per-ride proposal GeoJSON files.",
    )
    default_w4w = guess_w4w_root()
    parser.add_argument(
        "--gps-progress",
        type=str,
        default=str(default_w4w / "public" / "data" / "gps_paths_progress.json"),
        help="Path to gps_paths_progress.json used to map source_file to path_id.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(default_w4w / "public" / "data" / "osm_smoothness_proposal_ways.geojson"),
        help="Output GeoJSON file path for merged proposal ways.",
    )
    args = parser.parse_args()

    input_paths = [Path(p).resolve() for p in args.inputs]
    geojson_files = iter_geojson_files(input_paths)
    if not geojson_files:
        raise SystemExit("No GeoJSON input files found.")

    progress_path = Path(args.gps_progress).resolve()
    out_path = Path(args.out).resolve()

    path_mapping = load_path_mapping(progress_path)
    features = merge_features(geojson_files, path_mapping)
    payload = {"type": "FeatureCollection", "features": features}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Merged {len(geojson_files)} files -> {out_path} (features={len(features)})")


if __name__ == "__main__":
    main()
