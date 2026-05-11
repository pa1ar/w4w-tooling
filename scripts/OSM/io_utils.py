from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    cur = start
    for _ in range(6):
        if (cur / ".env").exists() and (cur / "scripts").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start


def load_env(require: List[str] | None = None) -> Dict[str, str]:
    """Load .env from repository root and ensure required keys exist."""
    root = find_repo_root(Path.cwd())
    load_dotenv(root / ".env")
    env: Dict[str, str] = {}
    for k, v in os.environ.items():
        env[k] = v
    if require:
        missing = [k for k in require if not env.get(k)]
        if missing:
            raise RuntimeError(f"Missing required env: {missing}")
    return env


def write_proposals_csv(proposals: List[Dict], out_csv: Path) -> None:
    import csv

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "way_id",
                "proposed_value",
                "coverage_pct",
                "bad_run_m",
                "agree_pct",
                "existing_smoothness",
                "counts",
                "confidence_wheelchair",
                "predicted_way_class",
                "osm_match",
                "osm_match_pct",
                "comment",
            ],
        )
        writer.writeheader()
        for p in proposals:
            writer.writerow(p)


def write_review_map(
    proposals: List[Dict],
    id_to_geom: Dict[int, object],
    out_html: Path,
    raw_path_coords: list[tuple[float, float]] | None = None,
) -> None:
    """Delegate to prep.make_map to generate Mapbox GL HTML (with optional raw path)."""
    import importlib.util

    scripts_dir = Path(__file__).resolve().parent
    prep_path = scripts_dir / "prepare_smoothness_from_ride.py"
    spec = importlib.util.spec_from_file_location("prep", prep_path)
    prep = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(prep)  # type: ignore[attr-defined]
    # Apply calibrated thresholds if available so path coloring uses calibrated classes
    try:
        cal_path = find_repo_root(Path.cwd()) / 'output' / 'calibrated_thresholds.json'
        if cal_path.exists():
            import json as _json
            data = _json.loads(cal_path.read_text(encoding='utf-8'))
            ex = float(data.get('excellent_max', 60.0))
            gd = float(data.get('good_max', 110.0))
            it = float(data.get('intermediate_max', 180.0))
            prep.set_classification_thresholds(ex, gd, it)
    except Exception:
        pass
    prep.make_map(proposals, id_to_geom, out_html, raw_path_coords=raw_path_coords)


def write_proposals_geojson(
    proposals: List[Dict],
    id_to_geom: Dict[int, object],
    out_geojson: Path,
    *,
    source_file: str,
    path_id: int | None = None,
) -> None:
    """Write proposals + geometries to a GeoJSON FeatureCollection."""
    from shapely.geometry import mapping  # type: ignore

    def _geometry_to_feature(way_id: int, props: Dict, geom_obj: object) -> Dict:
        if geom_obj is None:
            raise ValueError(f"Missing geometry for way_id={way_id}")
        try:
            geometry = mapping(geom_obj)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - fallback for unexpected geom types
            coords = getattr(geom_obj, "coords", None)
            if coords is None:
                raise exc
            geometry = {
                "type": "LineString",
                "coordinates": [[float(x), float(y)] for x, y in coords],
            }
        return {
            "type": "Feature",
            "geometry": geometry,
            "properties": props,
        }

    features: List[Dict] = []
    for proposal in proposals:
        way_id = int(proposal.get("way_id", 0) or 0)
        geom = id_to_geom.get(way_id)
        if not geom:
            continue
        properties = {
            "way_id": way_id,
            "source_file": source_file,
            "path_id": path_id,
            "proposed_value": proposal.get("proposed_value"),
            "existing_smoothness": proposal.get("existing_smoothness"),
            "coverage_pct": proposal.get("coverage_pct"),
            "agree_pct": proposal.get("agree_pct"),
            "bad_run_m": proposal.get("bad_run_m"),
            "confidence_wheelchair": proposal.get("confidence_wheelchair"),
            "counts": proposal.get("counts", {}),
        }
        features.append(_geometry_to_feature(way_id, properties, geom))

    out_geojson.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": features}
    out_geojson.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
