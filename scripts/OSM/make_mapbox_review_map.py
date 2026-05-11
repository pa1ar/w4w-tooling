#!/usr/bin/env python3
"""
Generate an interactive Mapbox GL JS review map from smoothness proposals.
Replaces Folium with a faster, more customizable web map.
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict

from shapely.geometry import LineString


def proposals_to_geojson(proposals: List[Dict], id_to_geom: Dict[int, LineString]) -> Dict:
    """Convert proposals + geometries to GeoJSON FeatureCollection."""
    features = []
    for prop in proposals:
        way_id = int(prop["way_id"])
        geom = id_to_geom.get(way_id)
        if not geom:
            continue
        coords = [[lon, lat] for lon, lat in geom.coords]

        # Color by proposal status
        proposed = prop.get("proposed_value", "")
        if proposed == "bad":
            color = "#e74c3c"  # red
        elif proposed == "intermediate":
            color = "#f39c12"  # orange
        elif prop.get("existing_smoothness"):
            color = "#95a5a6"  # gray (already tagged)
        else:
            color = "#bdc3c7"  # light gray (skipped)

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "properties": {
                "way_id": way_id,
                "proposed_value": proposed or "skip",
                "coverage_pct": prop.get("coverage_pct", 0),
                "bad_run_m": prop.get("bad_run_m", 0),
                "agree_pct": prop.get("agree_pct", 0),
                "existing_smoothness": prop.get("existing_smoothness", ""),
                "counts": prop.get("counts", "{}"),
                "color": color,
                "comment": prop.get("comment", "")
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


def make_html(geojson: Dict, mapbox_token: str, center_lat: float, center_lon: float) -> str:
    """Generate standalone HTML with Mapbox GL JS."""
    geojson_str = json.dumps(geojson, ensure_ascii=False)

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
<div class="legend">
    <h4>Proposals</h4>
    <div class="legend-item">
        <div class="legend-color" style="background: #e74c3c;"></div>
        <span>Bad (≥30m bad run)</span>
    </div>
    <div class="legend-item">
        <div class="legend-color" style="background: #f39c12;"></div>
        <span>Intermediate (≥70% agree)</span>
    </div>
    <div class="legend-item">
        <div class="legend-color" style="background: #95a5a6;"></div>
        <span>Already tagged</span>
    </div>
    <div class="legend-item">
        <div class="legend-color" style="background: #bdc3c7;"></div>
        <span>Skip (no proposal)</span>
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

const geojson = {geojson_str};

map.on('load', () => {{
    map.addSource('proposals', {{
        type: 'geojson',
        data: geojson
    }});

    map.addLayer({{
        id: 'proposals-lines',
        type: 'line',
        source: 'proposals',
        paint: {{
            'line-color': ['get', 'color'],
            'line-width': 4,
            'line-opacity': 0.8
        }}
    }});

    // Popup on click
    map.on('click', 'proposals-lines', (e) => {{
        const props = e.features[0].properties;
        const way_id = props.way_id;
        const osmLink = `https://www.openstreetmap.org/way/${{way_id}}`;

        let html = `<h3>Way ${{way_id}}</h3>`;
        html += `<p><strong>Proposed:</strong> ${{props.proposed_value}}</p>`;
        html += `<p><strong>Existing:</strong> ${{props.existing_smoothness || 'none'}}</p>`;
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

    // Cursor pointer on hover
    map.on('mouseenter', 'proposals-lines', () => {{
        map.getCanvas().style.cursor = 'pointer';
    }});
    map.on('mouseleave', 'proposals-lines', () => {{
        map.getCanvas().style.cursor = '';
    }});
}});
</script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate Mapbox review map from proposals")
    parser.add_argument("--proposals-geojson", required=True, help="GeoJSON with proposals + geometries")
    parser.add_argument("--mapbox-token", help="Mapbox access token (or use env MAPBOX_ACCESS_TOKEN)")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    import os
    token = args.mapbox_token or os.getenv("MAPBOX_ACCESS_TOKEN")
    if not token:
        print("Error: MAPBOX_ACCESS_TOKEN required")
        return 1

    # Load GeoJSON
    with open(args.proposals_geojson) as f:
        geojson = json.load(f)

    # Compute center
    all_coords = []
    for feat in geojson.get("features", []):
        coords = feat["geometry"]["coordinates"]
        all_coords.extend(coords)
    if not all_coords:
        center_lat, center_lon = 0, 0
    else:
        center_lon = sum(c[0] for c in all_coords) / len(all_coords)
        center_lat = sum(c[1] for c in all_coords) / len(all_coords)

    html = make_html(geojson, token, center_lat, center_lon)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote Mapbox review map: {out_path}")


if __name__ == "__main__":
    main()
