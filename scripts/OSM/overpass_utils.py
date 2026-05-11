from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from typing import List, Dict


def _import_prep_module():
    """Dynamically import prepare_smoothness_from_ride as 'prep'.

    Kept dynamic to avoid packaging changes and to be callable
    from notebooks or scripts alike.
    """
    scripts_dir = Path(__file__).resolve().parent
    prep_path = scripts_dir / "prepare_smoothness_from_ride.py"
    spec = importlib.util.spec_from_file_location("prep", prep_path)
    prep = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(prep)  # type: ignore[attr-defined]
    return prep


def fetch_with_fallbacks(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    urls: List[str],
    *,
    timeout_s: int = 90,
    sleep_s: float = 1.0,
) -> List[Dict]:
    """Fetch OSM ways for a bbox using multiple Overpass endpoints.

    Tries each URL in order until one returns data; raises on total failure.
    Uses the same fetch function as the main pipeline for consistency.
    """
    prep = _import_prep_module()
    last_err: Exception | None = None
    for url in urls:
        try:
            ways = prep.fetch_osm_ways_bbox(min_lat, min_lon, max_lat, max_lon, url, timeout_s=timeout_s)
            if ways:
                return ways
        except Exception as e:  # pragma: no cover - network variability
            last_err = e
            time.sleep(sleep_s)
            continue
    if last_err:
        raise RuntimeError(f"Overpass failed for all endpoints: {urls}\nlast_err={last_err}")
    raise RuntimeError(f"Overpass returned no data for all endpoints: {urls}")
