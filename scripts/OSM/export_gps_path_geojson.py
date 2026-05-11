"""
Utility to export a simple GPS path (lon/lat pairs) to GeoJSON LineString.

This module intentionally has no external dependencies beyond the Python stdlib.
It accepts either:
- an iterable of coordinate pairs [(lon, lat), ...], or
- a pandas.DataFrame with 'lon' and 'lat' columns.

Writes a FeatureCollection containing a single LineString to the specified path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Tuple, Any


def _is_number(value: Any) -> bool:
    try:
        # also filters out NaN because NaN != NaN
        v = float(value)
        return v == v
    except Exception:
        return False


def _to_coords_from_df(df: Any) -> list[tuple[float, float]]:
    """Extract (lon, lat) tuples from a DataFrame-like object.

    The object must have 'lon' and 'lat' columns. Values that are not numeric
    (including NaN) are skipped.
    """
    try:
        lons = df["lon"].tolist()  # type: ignore[index]
        lats = df["lat"].tolist()  # type: ignore[index]
    except Exception:
        return []
    coords: list[tuple[float, float]] = []
    for lo, la in zip(lons, lats):
        if _is_number(lo) and _is_number(la):
            coords.append((float(lo), float(la)))
    return coords


def write_gps_path_geojson(
    coords_or_df: Iterable[Tuple[float, float]] | Any,
    out_path: str | Path,
) -> Path:
    """Write a LineString GeoJSON for the given path.

    - coords_or_df: either an iterable of (lon, lat) pairs, or a DataFrame with
      'lon' and 'lat' columns
    - out_path: destination file path

    Returns the resolved output Path. Creates parent directories if needed.
    """
    # Normalize to list of (lon, lat)
    if hasattr(coords_or_df, "__iter__") and not hasattr(coords_or_df, "columns"):
        try:
            coords = [(float(lo), float(la)) for lo, la in coords_or_df]  # type: ignore[misc]
        except Exception:
            coords = []
    else:
        coords = _to_coords_from_df(coords_or_df)

    # Require at least two points
    if len(coords) < 2:
        # Still write a valid but empty collection to avoid client errors
        feature_collection = {"type": "FeatureCollection", "features": []}
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
        return out

    feature = {
        "type": "Feature",
        "properties": {"source": "w4w", "kind": "gps_raw"},
        "geometry": {"type": "LineString", "coordinates": coords},
    }
    feature_collection = {"type": "FeatureCollection", "features": [feature]}

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(feature_collection, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


__all__ = ["write_gps_path_geojson"]
