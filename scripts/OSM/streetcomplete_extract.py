#!/usr/bin/env python3
"""
Extract StreetComplete contributions from OSM for a given area and date range.

POC pipeline:
1) Query Overpass for elements with accessibility tags modified in date range
2) Collect unique changeset IDs from results
3) Batch-check changesets via OSM API to identify StreetComplete origin
4) Filter and export to GeoJSON + HTML map

No auth required — uses public APIs only.
"""

import json
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests

try:
    import folium
    from folium.plugins import MarkerCluster
except ImportError:
    folium = None

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from constants import TALLINN_BBOX  # noqa: F401,E402 - re-exported for backwards compat

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# overpass servers with fallbacks
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

# accessibility-relevant tags to query
ACCESSIBILITY_TAGS = [
    "surface",
    "smoothness",
    "sidewalk",
    "tactile_paving",
    "kerb",
    "crossing",
    "crossing:markings",
    "handrail",
    "step_count",
    "barrier",
    "incline",
    "wheelchair",
    "width",
]

# quest types we care about
ACCESSIBILITY_QUEST_TYPES = {
    "AddSurface", "AddPathSurface", "AddSmoothness",
    "AddSidewalk", "AddKerbHeight",
    "AddTactilePavingCrossing", "AddTactilePavingBusStop",
    "AddCrossingType", "AddCrossing", "AddCrossingMarkings",
    "AddHandrail", "AddStepCount",
    "AddBarrierType", "AddBarrierOnPath",
    "AddIncline",
    "AddWheelchairAccessBusiness", "AddWheelchairAccessToilets",
    "AddWheelchairAccessOutside",
    "AddRoadWidth", "AddCyclewayWidth",
    "AddRoadSurface", "AddFootwayPartSurface",
}


def overpass_query(query: str) -> dict:
    """run overpass query with fallback servers."""
    for server in OVERPASS_SERVERS:
        try:
            print(f"  trying {server}...")
            resp = requests.post(server, data={"data": query}, timeout=120)
            if resp.status_code == 200:
                return resp.json()
            print(f"  got {resp.status_code}, trying next server")
        except requests.RequestException as e:
            print(f"  failed: {e}")
    raise RuntimeError("all overpass servers failed")


def fetch_modified_elements(date_from: str, date_to: str, bbox: tuple) -> dict:
    """fetch elements with accessibility tags modified in date range."""
    s, w, n, e = bbox
    tag_filters = []
    for tag in ACCESSIBILITY_TAGS:
        tag_filters.append(f'  node["{tag}"](newer:"{date_from}")({s},{w},{n},{e});')
        tag_filters.append(f'  way["{tag}"](newer:"{date_from}")({s},{w},{n},{e});')

    filters_str = "\n".join(tag_filters)
    query = f"""
[out:json][timeout:180];
(
{filters_str}
);
out meta;
>;
out skel qt;
"""
    print(f"querying overpass for elements modified since {date_from}...")
    return overpass_query(query)


def extract_changeset_ids(overpass_data: dict) -> Set[int]:
    """extract unique changeset IDs from overpass results."""
    cs_ids = set()
    for elem in overpass_data.get("elements", []):
        cs_id = elem.get("changeset")
        if cs_id:
            cs_ids.add(cs_id)
    return cs_ids


def fetch_changeset_metadata(cs_ids: Set[int], batch_size: int = 50) -> Dict[int, dict]:
    """fetch changeset metadata from OSM API, filter for StreetComplete."""
    # osm api supports fetching multiple changesets: GET /api/0.6/changesets?changesets=id1,id2,...
    results = {}
    cs_list = sorted(cs_ids)
    total = len(cs_list)
    print(f"checking {total} changesets for StreetComplete origin...")

    for i in range(0, total, batch_size):
        batch = cs_list[i:i + batch_size]
        ids_str = ",".join(str(c) for c in batch)
        url = f"https://api.openstreetmap.org/api/0.6/changesets?changesets={ids_str}"

        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                print(f"  batch {i // batch_size + 1}: HTTP {resp.status_code}")
                time.sleep(2)
                continue

            root = ET.fromstring(resp.text)
            for cs_elem in root.findall("changeset"):
                cs_id = int(cs_elem.get("id"))
                tags = {}
                for tag in cs_elem.findall("tag"):
                    tags[tag.get("k")] = tag.get("v")

                results[cs_id] = {
                    "id": cs_id,
                    "user": cs_elem.get("user"),
                    "uid": cs_elem.get("uid"),
                    "created_at": cs_elem.get("created_at"),
                    "tags": tags,
                    "created_by": tags.get("created_by", ""),
                    "is_streetcomplete": tags.get("created_by", "").startswith("StreetComplete"),
                    "quest_type": tags.get("StreetComplete:quest_type", ""),
                }
        except Exception as e:
            print(f"  batch {i // batch_size + 1}: error {e}")

        progress = min(i + batch_size, total)
        print(f"  checked {progress}/{total} changesets")
        if i + batch_size < total:
            time.sleep(1)  # rate limiting

    return results


def filter_sc_elements(overpass_data: dict, sc_changesets: Dict[int, dict]) -> List[dict]:
    """filter overpass elements to only those from StreetComplete changesets."""
    sc_cs_ids = {cs_id for cs_id, meta in sc_changesets.items() if meta["is_streetcomplete"]}
    filtered = []
    for elem in overpass_data.get("elements", []):
        cs_id = elem.get("changeset")
        if cs_id in sc_cs_ids:
            meta = sc_changesets[cs_id]
            elem["_sc_user"] = meta["user"]
            elem["_sc_quest_type"] = meta["quest_type"]
            elem["_sc_date"] = meta["created_at"]
            filtered.append(elem)
    return filtered


def elements_to_geojson(elements: List[dict]) -> dict:
    """convert filtered elements to GeoJSON FeatureCollection."""
    features = []
    for elem in elements:
        if elem["type"] == "node" and "lat" in elem and "lon" in elem:
            geom = {"type": "Point", "coordinates": [elem["lon"], elem["lat"]]}
        elif elem["type"] == "way":
            # ways need node resolution — skip geometry for now, just record metadata
            continue
        else:
            continue

        props = {
            "osm_type": elem["type"],
            "osm_id": elem["id"],
            "user": elem.get("_sc_user", ""),
            "quest_type": elem.get("_sc_quest_type", ""),
            "date": elem.get("_sc_date", ""),
            "changeset": elem.get("changeset"),
        }
        # include all osm tags
        if "tags" in elem:
            for k, v in elem["tags"].items():
                props[f"tag:{k}"] = v

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}


def build_map(geojson: dict, sc_changesets: Dict[int, dict]) -> Optional[Any]:
    """build folium map of StreetComplete contributions."""
    if folium is None:
        print("folium not installed, skipping map")
        return None

    center = [59.437, 24.745]  # tallinn center
    m = folium.Map(location=center, zoom_start=12, tiles="cartodbpositron")

    # color by quest type category
    quest_colors = {
        "surface": "#e74c3c",
        "sidewalk": "#3498db",
        "crossing": "#2ecc71",
        "kerb": "#f39c12",
        "tactile": "#9b59b6",
        "wheelchair": "#1abc9c",
        "barrier": "#e67e22",
        "steps": "#34495e",
        "other": "#95a5a6",
    }

    def quest_category(qt: str) -> str:
        qt_lower = qt.lower()
        if "surface" in qt_lower or "smoothness" in qt_lower:
            return "surface"
        if "sidewalk" in qt_lower:
            return "sidewalk"
        if "crossing" in qt_lower:
            return "crossing"
        if "kerb" in qt_lower:
            return "kerb"
        if "tactile" in qt_lower:
            return "tactile"
        if "wheelchair" in qt_lower:
            return "wheelchair"
        if "barrier" in qt_lower:
            return "barrier"
        if "step" in qt_lower or "handrail" in qt_lower:
            return "steps"
        return "other"

    cluster = MarkerCluster(name="StreetComplete contributions").add_to(m)

    for feat in geojson["features"]:
        coords = feat["geometry"]["coordinates"]
        props = feat["properties"]
        qt = props.get("quest_type", "unknown")
        cat = quest_category(qt)
        color = quest_colors.get(cat, "#95a5a6")

        # build popup
        tag_lines = [f"<b>{k.replace('tag:', '')}</b>: {v}"
                     for k, v in props.items() if k.startswith("tag:")]
        popup_html = f"""
        <b>Quest:</b> {qt}<br>
        <b>User:</b> {props.get('user', '?')}<br>
        <b>Date:</b> {props.get('date', '?')[:10]}<br>
        <b>OSM:</b> {props['osm_type']}/{props['osm_id']}<br>
        <hr>
        {'<br>'.join(tag_lines)}
        """

        folium.CircleMarker(
            location=[coords[1], coords[0]],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(cluster)

    # add legend
    legend_html = '<div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;padding:10px;border-radius:5px;border:1px solid #ccc;font-size:12px;">'
    legend_html += "<b>Quest categories</b><br>"
    for cat, color in quest_colors.items():
        legend_html += f'<span style="color:{color};">&#9679;</span> {cat}<br>'
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def print_summary(elements: List[dict], sc_changesets: Dict[int, dict]):
    """print summary statistics."""
    sc_only = {k: v for k, v in sc_changesets.items() if v["is_streetcomplete"]}

    print("\n" + "=" * 60)
    print("STREETCOMPLETE EXTRACTION SUMMARY")
    print("=" * 60)

    print(f"\ntotal changesets checked: {len(sc_changesets)}")
    print(f"StreetComplete changesets: {len(sc_only)}")
    print(f"other editor changesets: {len(sc_changesets) - len(sc_only)}")
    print(f"StreetComplete elements (nodes): {len(elements)}")

    # by user
    user_counts = Counter(e.get("_sc_user", "?") for e in elements)
    print(f"\ncontributors ({len(user_counts)}):")
    for user, count in user_counts.most_common(20):
        print(f"  {user}: {count} edits")

    # by quest type
    quest_counts = Counter(e.get("_sc_quest_type", "?") for e in elements)
    print(f"\nquest types ({len(quest_counts)}):")
    for qt, count in quest_counts.most_common(20):
        print(f"  {qt}: {count}")

    # by date
    date_counts = Counter(e.get("_sc_date", "?")[:10] for e in elements)
    print(f"\nby date:")
    for date, count in sorted(date_counts.items()):
        print(f"  {date}: {count}")

    # top accessibility tags found
    tag_counts = Counter()
    for e in elements:
        for k in e.get("tags", {}):
            if k in ACCESSIBILITY_TAGS:
                tag_counts[k] += 1
    print(f"\naccessibility tags found:")
    for tag, count in tag_counts.most_common():
        print(f"  {tag}: {count}")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    date_from = "2025-05-22T00:00:00Z"
    date_to = "2025-05-30T00:00:00Z"

    # step 1: query overpass
    overpass_data = fetch_modified_elements(date_from, date_to, TALLINN_BBOX)
    elements = overpass_data.get("elements", [])
    print(f"overpass returned {len(elements)} elements")

    if not elements:
        print("no elements found, exiting")
        return

    # step 2: collect changeset IDs
    cs_ids = extract_changeset_ids(overpass_data)
    print(f"found {len(cs_ids)} unique changesets")

    # step 3: check changesets for StreetComplete origin
    cs_metadata = fetch_changeset_metadata(cs_ids)

    # step 4: filter elements to SC only
    sc_elements = filter_sc_elements(overpass_data, cs_metadata)

    # step 5: summary
    print_summary(sc_elements, cs_metadata)

    # step 6: export
    geojson = elements_to_geojson(sc_elements)
    geojson_path = OUTPUT_DIR / "streetcomplete_tallinn.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f, indent=2)
    print(f"\nGeoJSON saved: {geojson_path} ({len(geojson['features'])} features)")

    # step 7: map
    m = build_map(geojson, cs_metadata)
    if m:
        map_path = OUTPUT_DIR / "streetcomplete_tallinn.html"
        m.save(str(map_path))
        print(f"map saved: {map_path}")

    # save raw metadata for further analysis
    meta_path = OUTPUT_DIR / "streetcomplete_changesets.json"
    sc_only = {str(k): v for k, v in cs_metadata.items() if v["is_streetcomplete"]}
    with open(meta_path, "w") as f:
        json.dump(sc_only, f, indent=2, default=str)
    print(f"changeset metadata saved: {meta_path}")


if __name__ == "__main__":
    main()
