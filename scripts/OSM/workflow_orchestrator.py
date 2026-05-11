from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any
import importlib.util
import importlib.util as _imp
import sys

# Import fetch_with_fallbacks without package context
_op_path = Path(__file__).resolve().parent / 'overpass_utils.py'
_op_spec = _imp.spec_from_file_location('overpass_utils', _op_path)
overpass_utils = _imp.module_from_spec(_op_spec)
sys.modules['overpass_utils'] = overpass_utils
assert _op_spec and _op_spec.loader
_op_spec.loader.exec_module(overpass_utils)  # type: ignore
fetch_with_fallbacks = overpass_utils.fetch_with_fallbacks


def _import_prep():
    scripts_dir = Path(__file__).resolve().parent
    prep_path = scripts_dir / "prepare_smoothness_from_ride.py"
    spec = importlib.util.spec_from_file_location("prep", prep_path)
    prep = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(prep)  # type: ignore[attr-defined]
    return prep


@dataclass
class WorkflowResult:
    proposals: List[Dict]
    id_to_geom_clip: Dict[int, object]
    df_assigned: Any  # pandas.DataFrame
    stats: Dict[str, float]


def run_clipped_workflow(
    input_path: Path,
    mapbox_token: str,
    overpass_urls: List[str],
    *,
    buffer_m: float = 18.0,
    bbox_pad: float = 0.002,
    tolerance_m: float = 25.0,
    bad_run_m: float = 30.0,
    thresholds: dict | None = None,
) -> WorkflowResult:
    """Run the full clipped pipeline end-to-end and return structured outputs."""
    prep = _import_prep()
    # Apply calibrated thresholds if provided
    if thresholds:
        try:
            prep.set_classification_thresholds(
                thresholds.get("excellent_max", 60.0),
                thresholds.get("good_max", 110.0),
                thresholds.get("intermediate_max", 180.0),
            )
        except Exception:
            pass

    # Load and classify
    df_raw = prep.load_points(input_path, fmt="json")
    df_cls = prep.smooth_and_classify(df_raw, window_pts=25)

    # Map-match (Mapbox walking profile)
    coords = [(float(row["lon"]), float(row["lat"])) for _, row in df_cls.iterrows()]
    snapped = prep.mapbox_match(coords, mapbox_token, profile="mapbox/walking")

    # Bounding box
    lats = [lat for item in snapped if item for _, lat in [item]] or list(df_cls["lat"].values)
    lons = [lon for item in snapped if item for lon, _ in [item]] or list(df_cls["lon"].values)
    min_lat, max_lat = min(lats) - bbox_pad, max(lats) + bbox_pad
    min_lon, max_lon = min(lons) - bbox_pad, max(lons) + bbox_pad

    # Overpass fetch with fallbacks
    ways = fetch_with_fallbacks(min_lat, min_lon, max_lat, max_lon, overpass_urls, timeout_s=90)

    # Build index and clip corridor
    _tree, id_to_geom, id_to_tags, geoms, geom_way_ids = prep.build_way_index(ways)
    id_to_geom_clip = prep.clip_ways_to_trace(snapped, id_to_geom, buffer_m=buffer_m)

    # Rebuild index on clipped geoms
    geoms = list(id_to_geom_clip.values())
    geom_way_ids = list(id_to_geom_clip.keys())
    from shapely.strtree import STRtree

    tree = STRtree(geoms)

    # Assign points (fallback to raw coord if not snapped)
    to_assign = []
    for idx, s in enumerate(snapped):
        if s is not None:
            to_assign.append(s)
        else:
            to_assign.append((float(df_cls.iloc[idx]["lon"]), float(df_cls.iloc[idx]["lat"])))

    assigned = prep.assign_points_to_ways(to_assign, tree, geoms, geom_way_ids, tolerance_m=tolerance_m)
    if all(v is None for v in assigned):
        assigned = prep.assign_points_to_ways_bruteforce(to_assign, geoms, geom_way_ids, tolerance_m=tolerance_m)

    # Build dataframe
    import pandas as pd

    df_pts = df_cls.copy()
    df_pts["lon_snapped"] = [pt[0] if pt else float("nan") for pt in to_assign]
    df_pts["lat_snapped"] = [pt[1] if pt else float("nan") for pt in to_assign]
    df_pts["way_id"] = assigned
    df_assigned = df_pts.dropna(subset=["way_id"]).copy()

    # Aggregate with policy
    proposals = prep.aggregate_by_way(df_assigned, id_to_geom_clip, id_to_tags, bad_run_threshold_m=bad_run_m)

    stats = {
        "points_total": float(len(df_pts)),
        "assigned_pct": 100.0 * float(len(df_assigned)) / float(len(df_pts) or 1),
        "proposals": float(len(proposals)),
    }
    return WorkflowResult(proposals, id_to_geom_clip, df_assigned, stats)
