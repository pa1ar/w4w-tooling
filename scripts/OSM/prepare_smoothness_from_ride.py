#!/usr/bin/env python3
"""
Prepare OSM smoothness proposals from a scooter ride.

Pipeline:
1) Load ride points (CSV or JSON) with lat/lon and vibration metric (z-std mg)
2) Smooth/denoise and classify each point into OSM smoothness categories
3) Map-match points via Mapbox (profile mapbox/walking)
4) Fetch nearby OSM highway ways via Overpass and build a spatial index
5) Assign matched points to nearest way within tolerance
6) Aggregate per-way: coverage, category distribution, longest bad run
7) Apply policy -> proposed tag; export CSV and Folium review map

Env requirements (.env):
- MAPBOX_ACCESS_TOKEN
"""

import os
import sys
import csv
import math
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
import pandas as pd
from dotenv import load_dotenv
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from shapely.ops import transform, unary_union
from pyproj import Transformer

try:
    import folium
except Exception:
    folium = None


PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
# default Overpass; can be overridden via CLI/env
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_FALLBACKS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


# Classification thresholds (mg) – overridable at runtime via set_classification_thresholds
_CLASSIFY_THR = {
    "excellent_max": 60.0,
    "good_max": 110.0,
    "intermediate_max": 180.0,
    "bad_max": 250.0,
}


def set_classification_thresholds(excellent_max: float, good_max: float, intermediate_max: float, bad_max: float = 250.0) -> None:
    _CLASSIFY_THR["excellent_max"] = float(excellent_max)
    _CLASSIFY_THR["good_max"] = float(good_max)
    _CLASSIFY_THR["intermediate_max"] = float(intermediate_max)
    _CLASSIFY_THR["bad_max"] = float(bad_max)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def line_length_m(coords: List[Tuple[float, float]]) -> float:
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords[:-1], coords[1:]):
        total += haversine_m(lat1, lon1, lat2, lon2)
    return total


def load_points(input_path: Path, fmt: Optional[str]) -> pd.DataFrame:
    """Return DataFrame with columns: lat, lon, z_std_mg (optional), smoothness (optional)."""
    if fmt is None:
        if input_path.suffix.lower() == ".csv":
            fmt = "csv"
        elif input_path.suffix.lower() in {".json", ".geojson"}:
            fmt = "json"
        else:
            print("Error: cannot infer input format; use --format csv|json")
            sys.exit(1)

    if fmt == "csv":
        df = pd.read_csv(input_path)
        # best-effort column names
        lat_col = next((c for c in df.columns if c.lower() in {"lat", "latitude", "gps_lat"}), None)
        lon_col = next((c for c in df.columns if c.lower() in {"lon", "lng", "longitude", "gps_lon"}), None)
        if not lat_col or not lon_col:
            print("CSV must have lat/lon columns")
            sys.exit(1)
        df = df.rename(columns={lat_col: "lat", lon_col: "lon"})
        if "z_std_mg" not in df.columns:
            # accept z_std
            if "z_std" in df.columns:
                df = df.rename(columns={"z_std": "z_std_mg"})
        return df[[c for c in ["lat", "lon", "z_std_mg", "smoothness"] if c in df.columns]].copy()

    # json telemetry (expected format similar to telemetry_json/*)
    with open(input_path, "r") as f:
        data = json.load(f)
    records: List[Dict] = []
    ride = data.get("rideData", []) if isinstance(data, dict) else data
    for rec in ride:
        gps = rec.get("gpsPos") or {}
        lat = gps.get("gpsLat")
        lon = gps.get("gpsLon")
        if lat is None or lon is None:
            continue
        # filter invalid fixes and zeros
        gps_fix = gps.get("gpsFix", False)
        hacc = gps.get("hacc")
        if not gps_fix:
            continue
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            continue
        if isinstance(hacc, (int, float)) and hacc > 10.0:
            # reject very inaccurate points
            continue
        # capture speed in km/h (raw unit is 1/10 km/h per Bolt docs)
        speed = None
        gps_info = rec.get("gpsInfo") or {}
        if isinstance(gps_info.get("speed"), (int, float)):
            speed = float(gps_info.get("speed")) / 10.0
        else:
            cur_spd = rec.get("currentSpeed")
            if isinstance(cur_spd, list) and cur_spd:
                try:
                    speed = float(sum(cur_spd) / len(cur_spd)) / 10.0
                except Exception:
                    speed = None
        acc = rec.get("accelerationCoord")
        z_mg: Optional[float] = None
        if isinstance(acc, list) and len(acc) >= 3:
            # acc is flattened triples [x,y,z, x,y,z, ...]
            # compute simple std of z across this packet
            zs = [acc[i] for i in range(2, len(acc), 3)]
            if zs:
                # treat raw units as mg if already scaled, else keep as arbitrary
                z_mg = float(pd.Series(zs).std())
        records.append({"lat": lat, "lon": lon, "z_std_mg": z_mg, "speed": speed})
    df = pd.DataFrame.from_records(records)
    return df


def classify_point(z_std_mg: Optional[float]) -> str:
    """Map z-std (mg) to OSM smoothness using configurable thresholds.
    5 wheelchair-relevant classes: excellent<60, good<110, intermediate<180, bad<250, very_bad>=250.
    """
    if z_std_mg is None or pd.isna(z_std_mg):
        return "intermediate"  # neutral default
    z = float(z_std_mg)
    t1 = float(_CLASSIFY_THR.get("excellent_max", 60.0))
    t2 = float(_CLASSIFY_THR.get("good_max", 110.0))
    t3 = float(_CLASSIFY_THR.get("intermediate_max", 180.0))
    t4 = float(_CLASSIFY_THR.get("bad_max", 250.0))
    if z < t1:
        return "excellent"
    if z < t2:
        return "good"
    if z < t3:
        return "intermediate"
    if z < t4:
        return "bad"
    return "very_bad"


def smooth_and_classify(df: pd.DataFrame, window_pts: int = 25) -> pd.DataFrame:
    df = df.copy()
    if "z_std_mg" in df.columns:
        df["z_std_smooth"] = df["z_std_mg"].rolling(window_pts, min_periods=max(3, window_pts // 3)).median()
        df["smoothness_calc"] = df["z_std_smooth"].apply(classify_point)
    if "smoothness" in df.columns:
        # prefer provided labels if present, else use calc
        df["smoothness_point"] = df["smoothness"].fillna(df.get("smoothness_calc"))
    else:
        df["smoothness_point"] = df.get("smoothness_calc", pd.Series(["intermediate"] * len(df)))
    # mask stationary: speed <= threshold or near-constant z with no movement
    try:
        df = _mask_stationary(df)
    except Exception:
        pass
    cols = ["lat", "lon", "smoothness_point"]
    if "z_std_mg" in df.columns:
        cols += ["z_std_mg", "z_std_smooth"]
    if "speed" in df.columns:
        cols += ["speed"]
    return df[cols]


def _mask_stationary(df: pd.DataFrame) -> pd.DataFrame:
    speed_ok = None
    if "speed" in df.columns:
        try:
            sp = pd.to_numeric(df["speed"], errors="coerce").fillna(0)
            speed_ok = sp > 0.1
        except Exception:
            speed_ok = None
    z_std = df.get("z_std_mg")
    z_const = z_std.rolling(5, min_periods=3).std().fillna(0) < 1.0 if z_std is not None else None
    move_flags: List[bool] = []
    prev_lon = None
    prev_lat = None
    for lon, lat in zip(df["lon"].tolist(), df["lat"].tolist()):
        if prev_lon is None:
            move_flags.append(False)
        else:
            d = haversine_m(prev_lat, prev_lon, float(lat), float(lon))
            move_flags.append(d > 0.5)
        prev_lon, prev_lat = float(lon), float(lat)
    moving = pd.Series(move_flags).rolling(5, min_periods=3).sum().fillna(0) > 1
    if speed_ok is not None:
        stationary = (~speed_ok) & ((z_const if z_const is not None else False) | (~moving))
    else:
        stationary = ((z_const if z_const is not None else False) | (~moving))
    df.loc[stationary, "smoothness_point"] = pd.NA
    return df


def mapbox_match(coords: List[Tuple[float, float]], access_token: str, profile: str = "mapbox/walking", chunk_size: int = 100) -> List[Tuple[float, float]]:
    """Return list of snapped (lon,lat) in same order; unmatched points are skipped."""
    snapped: List[Tuple[float, float]] = []
    base = f"https://api.mapbox.com/matching/v5/{profile}/"
    headers = {"User-Agent": "w4w-mapmatch/1.0"}
    for i in range(0, len(coords), chunk_size):
        batch = coords[i:i + chunk_size]
        coord_str = ";".join([f"{lon},{lat}" for lon, lat in batch])
        params = {
            "access_token": access_token,
            "geometries": "geojson",
            "overview": "full",
            "tidy": "true",
            "steps": "false",
        }
        url = base + coord_str
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"Mapbox error {resp.status_code}: {resp.text[:200]}")
            continue
        data = resp.json()
        tracepoints = data.get("tracepoints") or []
        for tp in tracepoints:
            if not tp or "location" not in tp or tp.get("matchings_index") is None:
                snapped.append(None)  # keep alignment
            else:
                lon, lat = tp["location"]
                snapped.append((lon, lat))
        time.sleep(0.15)  # gentle rate limiting
    # ensure same length; if not, pad/truncate
    if len(snapped) < len(coords):
        snapped += [None] * (len(coords) - len(snapped))
    return snapped[:len(coords)]


def fetch_osm_ways_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float,
                        overpass_url: str, timeout_s: int) -> List[Dict]:
    ways_file = os.getenv("OVERPASS_WAYS_FILE", "").strip()
    if ways_file:
        with open(ways_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        elements = cached.get("ways") or cached.get("elements") or []
        return [el for el in elements if el.get("type") == "way"]

    highway_regex = os.getenv("OVERPASS_HIGHWAY_REGEX", "").strip()
    highway_filter = (
        f'["highway"~"{highway_regex}"]'
        if highway_regex
        else '["highway"]'
    )
    query = f"""
    [out:json][timeout:{timeout_s}];
    (
      way{highway_filter}({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out tags geom;
    """
    resp = requests.post(
        overpass_url,
        data={"data": query},
        headers={"User-Agent": "W4W-Tooling/0.1"},
        timeout=timeout_s + 10,
    )
    resp.raise_for_status()
    data = resp.json()
    return [el for el in data.get("elements", []) if el.get("type") == "way"]


def build_way_index(ways: List[Dict]) -> Tuple[STRtree, Dict[int, LineString], Dict[int, Dict], List[LineString], List[int]]:
    id_to_geom: Dict[int, LineString] = {}
    id_to_tags: Dict[int, Dict] = {}
    geoms: List[LineString] = []
    geom_way_ids: List[int] = []
    for el in ways:
        wid = int(el["id"])
        geom = [(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])]
        if len(geom) < 2:
            continue
        line = LineString(geom)
        id_to_geom[wid] = line
        id_to_tags[wid] = el.get("tags", {})
        geoms.append(line)
        geom_way_ids.append(wid)
    tree = STRtree(geoms)
    return tree, id_to_geom, id_to_tags, geoms, geom_way_ids


def clip_ways_to_trace(snapped: List[Optional[Tuple[float, float]]],
                      id_to_geom: Dict[int, LineString],
                      buffer_m: float = 18.0) -> Dict[int, LineString]:
    """Clip OSM ways to a narrow corridor around the rider's trace.

    - snapped: list of (lon,lat) or None of same length as points
    - id_to_geom: full way geometries in lon/lat
    - buffer_m: corridor half-width in meters
    Returns: way_id -> clipped LineString (lon/lat) intersecting the corridor
    """
    coords = []
    for s in snapped:
        if not s:
            continue
        lon, lat = s
        if lon is None or lat is None:
            continue
        coords.append((lon, lat))
    if not coords:
        return {}
    trace_ll = LineString(coords)
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
    to_ll = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
    trace_m = transform(to_m, trace_ll)
    corridor_m = trace_m.buffer(buffer_m)

    clipped: Dict[int, LineString] = {}
    for wid, geom_ll in id_to_geom.items():
        try:
            geom_m = transform(to_m, geom_ll)
            inter_m = geom_m.intersection(corridor_m)
            if inter_m.is_empty:
                continue
            if inter_m.geom_type == "LineString":
                inter_ll = transform(to_ll, inter_m)
                if inter_ll.length > 0:
                    clipped[wid] = inter_ll
            elif inter_m.geom_type == "MultiLineString":
                parts = [transform(to_ll, g) for g in inter_m.geoms if g.length > 0]
                if parts:
                    # Keep as MultiLineString to preserve all fragments
                    try:
                        from shapely.geometry import MultiLineString
                        inter_ll = MultiLineString(parts)
                    except Exception:
                        inter_ll = unary_union(parts)
                    clipped[wid] = inter_ll
        except Exception:
            continue
    return clipped


def assign_points_to_ways(snapped: List[Optional[Tuple[float, float]]], tree: STRtree,
                          geoms: List[LineString], geom_way_ids: List[int],
                          tolerance_m: float) -> List[Optional[int]]:
    assigned: List[Optional[int]] = []
    for pt in snapped:
        if pt is None:
            assigned.append(None)
            continue
        lon, lat = pt
        sp = Point(lon, lat)
        j_idx: Optional[int] = None
        d_m: float = float("inf")
        # Prefer query_nearest if available
        # Shapely 2.x: returns numpy array of indices
        try:
            res = tree.query_nearest(sp, return_distance=False)
            # Shapely >=2.0 returns ndarray or array-like with indices
            if hasattr(res, '__len__') and len(res) > 0:
                j_idx = int(res[0]) if hasattr(res, '__getitem__') else None
            elif hasattr(res, 'geom_type'):
                # fallback: geometry object (older versions)
                try:
                    j_idx = geoms.index(res)
                except ValueError:
                    j_idx = None
        except Exception as e:
            # query_nearest failed; will use buffer fallback
            j_idx = None
        if j_idx is None:
            # fallback: expand buffer in degrees proportional to tolerance (≈111km/deg)
            buffer_deg = max(0.0002, (tolerance_m / 111320.0) * 1.5)
            try:
                _, cand_js = tree.query(sp.buffer(buffer_deg), return_index=True)
                cand_js = list(cand_js)
            except Exception:
                cand_js = []
            if not cand_js:
                assigned.append(None)
                continue
            best_j = None
            best_d = float("inf")
            for j in cand_js:
                try:
                    line_c = geoms[j]
                    nearest_on = line_c.interpolate(line_c.project(sp))
                    d = haversine_m(lat, lon, nearest_on.y, nearest_on.x)
                    if d < best_d:
                        best_d = d
                        best_j = j
                except Exception:
                    continue
            j_idx = best_j
            d_m = best_d
        # final distance using nearest point on chosen geometry
        if j_idx is None or j_idx < 0 or j_idx >= len(geoms):
            assigned.append(None)
            continue
        line = geoms[j_idx]
        try:
            nearest_on = line.interpolate(line.project(sp))
            d_m = haversine_m(lat, lon, nearest_on.y, nearest_on.x)
        except Exception:
            assigned.append(None)
            continue
        if d_m <= tolerance_m:
            assigned.append(geom_way_ids[j_idx])
        else:
            assigned.append(None)
    return assigned


def assign_points_to_ways_bruteforce(snapped: List[Optional[Tuple[float, float]]],
                                     geoms: List[LineString], geom_way_ids: List[int],
                                     tolerance_m: float) -> List[Optional[int]]:
    assigned: List[Optional[int]] = []
    for pt in snapped:
        if pt is None:
            assigned.append(None)
            continue
        lon, lat = pt
        sp = Point(lon, lat)
        best_j = None
        best_d = float("inf")
        for j, line in enumerate(geoms):
            try:
                nearest_on = line.interpolate(line.project(sp))
                d = haversine_m(lat, lon, nearest_on.y, nearest_on.x)
                if d < best_d:
                    best_d = d
                    best_j = j
            except Exception:
                continue
        if best_j is not None and best_d <= tolerance_m:
            assigned.append(geom_way_ids[best_j])
        else:
            assigned.append(None)
    return assigned


def aggregate_by_way(df_pts: pd.DataFrame, id_to_geom: Dict[int, LineString], id_to_tags: Dict[int, Dict], bad_run_threshold_m: float) -> List[Dict]:
    proposals: List[Dict] = []
    # group by way id
    for way_id, g in df_pts.groupby("way_id"):
        if pd.isna(way_id):
            continue
        way_id = int(way_id)
        way_geom = id_to_geom.get(way_id)
        if way_geom is None:
            continue
        # way length (support LineString or MultiLineString)
        try:
            parts = getattr(way_geom, 'geoms', None)
        except Exception:
            parts = None
        if parts:
            way_len_m = 0.0
            for sub in parts:
                try:
                    way_len_m += line_length_m(list(sub.coords))
                except Exception:
                    continue
        else:
            coords = list(way_geom.coords)
            way_len_m = line_length_m(coords)
        # coverage: sum distance between consecutive points assigned to this way
        covered_m = 0.0
        bad_run_m = 0.0
        curr_bad_run = 0.0
        counts: Dict[str, int] = {}
        prev: Optional[Tuple[float, float]] = None
        prev_cat: Optional[str] = None
        for _, row in g.iterrows():
            cat = row.get("smoothness_point")
            if pd.isna(cat) or not cat:
                continue
            counts[cat] = counts.get(cat, 0) + 1
            pt = (row["lon_snapped"], row["lat_snapped"]) if pd.notna(row["lon_snapped"]) else None
            if prev and pt:
                seg = haversine_m(prev[1], prev[0], pt[1], pt[0])
                # accumulate coverage on same way
                covered_m += seg
                # track bad run
                is_bad = cat in {"bad", "very_bad"}
                if is_bad and prev_cat in {"bad", "very_bad"}:
                    curr_bad_run += seg
                else:
                    bad_run_m = max(bad_run_m, curr_bad_run)
                    curr_bad_run = seg if is_bad else 0.0
            prev = pt
            prev_cat = cat
        bad_run_m = max(bad_run_m, curr_bad_run)
        coverage_pct = (covered_m / way_len_m) if way_len_m > 0 else 0.0
        total_pts = sum(counts.values()) or 1
        inter_or_better = sum(counts.get(k, 0) for k in ["excellent", "good", "intermediate"])
        agree_pct = inter_or_better / total_pts

        # Check existing tags first
        existing = (id_to_tags.get(way_id) or {}).get("smoothness")

        # Policy: only propose if way has NO smoothness tag yet
        proposed: Optional[str] = None
        if not existing:
            if bad_run_m >= bad_run_threshold_m:
                proposed = "bad"
            elif agree_pct >= 0.7:
                proposed = "intermediate"
        proposals.append({
            "way_id": way_id,
            "proposed_value": proposed or "",
            "coverage_pct": round(coverage_pct, 3),
            "bad_run_m": round(bad_run_m, 1),
            "agree_pct": round(agree_pct, 3),
            "existing_smoothness": existing or "",
            "counts": json.dumps(counts, ensure_ascii=False),
            "comment": "[w4w] smoothness from scooter telemetry",
        })
    return proposals


def make_map(
    proposals: List[Dict],
    id_to_geom: Dict[int, LineString],
    out_html: Path,
    raw_path_coords: Optional[List[Tuple[float, float]]] = None,
) -> None:
    """Generate Mapbox GL JS interactive review map."""
    # Build GeoJSON
    features = []
    all_coords = []
    for prop in proposals:
        way_id = int(prop["way_id"])
        geom = id_to_geom.get(way_id)
        if not geom:
            continue
        # Support MultiLineString as either MultiLineString or exploded LineStrings
        coords_list: List[List[float]] = []
        multi_coords: List[List[List[float]]] = []
        parts = getattr(geom, 'geoms', None)
        if parts:
            for sub in parts:
                sub_coords = [[lon, lat] for lon, lat in sub.coords]
                if sub_coords:
                    multi_coords.append(sub_coords)
                    all_coords.extend(sub_coords)
        else:
            coords_list = [[lon, lat] for lon, lat in geom.coords]
            all_coords.extend(coords_list)

        # Derive values for coloring
        proposed = prop.get("proposed_value", "")
        # detected_value: ignore existing tag, color purely from telemetry metrics
        detected_value = ""
        try:
            if float(prop.get("bad_run_m", 0)) >= 30.0:
                detected_value = "bad"
            elif float(prop.get("agree_pct", 0)) >= 0.7:
                detected_value = "intermediate"
        except Exception:
            detected_value = proposed or ""
        # filtered color: honor existing tag gray-out
        if proposed == "bad":
            color = "#e74c3c"  # red
        elif proposed == "intermediate":
            color = "#2ecc71"  # green (target)
        elif prop.get("existing_smoothness"):
            color = "#95a5a6"  # gray (already tagged)
        else:
            color = "#bdc3c7"  # light gray (skipped)

        geometry_obj = (
            {"type": "MultiLineString", "coordinates": multi_coords}
            if parts else
            {"type": "LineString", "coordinates": coords_list}
        )
        # Agreement color between predicted and existing
        def _norm(lbl: str | None) -> str | None:
            if not lbl:
                return None
            t = str(lbl).strip().lower()
            return 'very_bad' if t in {'very-bad','very bad'} else t
        _order = {'excellent': 0, 'good': 1, 'intermediate': 2, 'bad': 3, 'very_bad': 4}
        _exist = _norm(prop.get("existing_smoothness", ""))
        _pred = _norm(prop.get("predicted_way_class", ""))
        if not _exist:
            agreement_color = '#bdc3c7'  # no OSM tag -> gray
        elif _exist == _pred and _exist is not None:
            agreement_color = '#2ecc71'  # green
        else:
            try:
                d = abs(int(_order.get(_exist)) - int(_order.get(_pred)))
            except Exception:
                d = None
            if d == 1:
                agreement_color = '#f1c40f'  # yellow
            elif d == 2:
                agreement_color = '#e67e22'  # orange
            elif d is not None and d > 2:
                agreement_color = '#e74c3c'  # red (should be rare)
            else:
                agreement_color = '#bdc3c7'

        features.append({
            "type": "Feature",
            "geometry": geometry_obj,
            "properties": {
                "way_id": way_id,
                "proposed_value": proposed or "skip",
                "coverage_pct": prop.get("coverage_pct", 0),
                "bad_run_m": prop.get("bad_run_m", 0),
                "agree_pct": prop.get("agree_pct", 0),
                "existing_smoothness": prop.get("existing_smoothness", ""),
                "counts": prop.get("counts", "{}"),
                "color": color,
                "detected_value": detected_value,
                "confidence_wheelchair": prop.get("confidence_wheelchair", 0.0),
                "predicted_way_class": prop.get("predicted_way_class", ""),
                "osm_match": prop.get("osm_match", ""),
                "osm_match_pct": prop.get("osm_match_pct", ""),
                "agreement_color": agreement_color
            }
        })

    if not all_coords:
        return

    center_lon = sum(c[0] for c in all_coords) / len(all_coords)
    center_lat = sum(c[1] for c in all_coords) / len(all_coords)

    geojson = {"type": "FeatureCollection", "features": features}
    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    # Optional raw path as GeoJSON string for Mapbox GL
    # Supports either a list of (lon,lat) tuples OR a list of dicts with lon/lat/z keys
    raw_geojson_str = "null"
    if raw_path_coords and len(raw_path_coords) >= 2:
        try:
            # Detect shape: tuple-only vs dicts with z
            first = raw_path_coords[0]
            if isinstance(first, dict) and 'lon' in first and 'lat' in first:
                pts = raw_path_coords  # type: ignore
                # Build small segments with per-segment z (average of endpoints)
                seg_features = []
                for i in range(len(pts)-1):
                    p1 = pts[i]
                    p2 = pts[i+1]
                    try:
                        lon1, lat1 = float(p1['lon']), float(p1['lat'])
                        lon2, lat2 = float(p2['lon']), float(p2['lat'])
                    except Exception:
                        continue
                    z1 = p1.get('z')
                    z2 = p2.get('z')
                    z_avg = None
                    try:
                        if z1 is not None and z2 is not None:
                            z_avg = (float(z1) + float(z2)) / 2.0
                    except Exception:
                        z_avg = None
                    seg_features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[lon1, lat1], [lon2, lat2]],
                        },
                        "properties": {
                            "z": (z_avg if z_avg is not None else 0.0)
                        }
                    })
                raw_geojson = {"type": "FeatureCollection", "features": seg_features}
            else:
                # Fallback: whole path as one line (mono color)
                raw_geojson = {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[float(lon), float(lat)] for lon, lat in raw_path_coords],
                    },
                    "properties": {"color": "#1f77b4"},
                }
            raw_geojson_str = json.dumps(raw_geojson, ensure_ascii=False)
        except Exception:
            raw_geojson_str = "null"

    # thresholds for raw path coloring
    t1 = float(_CLASSIFY_THR.get("excellent_max", 60.0))
    t2 = float(_CLASSIFY_THR.get("good_max", 110.0))
    t3 = float(_CLASSIFY_THR.get("intermediate_max", 180.0))

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>OSM Smoothness Proposals Review</title>
    <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.css" rel="stylesheet">
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .legend {{
            position: absolute;
            bottom: 30px;
            right: 10px;
            background: white;
            padding: 10px;
            border-radius: 3px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.2);
            font-size: 13px;
            z-index: 1;
        }}
        .legend h4 {{ margin: 0 0 10px; font-size: 14px; }}
        .legend-item {{ margin: 4px 0; display: flex; align-items: center; }}
        .legend-color {{ width: 30px; height: 3px; margin-right: 8px; }}
        .mapboxgl-popup-content {{ max-width: 350px; }}
    </style>
</head>
<body>
<div id="map"></div>
<div id="menu" style="position:absolute;top:10px;left:10px;background:#fff;padding:8px;border-radius:4px;z-index:1;">
  <label><input type="checkbox" id="toggle-filtered" checked> filtered</label>
  <label style="margin-left:8px;"><input type="checkbox" id="toggle-segments" checked> segments</label>
  <label style="margin-left:8px;"><input type="checkbox" id="toggle-confidence"> confidence</label>
  <label style="margin-left:8px;"><input type="checkbox" id="toggle-agreement"> agreement</label>
  {('<label style="margin-left:8px;"><input type="checkbox" id="toggle-raw" checked> path</label>' if raw_path_coords else '')}
</div>
<div id="legends" class="legend">
    <div id="legend-filtered">
        <h4>Filtered</h4>
        <div class="legend-item"><div class="legend-color" style="background: #e74c3c;"></div><span>Bad (≥30m bad run)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #f39c12;"></div><span>Intermediate (≥70% agree)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #95a5a6;"></div><span>Already tagged</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #bdc3c7;"></div><span>Skip (no proposal)</span></div>
    </div>
    <div id="legend-segments" style="display:none; margin-top:10px;">
        <h4>Segments</h4>
        <div class="legend-item"><div class="legend-color" style="background: #e74c3c;"></div><span>Detected bad</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #2ecc71;"></div><span>Detected intermediate</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #1f77b4;"></div><span>Detected good/excellent</span></div>
    </div>
    <div id="legend-confidence" style="display:none; margin-top:10px;">
        <h4>Confidence</h4>
        <div class="legend-item"><div class="legend-color" style="background: #e74c3c; height: 6px;"></div><span>Bad (width ∝ confidence)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #f39c12; height: 6px;"></div><span>Intermediate (width ∝ confidence)</span></div>
    </div>
    <div id="legend-agreement" style="display:none; margin-top:10px;">
        <h4>Agreement</h4>
        <div class="legend-item"><div class="legend-color" style="background: #2ecc71;"></div><span>Match (predicted = OSM)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #bdc3c7;"></div><span>No OSM tag</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #f1c40f;"></div><span>1 level off</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #e67e22;"></div><span>2 levels off</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #e74c3c;"></div><span>>2 levels off</span></div>
    </div>
    <div id="legend-path" style="display:none; margin-top:10px;">
        <h4>Path smoothness (z mg)</h4>
        <div class="legend-item"><div class="legend-color" style="background: #00bcd4;"></div><span>≤ {t1:.0f} (excellent)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #1f77b4;"></div><span>{t1:.0f}–{t2:.0f} (good)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #2ecc71;"></div><span>{t2:.0f}–{t3:.0f} (intermediate)</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #e74c3c;"></div><span>&gt; {t3:.0f} (bad)</span></div>
    </div>
</div>

<script>
mapboxgl.accessToken = '{mapbox_token}';

const map = new mapboxgl.Map({{
    container: 'map',
    style: 'mapbox://styles/mapbox/streets-v12',
    center: [{center_lon}, {center_lat}],
    zoom: 14
}});

const geojson = {json.dumps(geojson, ensure_ascii=False)};
const rawGeo = {raw_geojson_str};

map.on('load', () => {{
    map.addSource('proposals', {{
        type: 'geojson',
        data: geojson
    }});

    // Agreement layer (green if predicted==existing; gray if no tag; yellow/orange/red by difference level)
    map.addLayer({{
        id: 'agreement-lines',
        type: 'line',
        source: 'proposals',
        layout: {{ 'visibility': 'none' }},
        paint: {{
            'line-color': ['get','agreement_color'],
            'line-width': 5,
            'line-opacity': 0.9
        }}
    }});

    // Filtered (policy-colored) layer
    map.addLayer({{
        id: 'filtered-lines',
        type: 'line',
        source: 'proposals',
        paint: {{
            'line-color': ['get', 'color'],
            'line-width': 4,
            'line-opacity': 0.8
        }}
    }});

    // Unfiltered segments layer (ignores existing tag color logic)
    map.addLayer({{
        id: 'segments-lines',
        type: 'line',
        source: 'proposals',
        layout: {{ 'visibility': 'none' }},
        paint: {{
            'line-color': [
                'case',
                ['==', ['get','detected_value'], 'bad'], '#e74c3c',
                ['==', ['get','detected_value'], 'intermediate'], '#2ecc71',
                /* else */ '#1f77b4'
            ],
            'line-width': 3,
            'line-opacity': 0.7
        }}
    }});

    // Wheelchair confidence casing (halo)
    map.addLayer({{
        id: 'confidence-casing',
        type: 'line',
        source: 'proposals',
        layout: {{ 'visibility': 'none', 'line-cap': 'round', 'line-join': 'round' }},
        paint: {{
            'line-color': ['get','color'],
            'line-width': 14,
            'line-opacity': [
                'interpolate', ['linear'], ['to-number', ['get','confidence_wheelchair'], 0],
                0, 0.0,
                0.2, 0.25,
                0.4, 0.45,
                0.6, 0.65,
                0.8, 0.8,
                1, 0.9
            ],
            'line-blur': 2.0
        }}
    }}, 'filtered-lines');

    // Raw GPS path source and layer (supports per-segment z coloring when FeatureCollection provided)
    if (rawGeo) {{
        const validLineString = rawGeo.geometry && rawGeo.geometry.coordinates && rawGeo.geometry.coordinates.length > 1;
        const validFC = rawGeo.type === 'FeatureCollection' && rawGeo.features && rawGeo.features.length > 0;
        if (validLineString || validFC) {{
            map.addSource('raw-path', {{
                type: 'geojson',
                data: rawGeo
            }});
            map.addLayer({{
                id: 'raw-line',
                type: 'line',
                source: 'raw-path',
                paint: {{
                    'line-color': [
                        'case',
                        // When per-segment z available
                        ['has','z'],
                        ['interpolate', ['linear'], ['to-number', ['get','z'], 0],
                            0, '#00bcd4',        // cyan (excellent)
                            {t1}, '#00bcd4',     // ≤t1 -> cyan
                            {t2}, '#1f77b4',     // good -> blue
                            {t3}, '#2ecc71',     // intermediate -> green (target)
                            800, '#e74c3c'       // >t3 -> red (bad)
                        ],
                        // Fallback mono color when no z
                        ['coalesce', ['get','color'], '#1f77b4']
                    ],
                    'line-width': 5,
                    'line-opacity': 0.8
                }}
            }});

            // Hover value for path (show z + class on hover if available)
            if (validFC) {{
                const T1 = {t1};
                const T2 = {t2};
                const T3 = {t3};
                let pathHoverPopup = new mapboxgl.Popup({{ closeButton: false, closeOnClick: false }});
                map.on('mousemove', 'raw-line', (e) => {{
                    const f = e.features && e.features[0];
                    if (!f) return;
                    const z = f.properties && f.properties.z;
                    if (z === undefined || z === null) {{
                        map.getCanvas().style.cursor = '';
                        pathHoverPopup.remove();
                        return;
                    }}
                    const zNum = Number(z);
                    const cls = (zNum <= T1) ? 'excellent' : (zNum <= T2) ? 'good' : (zNum <= T3) ? 'intermediate' : 'bad';
                    const html = `<div style="font-size:12px;line-height:1.2;">
                        <div><strong>${{zNum.toFixed(0)}} mg</strong></div>
                        <div>${{cls}}</div>
                    </div>`;
                    map.getCanvas().style.cursor = 'crosshair';
                    pathHoverPopup.setLngLat(e.lngLat).setHTML(html).addTo(map);
                }});
                map.on('mouseleave', 'raw-line', () => {{
                    map.getCanvas().style.cursor = '';
                    pathHoverPopup.remove();
                }});
            }}
        }}
    }}

    // Popup on click (filtered layer)
    map.on('click', 'filtered-lines', (e) => {{
        const props = e.features[0].properties;
        const way_id = props.way_id;
        const osmLink = `https://www.openstreetmap.org/way/${{way_id}}`;

        let html = `<h3>Way ${{way_id}}</h3>`;
        html += `<p><strong>Proposed:</strong> ${{props.proposed_value}}</p>`;
        html += `<p><strong>Existing:</strong> ${{props.existing_smoothness || 'none'}}</p>`;
        if (props.predicted_way_class) {{
        html += `<p><strong>Predicted:</strong> ${{props.predicted_way_class}}</p>`;
        }}
        if (props.osm_match_pct !== undefined && props.osm_match_pct !== '' ) {{
        const pct = (parseFloat(props.osm_match_pct) * 100).toFixed(0);
        html += `<p><strong>OSM match:</strong> ${{props.osm_match ? 'yes' : 'no'}} (${{isNaN(pct) ? '-' : pct+'%'}})</p>`;
        }}
        html += `<p><strong>Coverage:</strong> ${{(props.coverage_pct * 100).toFixed(1)}}%</p>`;
        html += `<p><strong>Agreement:</strong> ${{(props.agree_pct * 100).toFixed(1)}}%</p>`;
        html += `<p><strong>Bad run:</strong> ${{props.bad_run_m}} m</p>`;
        html += `<p><strong>Counts:</strong> ${{props.counts}}</p>`;
        html += `<p><a href="${{osmLink}}" target="_blank">View on OSM ↗</a></p>`;

        new mapboxgl.Popup()
            .setLngLat(e.lngLat)
            .setHTML(html)
            .addTo(map);
    }});

    // Popup on click (agreement layer)
    map.on('click', 'agreement-lines', (e) => {{
        const props = e.features[0].properties;
        const way_id = props.way_id;
        const osmLink = `https://www.openstreetmap.org/way/${{way_id}}`;

        let html = `<h3>Way ${{way_id}}</h3>`;
        html += `<p><strong>Existing:</strong> ${{props.existing_smoothness || 'none'}}</p>`;
        if (props.predicted_way_class) {{
        html += `<p><strong>Predicted:</strong> ${{props.predicted_way_class}}</p>`;
        }}
        if (props.osm_match_pct !== undefined && props.osm_match_pct !== '' ) {{
        const pct = (parseFloat(props.osm_match_pct) * 100).toFixed(0);
        html += `<p><strong>OSM match:</strong> ${{props.osm_match ? 'yes' : 'no'}} (${{isNaN(pct) ? '-' : pct+'%'}})</p>`;
        }}
        html += `<p><strong>Proposed:</strong> ${{props.proposed_value}}</p>`;
        html += `<p><a href="${{osmLink}}" target="_blank">View on OSM ↗</a></p>`;

        new mapboxgl.Popup()
            .setLngLat(e.lngLat)
            .setHTML(html)
            .addTo(map);
    }});

    // Cursor pointer on hover
    map.on('mouseenter', 'filtered-lines', () => {{
        map.getCanvas().style.cursor = 'pointer';
    }});
    map.on('mouseleave', 'filtered-lines', () => {{
        map.getCanvas().style.cursor = '';
    }});
    map.on('mouseenter', 'agreement-lines', () => {{
        map.getCanvas().style.cursor = 'pointer';
    }});
    map.on('mouseleave', 'agreement-lines', () => {{
        map.getCanvas().style.cursor = '';
    }});
    // Layer toggles (path/segments/filtered)
    function setVisibility(layerId, visible) {{
        const v = visible ? 'visible' : 'none';
        if (map.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', v);
    }}
    function setLegend(legendId, visible) {{
        const el = document.getElementById(legendId);
        if (!el) return;
        el.style.display = visible ? 'block' : 'none';
    }}
    const tf = document.getElementById('toggle-filtered');
    if (tf) {{
      tf.addEventListener('change', (e) => {{
        setVisibility('filtered-lines', e.target.checked);
        setLegend('legend-filtered', e.target.checked);
      }});
    }}
    const ts = document.getElementById('toggle-segments');
    if (ts) {{
      ts.addEventListener('change', (e) => {{
        setVisibility('segments-lines', e.target.checked);
        setLegend('legend-segments', e.target.checked);
      }});
    }}
    const tc = document.getElementById('toggle-confidence');
    if (tc) {{
      tc.addEventListener('change', (e) => {{
        setVisibility('confidence-casing', e.target.checked);
        setLegend('legend-confidence', e.target.checked);
      }});
    }}
    const ta = document.getElementById('toggle-agreement');
    if (ta) {{
      ta.addEventListener('change', (e) => {{
        setVisibility('agreement-lines', e.target.checked);
        setLegend('legend-agreement', e.target.checked);
      }});
    }}
    const tr = document.getElementById('toggle-raw');
    if (tr) {{
      tr.addEventListener('change', (e) => {{
        setVisibility('raw-line', e.target.checked);
        setLegend('legend-path', e.target.checked);
      }});
    }}
    // Initialize legends based on defaults
    setLegend('legend-filtered', tf ? tf.checked : false);
    setLegend('legend-segments', ts ? ts.checked : false);
    setLegend('legend-confidence', tc ? tc.checked : false);
    setLegend('legend-agreement', ta ? ta.checked : false);
    setLegend('legend-path', tr ? tr.checked : false);
}});
</script>
</body>
</html>"""

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare smoothness proposals from ride data")
    parser.add_argument("--input", required=True, help="Path to ride data (CSV or JSON)")
    parser.add_argument("--format", choices=["csv", "json"], help="Input format (auto if omitted)")
    parser.add_argument("--profile", default="mapbox/walking", help="Mapbox profile (default: mapbox/walking)")
    parser.add_argument("--window-pts", type=int, default=25, help="Rolling window points for smoothing")
    parser.add_argument("--tolerance-m", type=float, default=15.0, help="Snap tolerance to assign points to ways")
    parser.add_argument("--bad-run-m", type=float, default=30.0, help="Contiguous bad run threshold (meters)")
    parser.add_argument("--out-csv", default=str(OUTPUT_DIR / "smoothness_proposals.csv"))
    parser.add_argument("--out-map", default=str(OUTPUT_DIR / "smoothness_proposals.html"))
    parser.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass endpoint")
    parser.add_argument("--overpass-timeout", type=int, default=60, help="Overpass timeout seconds")
    args = parser.parse_args()

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    access_token = os.getenv("MAPBOX_ACCESS_TOKEN")
    if not access_token:
        print("Error: MAPBOX_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    input_path = Path(args.input)
    df_raw = load_points(input_path, args.format)
    df_cls = smooth_and_classify(df_raw, window_pts=args.window_pts)

    coords = [(float(row["lon"]), float(row["lat"])) for _, row in df_cls.iterrows()]
    snapped = mapbox_match(coords, access_token, profile=args.profile)
    # bounds from snapped (fallback to raw)
    lats = [lat for item in snapped if item for _, lat in [item]] or list(df_cls["lat"].values)
    lons = [lon for item in snapped if item for lon, _ in [item]] or list(df_cls["lon"].values)
    if not lats or not lons:
        print("No coordinates available after matching")
        sys.exit(1)
    bbox_pad = 0.002  # ~200 meters pad
    min_lat, max_lat = min(lats) - bbox_pad, max(lats) + bbox_pad
    min_lon, max_lon = min(lons) - bbox_pad, max(lons) + bbox_pad

    # Try primary and fallbacks
    try_urls = [args.overpass_url] + [u for u in OVERPASS_FALLBACKS if u != args.overpass_url]
    ways: List[Dict] = []
    last_err: Optional[Exception] = None
    for url in try_urls:
        try:
            print(f"Querying Overpass: {url}")
            ways = fetch_osm_ways_bbox(min_lat, min_lon, max_lat, max_lon, url, args.overpass_timeout)
            if ways:
                break
        except Exception as e:
            last_err = e
            print(f"Overpass failed at {url}: {e}")
            time.sleep(1.0)
    if not ways:
        if last_err:
            raise last_err
        print("No OSM ways found in bbox")
        sys.exit(0)
    tree, id_to_geom, id_to_tags, geoms, geom_way_ids = build_way_index(ways)

    # Clip ways to rider corridor (strict)
    id_to_geom_clip = clip_ways_to_trace(snapped, id_to_geom, buffer_m=18.0)
    geoms = list(id_to_geom_clip.values())
    geom_way_ids = list(id_to_geom_clip.keys())
    tree = STRtree(geoms)

    # assign
    # per-point fallback: if snapped is None, use original coord
    to_assign: List[Optional[Tuple[float, float]]] = []
    for idx, s in enumerate(snapped):
        if s is not None:
            to_assign.append(s)
        else:
            lon_raw = float(df_cls.iloc[idx]["lon"]) if "lon" in df_cls.columns else None
            lat_raw = float(df_cls.iloc[idx]["lat"]) if "lat" in df_cls.columns else None
            if lon_raw is not None and lat_raw is not None:
                to_assign.append((lon_raw, lat_raw))
            else:
                to_assign.append(None)

    assigned_way_ids = assign_points_to_ways(to_assign, tree, geoms, geom_way_ids, args.tolerance_m)
    if all(v is None for v in assigned_way_ids):
        # Fallback: brute-force nearest to ensure we produce some proposals
        print("No assignments via spatial index; trying brute-force matching...")
        assigned_way_ids = assign_points_to_ways_bruteforce(to_assign, geoms, geom_way_ids, args.tolerance_m)
    # build working df with snapped coords and assignments
    df_pts = df_cls.copy()
    df_pts["lon_snapped"] = [pt[0] if pt else float("nan") for pt in to_assign]
    df_pts["lat_snapped"] = [pt[1] if pt else float("nan") for pt in to_assign]
    df_pts["way_id"] = assigned_way_ids

    df_assigned = df_pts.dropna(subset=["way_id"]).copy()
    print(f"Points total={len(df_pts)}, assigned_to_way={len(df_assigned)} across {len(id_to_geom_clip)} clipped ways")
    proposals = aggregate_by_way(df_assigned, id_to_geom_clip, id_to_tags, args.bad_run_m)
    print(f"Proposals count={len(proposals)}")

    # write CSV
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "way_id", "proposed_value", "coverage_pct", "bad_run_m", "agree_pct", "existing_smoothness", "counts", "comment"
        ])
        writer.writeheader()
        for p in proposals:
            writer.writerow(p)
    print(f"Wrote proposals CSV: {out_csv}")

    # map
    out_map = Path(args.out_map)
    make_map(proposals, id_to_geom_clip, out_map)
    if out_map.exists():
        print(f"Wrote review map:   {out_map}")


if __name__ == "__main__":
    main()
