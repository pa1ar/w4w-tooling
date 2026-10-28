#!/usr/bin/env python3
"""Tallinn coverage estimate and way-level smoothness candidates.

Reads the classified ride sections from the local W4W website checkout and an
OSM highway snapshot. Outputs stay under gitignored output/tallinn-coverage.
This script does not upload telemetry or edit OpenStreetMap.

A ride counts as evidence for a way only when its own sections cover at least
MIN_RIDE_COVERAGE of that way. Rides that only graze a way are ignored, so the
two-ride publication threshold means two rides that actually rode it.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import folium
import requests
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "tallinn-coverage"
SITE_DATA = ROOT.parent / "w4w" / "public" / "data"

DISTRICTS_URL = (
    "https://gis.tallinn.ee/arcgis/rest/services/"
    "Linnaosad_asumid/FeatureServer/1/query"
    "?where=1%3D1&outFields=*&f=geojson&outSR=4326"
)
NEIGHBORHOODS_URL = (
    "https://gis.tallinn.ee/arcgis/rest/services/"
    "Linnaosad_asumid/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=geojson&outSR=4326"
)

MIN_RIDE_COVERAGE = 0.10

CLASSES = ["excellent", "good", "intermediate", "bad", "very_bad"]
ELIGIBLE_HIGHWAYS = {
    "cycleway",
    "footway",
    "living_street",
    "path",
    "pedestrian",
    "primary",
    "residential",
    "road",
    "secondary",
    "service",
    "tertiary",
    "track",
    "unclassified",
}

TO_METERS = Transformer.from_crs(4326, 3301, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(3301, 4326, always_xy=True).transform


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fetch_geojson(url: str, path: Path) -> dict[str, Any]:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    value = response.json()
    write_json(path, value)
    return value


def line_from_feature(feature: dict[str, Any]) -> LineString | None:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") != "LineString" or len(coordinates) < 2:
        return None
    try:
        line = LineString(coordinates)
    except Exception:
        return None
    return line if not line.is_empty and line.length > 0 else None


def metric_shape(feature: dict[str, Any]):
    return transform(TO_METERS, shape(feature["geometry"]))


def district_name(properties: dict[str, Any]) -> str:
    return properties["animi"]


def neighborhood_name(properties: dict[str, Any]) -> str:
    return properties["asumi_nimi"]


def classify_area(point: Point, areas: list[dict[str, Any]]) -> str | None:
    for area in areas:
        if area["geom_m"].covers(point):
            return area["name"]
    return None


def explode_lines(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    if geometry.geom_type == "MultiLineString":
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        return [g for g in geometry.geoms if g.geom_type == "LineString"]
    return []


def build_area_rows(
    areas: list[dict[str, Any]],
    rides_by_area: dict[str, set[str]],
    sections_by_area: Counter,
    trace_by_area_class: dict[str, Counter],
) -> list[dict[str, Any]]:
    rows = []
    for area in areas:
        name = area["name"]
        by_class = trace_by_area_class[name]
        trace_m = sum(by_class.values())
        row = {
            "name": name,
            "parent_district": area.get("parent_district"),
            "area_km2": round(area["geom_m"].area / 1_000_000, 3),
            "rides_touched": len(rides_by_area[name]),
            "classified_sections": sections_by_area[name],
            "trace_km": round(trace_m / 1000, 3),
        }
        for class_name in CLASSES:
            row[f"{class_name}_km"] = round(by_class[class_name] / 1000, 3)
            row[f"{class_name}_pct"] = (
                round(100 * by_class[class_name] / trace_m, 1) if trace_m else 0.0
            )
        rows.append(row)
    return sorted(rows, key=lambda row: row["name"])


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evidence_for_ways(
    way_geometries: list,
    way_records: list[dict[str, Any]],
    trace_records: list[dict[str, Any]],
    max_distance_m: float,
    buffer_m: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tree = STRtree(way_geometries)
    trace_geometries = [record["geom_m"] for record in trace_records]
    indices, distances = tree.query_nearest(
        trace_geometries,
        max_distance=max_distance_m,
        all_matches=False,
        return_distance=True,
    )

    by_way: dict[int, list[int]] = defaultdict(list)
    distance_by_trace: dict[int, float] = {}
    for trace_index, way_index, distance in zip(indices[0], indices[1], distances):
        by_way[int(way_index)].append(int(trace_index))
        distance_by_trace[int(trace_index)] = float(distance)

    results = []
    for way_index, trace_indexes in by_way.items():
        way = way_records[way_index]
        way_geom = way_geometries[way_index]
        by_ride: dict[str, list[int]] = defaultdict(list)
        for trace_index in trace_indexes:
            by_ride[trace_records[trace_index]["ride_id"]].append(trace_index)
        trace_indexes = [
            trace_index
            for group in by_ride.values()
            if way["length_m"]
            and way_geom.intersection(
                unary_union([trace_records[i]["geom_m"].buffer(buffer_m) for i in group])
            ).length
            / way["length_m"]
            >= MIN_RIDE_COVERAGE
            for trace_index in group
        ]
        if not trace_indexes:
            continue
        class_lengths = Counter()
        rides = set()
        evidence_geometries = []
        bad_geometries = []
        match_distances = []

        for trace_index in trace_indexes:
            trace = trace_records[trace_index]
            weight = trace["length_m"]
            class_lengths[trace["class_name"]] += weight
            rides.add(trace["ride_id"])
            evidence_geometries.append(trace["geom_m"].buffer(buffer_m))
            if trace["class_name"] in {"bad", "very_bad"}:
                bad_geometries.append(trace["geom_m"].buffer(buffer_m))
            match_distances.append(distance_by_trace[trace_index])

        evidence_union = unary_union(evidence_geometries)
        covered_geometry = way_geom.intersection(evidence_union)
        covered_m = covered_geometry.length
        coverage = min(1.0, covered_m / way["length_m"]) if way["length_m"] else 0.0
        total_evidence_m = sum(class_lengths.values())
        dominant_class, dominant_m = class_lengths.most_common(1)[0]
        dominant_share = dominant_m / total_evidence_m if total_evidence_m else 0.0
        non_bad_share = (
            sum(class_lengths[name] for name in ["excellent", "good", "intermediate"])
            / total_evidence_m
            if total_evidence_m
            else 0.0
        )

        bad_run_m = 0.0
        if bad_geometries:
            bad_covered = way_geom.intersection(unary_union(bad_geometries))
            bad_run_m = max((part.length for part in explode_lines(bad_covered)), default=0.0)

        proposed_value = None
        if bad_run_m >= 30:
            proposed_value = "bad"
        elif non_bad_share >= 0.70:
            proposed_value = "intermediate"

        record = {
            **way,
            "coverage": coverage,
            "covered_m": covered_m,
            "rides": len(rides),
            "dominant_class": dominant_class,
            "dominant_share": dominant_share,
            "non_bad_share": non_bad_share,
            "bad_run_m": bad_run_m,
            "proposed_value": proposed_value,
            "mean_match_distance_m": sum(match_distances) / len(match_distances),
            "class_lengths_m": dict(class_lengths),
        }
        record["potential"] = (
            not way["existing_smoothness"]
            and coverage >= 0.30
            and proposed_value is not None
        )
        record["conservative"] = (
            not way["existing_smoothness"]
            and coverage >= 0.70
            and len(rides) >= 2
            and proposed_value is not None
        )
        results.append(record)

    audit = {
        "trace_geometries": len(trace_geometries),
        "matched_trace_geometries": len(distance_by_trace),
        "matched_pct": round(100 * len(distance_by_trace) / len(trace_geometries), 1),
        "ways_with_evidence": len(by_way),
        "max_distance_m": max_distance_m,
        "buffer_m": buffer_m,
    }
    return results, audit


def way_scope_summary(records: list[dict[str, Any]], key: str | None = None) -> dict[str, Any]:
    selected = records if key is None else [record for record in records if record[key]]
    return {
        "ways": len(selected),
        "network_km": round(sum(record["length_m"] for record in selected) / 1000, 3),
        "observed_km": round(sum(record["covered_m"] for record in selected) / 1000, 3),
        "by_proposal": dict(Counter(record["proposed_value"] for record in selected)),
    }


def district_candidate_rows(
    districts: list[dict[str, Any]],
    way_evidence: list[dict[str, Any]],
    network_ways: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for district in districts:
        geom = district["geom_m"]
        all_network = []
        tagged = []
        footprint = []
        potential = []
        conservative = []
        for way in network_ways:
            length = way["geom_m"].intersection(geom).length
            if length <= 0:
                continue
            all_network.append((way["way_id"], length))
            if way["existing_smoothness"]:
                tagged.append((way["way_id"], length))
        for way in way_evidence:
            length = way["geom_m"].intersection(geom).length
            if length <= 0:
                continue
            if not way["existing_smoothness"]:
                footprint.append((way["way_id"], length))
            if way["potential"]:
                potential.append((way["way_id"], length))
            if way["conservative"]:
                conservative.append((way["way_id"], length))

        network_m = sum(length for _, length in all_network)
        tagged_m = sum(length for _, length in tagged)
        potential_m = sum(length for _, length in potential)
        conservative_m = sum(length for _, length in conservative)
        rows.append(
            {
                "district": district["name"],
                "network_km": round(network_m / 1000, 3),
                "currently_tagged_km": round(tagged_m / 1000, 3),
                "current_tagged_pct": round(100 * tagged_m / network_m, 2) if network_m else 0,
                "missing_smoothness_ways_touched": len({way_id for way_id, _ in footprint}),
                "potential_ways": len({way_id for way_id, _ in potential}),
                "potential_km": round(potential_m / 1000, 3),
                "potential_after_pct": round(100 * (tagged_m + potential_m) / network_m, 2)
                if network_m
                else 0,
                "conservative_ways": len({way_id for way_id, _ in conservative}),
                "conservative_km": round(conservative_m / 1000, 3),
                "conservative_after_pct": round(
                    100 * (tagged_m + conservative_m) / network_m, 2
                )
                if network_m
                else 0,
            }
        )
    return sorted(rows, key=lambda row: row["district"])


def add_map(
    districts_geojson: dict[str, Any],
    district_rows: list[dict[str, Any]],
    way_evidence: list[dict[str, Any]],
) -> None:
    district_lookup = {row["district"]: row for row in district_rows}
    geojson = json.loads(json.dumps(districts_geojson))
    for feature in geojson["features"]:
        name = district_name(feature["properties"])
        feature["properties"].update(district_lookup[name])

    map_view = folium.Map(location=[59.435, 24.75], zoom_start=11, tiles="OpenStreetMap")
    folium.GeoJson(
        geojson,
        name="Tallinn districts",
        style_function=lambda feature: {
            "color": "#46544d",
            "weight": 1.5,
            "fillColor": "#1f6b4f" if feature["properties"]["conservative_ways"] else "#303a35",
            "fillOpacity": 0.18,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "district",
                "missing_smoothness_ways_touched",
                "potential_ways",
                "conservative_ways",
                "conservative_km",
            ],
            aliases=[
                "District",
                "Missing-tag ways touched",
                "Potential ways",
                "Conservative ways",
                "Conservative network km",
            ],
        ),
    ).add_to(map_view)

    potential_group = folium.FeatureGroup(name="Potential estimate", show=False)
    conservative_group = folium.FeatureGroup(name="Conservative estimate", show=True)
    for record in way_evidence:
        if not record["potential"]:
            continue
        coordinates = [
            [[lat, lon] for lon, lat in transform(TO_WGS84, part).coords]
            for part in explode_lines(record["geom_m"])
        ]
        target = conservative_group if record["conservative"] else potential_group
        color = "#ff43e6" if record["conservative"] else "#f2b84b"
        for coordinate_list in coordinates:
            folium.PolyLine(
                coordinate_list,
                color=color,
                weight=4 if record["conservative"] else 2,
                opacity=0.85,
                tooltip=(
                    f"OSM way {record['way_id']} | {record['proposed_value']} | "
                    f"coverage {record['coverage']:.0%} | rides {record['rides']}"
                ),
            ).add_to(target)
    potential_group.add_to(map_view)
    conservative_group.add_to(map_view)
    folium.LayerControl(collapsed=False).add_to(map_view)
    map_view.save(OUT / "coverage-map.html")


def render_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(str(row[column]) for column in columns) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    districts_geojson = fetch_geojson(DISTRICTS_URL, OUT / "districts.geojson")
    neighborhoods_geojson = fetch_geojson(NEIGHBORHOODS_URL, OUT / "neighborhoods.geojson")

    districts = [
        {
            "name": district_name(feature["properties"]),
            "geom_m": metric_shape(feature),
        }
        for feature in districts_geojson["features"]
    ]
    neighborhoods = [
        {
            "name": neighborhood_name(feature["properties"]),
            "parent_district": feature["properties"]["linnaosa_lyhinimi"],
            "geom_m": metric_shape(feature),
        }
        for feature in neighborhoods_geojson["features"]
    ]
    tallinn = unary_union([district["geom_m"] for district in districts])

    colored = read_json(SITE_DATA / "gps_paths_colored.json")
    trace_records = []
    sections_by_district = Counter()
    sections_by_neighborhood = Counter()
    rides_by_district: dict[str, set[str]] = defaultdict(set)
    rides_by_neighborhood: dict[str, set[str]] = defaultdict(set)
    trace_by_district_class: dict[str, Counter] = defaultdict(Counter)
    trace_by_neighborhood_class: dict[str, Counter] = defaultdict(Counter)
    single_point_sections = 0
    unknown_sections = 0
    total_non_primary = 0
    ride_ids_seen = set()
    section_classes = Counter()

    for feature in colored["features"]:
        properties = feature.get("properties") or {}
        if properties.get("primary") is True:
            continue
        total_non_primary += 1
        class_name = properties.get("cls")
        if class_name not in CLASSES:
            unknown_sections += 1
            continue
        ride_id = f"{properties['source_file']}::{properties['path_id']}"
        ride_ids_seen.add(ride_id)
        section_classes[class_name] += 1
        coordinates = feature["geometry"].get("coordinates") or []
        if not coordinates:
            continue

        if len(coordinates) == 1:
            single_point_sections += 1
            point = transform(TO_METERS, Point(coordinates[0]))
            district = classify_area(point, districts)
            neighborhood = classify_area(point, neighborhoods)
            if district:
                sections_by_district[district] += 1
                rides_by_district[district].add(ride_id)
            if neighborhood:
                sections_by_neighborhood[neighborhood] += 1
                rides_by_neighborhood[neighborhood].add(ride_id)
            continue

        line = line_from_feature(feature)
        if line is None:
            continue
        line_m = transform(TO_METERS, line)
        midpoint = line_m.interpolate(0.5, normalized=True)
        district = classify_area(midpoint, districts)
        neighborhood = classify_area(midpoint, neighborhoods)
        if district:
            sections_by_district[district] += 1
        if neighborhood:
            sections_by_neighborhood[neighborhood] += 1

        for area in districts:
            intersection_length = line_m.intersection(area["geom_m"]).length
            if intersection_length > 0:
                rides_by_district[area["name"]].add(ride_id)
                trace_by_district_class[area["name"]][class_name] += intersection_length
        for area in neighborhoods:
            if not line_m.envelope.intersects(area["geom_m"].envelope):
                continue
            intersection_length = line_m.intersection(area["geom_m"]).length
            if intersection_length > 0:
                rides_by_neighborhood[area["name"]].add(ride_id)
                trace_by_neighborhood_class[area["name"]][class_name] += intersection_length

        trace_records.append(
            {
                "ride_id": ride_id,
                "class_name": class_name,
                "geom_m": line_m,
                "length_m": line_m.length,
            }
        )

    district_rows = build_area_rows(
        districts, rides_by_district, sections_by_district, trace_by_district_class
    )
    neighborhood_rows = build_area_rows(
        neighborhoods,
        rides_by_neighborhood,
        sections_by_neighborhood,
        trace_by_neighborhood_class,
    )
    write_csv(OUT / "district-ride-coverage.csv", district_rows)
    write_csv(OUT / "neighborhood-ride-coverage.csv", neighborhood_rows)

    osm = read_json(OUT / "osm-highways.json")
    network_ways = []
    for element in osm.get("elements", []):
        tags = element.get("tags") or {}
        if tags.get("highway") not in ELIGIBLE_HIGHWAYS:
            continue
        coordinates = [
            [point["lon"], point["lat"]]
            for point in element.get("geometry", [])
            if "lon" in point and "lat" in point
        ]
        if len(coordinates) < 2:
            continue
        line_m = transform(TO_METERS, LineString(coordinates))
        clipped = line_m.intersection(tallinn)
        clipped_lines = explode_lines(clipped)
        if not clipped_lines:
            continue
        geom_m = unary_union(clipped_lines)
        length_m = geom_m.length
        if length_m <= 0:
            continue
        network_ways.append(
            {
                "way_id": int(element["id"]),
                "highway": tags.get("highway"),
                "existing_smoothness": tags.get("smoothness"),
                "length_m": length_m,
                "geom_m": geom_m,
            }
        )

    network_geometries = [record["geom_m"] for record in network_ways]
    way_evidence, match_audit = evidence_for_ways(
        network_geometries,
        network_ways,
        trace_records,
        max_distance_m=8,
        buffer_m=8,
    )
    loose_evidence, loose_match_audit = evidence_for_ways(
        network_geometries,
        network_ways,
        trace_records,
        max_distance_m=15,
        buffer_m=15,
    )

    known_geojson = read_json(SITE_DATA / "osm_smoothness_proposal_ways.geojson")
    known_rides = {
        f"{feature['properties']['source_file']}::{feature['properties']['path_id']}"
        for feature in known_geojson["features"]
    }
    rides_with_line_geometry = {record["ride_id"] for record in trace_records}
    known_analysis_rides = known_rides & rides_with_line_geometry
    known_way_ids = {
        int(feature["properties"]["way_id"])
        for feature in known_geojson["features"]
        if feature.get("properties", {}).get("way_id") is not None
        and (
            f"{feature['properties']['source_file']}::{feature['properties']['path_id']}"
            in known_analysis_rides
        )
    }
    # Re-run the validation as a cheap ride-filtered nearest query.
    validation_traces = [
        record for record in trace_records if record["ride_id"] in known_analysis_rides
    ]
    validation_records, _ = evidence_for_ways(
        network_geometries,
        network_ways,
        validation_traces,
        max_distance_m=8,
        buffer_m=8,
    )
    strict_known_matches = {record["way_id"] for record in validation_records}
    known_in_network = known_way_ids & {record["way_id"] for record in network_ways}
    recovered_known = known_in_network & strict_known_matches

    district_candidate = district_candidate_rows(districts, way_evidence, network_ways)
    write_csv(OUT / "district-osm-estimate.csv", district_candidate)

    candidate_rows = []
    for record in sorted(way_evidence, key=lambda item: item["way_id"]):
        if record["existing_smoothness"] and not record["potential"]:
            continue
        candidate_rows.append(
            {
                "way_id": record["way_id"],
                "highway": record["highway"],
                "existing_smoothness": record["existing_smoothness"] or "",
                "length_m": round(record["length_m"], 1),
                "covered_m": round(record["covered_m"], 1),
                "coverage_pct": round(100 * record["coverage"], 1),
                "rides": record["rides"],
                "dominant_class": record["dominant_class"],
                "dominant_share_pct": round(100 * record["dominant_share"], 1),
                "bad_run_m": round(record["bad_run_m"], 1),
                "proposed_value": record["proposed_value"] or "",
                "potential": record["potential"],
                "conservative": record["conservative"],
                "mean_match_distance_m": round(record["mean_match_distance_m"], 2),
            }
        )
    write_csv(OUT / "osm-way-estimates.csv", candidate_rows)

    network_length_m = sum(record["length_m"] for record in network_ways)
    tagged_records = [record for record in network_ways if record["existing_smoothness"]]
    tagged_length_m = sum(record["length_m"] for record in tagged_records)
    potential_records = [record for record in way_evidence if record["potential"]]
    conservative_records = [record for record in way_evidence if record["conservative"]]

    summary = {
        "sources": {
            "classified_rides": str(SITE_DATA / "gps_paths_colored.json"),
            "ride_stats": str(SITE_DATA / "ride_stats.json"),
            "official_districts": DISTRICTS_URL,
            "official_neighborhoods": NEIGHBORHOODS_URL,
            "osm_highways": "Overpass snapshot stored at output/tallinn-coverage/osm-highways.json",
        },
        "dataset": {
            "non_primary_features": total_non_primary,
            "classified_sections": total_non_primary - unknown_sections,
            "unknown_sections_excluded": unknown_sections,
            "single_point_sections_excluded_from_distance_and_osm_matching": single_point_sections,
            "valid_line_sections": len(trace_records),
            "unique_rides_represented": len(ride_ids_seen),
            "unique_rides_with_line_geometry": len(rides_with_line_geometry),
            "class_counts": dict(section_classes),
            "classified_trace_km": round(
                sum(record["length_m"] for record in trace_records) / 1000, 3
            ),
            "districts_touched": sum(row["rides_touched"] > 0 for row in district_rows),
            "neighborhoods_touched": sum(row["rides_touched"] > 0 for row in neighborhood_rows),
        },
        "osm_network_scope": {
            "snapshot_time": osm.get("osm3s", {}).get("timestamp_osm_base"),
            "eligible_highway_types": sorted(ELIGIBLE_HIGHWAYS),
            "ways": len(network_ways),
            "network_km": round(network_length_m / 1000, 3),
            "currently_smoothness_tagged_ways": len(tagged_records),
            "currently_smoothness_tagged_km": round(tagged_length_m / 1000, 3),
            "currently_smoothness_tagged_pct": round(100 * tagged_length_m / network_length_m, 2),
        },
        "matching": {
            "strict": match_audit,
            "loose_sensitivity": loose_match_audit,
            "known_pipeline_way_validation": {
                "pipeline_rides_available_for_validation": len(known_analysis_rides),
                "known_way_ids_in_eligible_network": len(known_in_network),
                "recovered_by_8m_spatial_match": len(recovered_known),
                "recovery_pct": round(100 * len(recovered_known) / len(known_in_network), 1)
                if known_in_network
                else None,
            },
        },
        "estimates": {
            "missing_tag_footprint": way_scope_summary(
                [record for record in way_evidence if not record["existing_smoothness"]]
            ),
            "potential_30pct_one_ride": way_scope_summary(way_evidence, "potential"),
            "conservative_70pct_two_rides": way_scope_summary(way_evidence, "conservative"),
            "loose_15m_sensitivity_potential": way_scope_summary(loose_evidence, "potential"),
            "loose_15m_sensitivity_conservative": way_scope_summary(loose_evidence, "conservative"),
        },
        "citywide_coverage_change": {
            "baseline_pct": round(100 * tagged_length_m / network_length_m, 2),
            "potential_after_pct": round(
                100
                * (tagged_length_m + sum(record["length_m"] for record in potential_records))
                / network_length_m,
                2,
            ),
            "conservative_after_pct": round(
                100
                * (tagged_length_m + sum(record["length_m"] for record in conservative_records))
                / network_length_m,
                2,
            ),
        },
    }
    write_json(OUT / "coverage-summary.json", summary)

    add_map(districts_geojson, district_candidate, way_evidence)

    touched_districts = [row for row in district_rows if row["rides_touched"]]
    touched_neighborhoods = [row for row in neighborhood_rows if row["rides_touched"]]
    neighborhoods_by_district: dict[str, list[str]] = defaultdict(list)
    for row in touched_neighborhoods:
        neighborhoods_by_district[row["parent_district"]].append(row["name"])
    neighborhood_lines = "\n".join(
        f"- **{district}:** {', '.join(sorted(names))}"
        for district, names in sorted(neighborhoods_by_district.items())
    )
    untouched_by_district: dict[str, list[str]] = defaultdict(list)
    for row in neighborhood_rows:
        if not row["rides_touched"]:
            untouched_by_district[row["parent_district"]].append(row["name"])
    untouched_lines = "\n".join(
        f"- **{district}:** {', '.join(sorted(names))}"
        for district, names in sorted(untouched_by_district.items())
    )
    report = f"""# Tallinn coverage estimate

Generated locally from W4W classified ride geometry, Tallinn's official GIS boundaries,
and a current OpenStreetMap highway snapshot. No data was uploaded and no OSM edits were made.

The OSM snapshot is from {summary['osm_network_scope']['snapshot_time']}.

## Dataset checks

- {summary['dataset']['unique_rides_represented']} rides are represented by classified sections; {summary['dataset']['unique_rides_with_line_geometry']} have usable line geometry for distance and OSM matching.
- {summary['dataset']['classified_sections']:,} classified sections are present.
- {summary['dataset']['classified_trace_km']:.1f} km of classified trace geometry is measurable.
- {summary['dataset']['single_point_sections_excluded_from_distance_and_osm_matching']:,} single-point sections are retained in section counts but cannot contribute to distance or OSM matching.
- The 8 m spatial matcher recovers {summary['matching']['known_pipeline_way_validation']['recovery_pct']}% of the known pipeline OSM ways from the two processed rides available in this analysis set. The OSM estimate is therefore directional, not upload-ready.

## Official Tallinn districts touched by rides

{render_table(touched_districts, ['name', 'rides_touched', 'classified_sections', 'trace_km'])}

## District-level OSM improvement estimate

{render_table(district_candidate, ['district', 'current_tagged_pct', 'missing_smoothness_ways_touched', 'potential_ways', 'conservative_ways', 'conservative_km', 'conservative_after_pct'])}

## Citywide estimate

- Current `smoothness=*` coverage in the scoped OSM network: {summary['citywide_coverage_change']['baseline_pct']}%.
- Raw spatial footprint: {summary['estimates']['missing_tag_footprint']['ways']} currently untagged ways / {summary['estimates']['missing_tag_footprint']['network_km']} network km touched by some classified evidence. This is not an upload candidate count.
- Broad upper estimate, using at least 30% spatial coverage and one ride: {summary['estimates']['potential_30pct_one_ride']['ways']} ways / {summary['estimates']['potential_30pct_one_ride']['network_km']} network km, raising coverage to {summary['citywide_coverage_change']['potential_after_pct']}% if every candidate survived the real pipeline and manual review.
- Conservative research estimate, using at least 70% spatial coverage, at least two rides that each cover at least 10% of the way, and the current intermediate/bad proposal policy: {summary['estimates']['conservative_70pct_two_rides']['ways']} ways / {summary['estimates']['conservative_70pct_two_rides']['network_km']} network km. This splits into {summary['estimates']['conservative_70pct_two_rides']['by_proposal']['intermediate']} intermediate proposals and {summary['estimates']['conservative_70pct_two_rides']['by_proposal']['bad']} bad proposals, raising coverage to {summary['citywide_coverage_change']['conservative_after_pct']}%.
- A looser 15 m rematching tolerance produces {summary['estimates']['loose_15m_sensitivity_conservative']['ways']} conservative candidates / {summary['estimates']['loose_15m_sensitivity_conservative']['network_km']} km. This sensitivity is another reason not to call the estimate upload-ready.

## Neighborhood localization

The official layer contains {len(neighborhoods)} neighborhoods. Rides touch {len(touched_neighborhoods)} of them.

{neighborhood_lines}

The 24 neighborhoods without ride coverage are:

{untouched_lines}

See `neighborhood-ride-coverage.csv` for the complete list.

## Interpretation limits

- Ride traces were spatially rematched to the nearest eligible OSM way. The original Mapbox-snapped points and raw telemetry are not available locally for all rides.
- Parallel roads, cycleways, and footways can be confused by nearest-way matching.
- The conservative count is a research estimate. It still requires the production pipeline, current OSM conflict checks, and human review before upload.
- Coverage percentage is measured against selected OSM highway categories, not every sidewalk or every wheelchair-relevant feature in Tallinn.
- The percentage change measures OSM `smoothness` data completeness. It does not mean Tallinn becomes physically more accessible by the same percentage or guarantee that routing applications will use every added tag.
"""
    (OUT / "README.md").write_text(report)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
