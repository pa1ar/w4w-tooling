#!/usr/bin/env python3
"""
Plotting utilities reused by the notebook and CLI.
Provides:
- plot_raw_map_plotly(df, mapbox_token) -> plotly.Figure
- plot_smoothness_panels(df) -> matplotlib Figure

Expected df columns: lat, lon, z_std_mg (optional), smoothness_point (categorical)
"""

from typing import Optional, Dict, List, Tuple
from pathlib import Path

import pandas as pd

def plot_raw_map_plotly(df: pd.DataFrame, mapbox_token: str):
    import plotly.express as px
    import plotly.graph_objects as go
    import os
    os.environ["MAPBOX_ACCESS_TOKEN"] = mapbox_token

    fig = px.line_mapbox(
        df.dropna(subset=["lat", "lon"]),
        lat="lat",
        lon="lon",
        zoom=14,
        height=500,
    )
    fig.update_layout(
        mapbox_style="streets",
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def plot_smoothness_panels(df: pd.DataFrame, calibrated_thresholds: dict | None = None):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=False)

    # Top: raw z proxy (use z_std_mg if available else zeros)
    z = df.get("z_std_mg")
    if z is None:
        z = pd.Series([0] * len(df))
    axes[0].plot(z.values, color='tab:blue', linewidth=0.8)
    axes[0].set_title('Raw z-axis proxy (z_std_mg)')
    axes[0].set_ylabel('mg')

    # Middle: smoothed (if present)
    z_s = df.get("z_std_smooth")
    if z_s is not None:
        axes[1].plot(z_s.values, color='tab:orange', linewidth=0.8)
    else:
        axes[1].plot(z.values, color='tab:orange', linewidth=0.8)
    axes[1].set_title('Smoothed (rolling) z')
    axes[1].set_ylabel('mg')

    # Overlay calibrated threshold bands if provided
    if calibrated_thresholds:
        try:
            import numpy as np
            n = len(z_s) if z_s is not None else len(z)
            xs = np.arange(n)
            t1 = float(calibrated_thresholds.get('excellent_max'))
            t2 = float(calibrated_thresholds.get('good_max'))
            t3 = float(calibrated_thresholds.get('intermediate_max'))
            # draw horizontal bands
            axes[1].axhspan(0, t1, color='#e8f5e9', alpha=0.4, label='excellent')
            axes[1].axhspan(t1, t2, color='#e3f2fd', alpha=0.3, label='good')
            axes[1].axhspan(t2, t3, color='#fff3e0', alpha=0.3, label='intermediate')
            axes[1].axhspan(t3, max((z_s.max() if z_s is not None else z.max()) * 1.1, t3 + 50), color='#ffebee', alpha=0.25, label='bad')
            axes[1].legend(loc='upper right', frameon=False)
        except Exception:
            pass

    # Bottom: categorical smoothness levels
    levels = [
        "excellent","good","intermediate","bad","very_bad","horrible","very_horrible","impassable"
    ]
    level_to_num = {lvl: i for i, lvl in enumerate(levels)}
    if "smoothness_point" in df.columns:
        smooth = df["smoothness_point"]
    elif "smoothness" in df.columns:
        smooth = df["smoothness"]
    else:
        smooth = pd.Series(["intermediate"] * len(df))
    # Do not show NA (stationary) points; previously these appeared as 'intermediate'
    mask = smooth.notna()
    idx = smooth[mask].index.to_numpy()
    y = [level_to_num.get(str(v)) for v in smooth[mask]]
    axes[2].plot(idx, y, 'ko', markersize=2)
    axes[2].set_title('Smoothness categories (OSM levels)')
    axes[2].set_yticks(list(range(len(levels))))
    axes[2].set_yticklabels(levels)
    axes[2].set_xlabel('sample index')

    fig.tight_layout()
    return fig


def plot_smoothness_panels_4(
    df: pd.DataFrame,
    calibrated_thresholds: dict | None,
    point_osm_labels: pd.Series | None = None,
):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=False)

    # 1) Raw z proxy
    z = df.get("z_std_mg") if df is not None else None
    if z is None:
        z = pd.Series([0] * len(df))
    axes[0].plot(z.values, color='tab:blue', linewidth=0.8)
    axes[0].set_title('Raw z-axis proxy (z_std_mg)')
    axes[0].set_ylabel('mg')

    # 2) Smoothed with threshold bands
    z_s = df.get("z_std_smooth")
    if z_s is not None:
        axes[1].plot(z_s.values, color='tab:orange', linewidth=0.8)
    else:
        axes[1].plot(z.values, color='tab:orange', linewidth=0.8)
    axes[1].set_title('Smoothed z with calibrated bands')
    axes[1].set_ylabel('mg')
    if calibrated_thresholds:
        try:
            t1 = float(calibrated_thresholds.get('excellent_max'))
            t2 = float(calibrated_thresholds.get('good_max'))
            t3 = float(calibrated_thresholds.get('intermediate_max'))
            ymax = float(np.nanmax((z_s if z_s is not None else z).values)) * 1.1
            axes[1].axhspan(0, t1, color='#e8f5e9', alpha=0.4, label='excellent')
            axes[1].axhspan(t1, t2, color='#e3f2fd', alpha=0.3, label='good')
            axes[1].axhspan(t2, t3, color='#fff3e0', alpha=0.3, label='intermediate')
            axes[1].axhspan(t3, ymax, color='#ffebee', alpha=0.25, label='bad')
            axes[1].legend(loc='upper right', frameon=False)
        except Exception:
            pass

    # 3) Predicted class per point (post-calibration)
    # Expect df['pred_label'] column to be present
    pred = df.get('pred_label')
    levels = ["excellent","good","intermediate","bad"]
    level_to_num = {lvl: i for i, lvl in enumerate(levels)}
    if pred is not None:
        mask = pred.notna()
        idx = pred[mask].index.to_numpy()
        y = [level_to_num.get(str(v)) for v in pred[mask]]
        axes[2].plot(idx, y, 'ko', markersize=2)
    axes[2].set_title('Predicted class (calibrated)')
    axes[2].set_yticks(list(range(len(levels))))
    axes[2].set_yticklabels(levels)
    axes[2].set_xlabel('sample index')

    # 4) Correlation strip vs OSM tag (if provided)
    # green=match, red=mismatch, gray=untagged/NA
    if point_osm_labels is None:
        point_osm_labels = pd.Series([None] * len(df))
    colors = []
    for i in range(len(df)):
        pl = pred.iloc[i] if pred is not None and i < len(pred) else None
        osm = point_osm_labels.iloc[i] if i < len(point_osm_labels) else None
        if osm is None or (isinstance(osm, float) and np.isnan(osm)):
            colors.append('#cccccc')  # untagged
        else:
            colors.append('#2ecc71' if str(pl) == str(osm) else '#e74c3c')
    axes[3].imshow([np.arange(len(colors))], aspect='auto', cmap=None)
    axes[3].imshow([np.zeros(len(colors))], extent=[0, len(colors), 0, 1], aspect='auto', alpha=0.0)
    axes[3].set_title('Correlation with existing OSM tags (green=match, red=mismatch, gray=untagged)')
    axes[3].set_yticks([])
    axes[3].set_xlabel('sample index')

    fig.tight_layout()
    return fig


def plot_proposals_mapbox(
    proposals: List[Dict],
    id_to_geom: Dict[int, object],
    mapbox_token: str,
    center: Optional[Tuple[float, float]] = None,
    raw_path_coords: Optional[List[Tuple[float, float]]] = None,
):
    """
    Plot OSM ways as Mapbox lines colored by proposal status.

    - proposals: list of dicts with keys way_id, proposed_value, coverage_pct, bad_run_m,
      agree_pct, existing_smoothness, counts
    - id_to_geom: way_id -> shapely LineString (or any object exposing .coords of (lon, lat))
    - mapbox_token: Mapbox access token
    - center: optional (lat, lon) to center the map; computed from geometries if None
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    pio.renderers.default = pio.renderers.default or "plotly_mimetype"

    # compute center if missing
    if center is None:
        all_coords: List[Tuple[float, float]] = []
        for geom in id_to_geom.values():
            try:
                all_coords.extend(list(geom.coords))
            except Exception:
                continue
        if all_coords:
            mean_lon = sum(c[0] for c in all_coords) / len(all_coords)
            mean_lat = sum(c[1] for c in all_coords) / len(all_coords)
            center = (mean_lat, mean_lon)
        else:
            center = (0.0, 0.0)

    traces: List[go.Scattermapbox] = []
    for p in proposals:
        way_id = int(p.get("way_id"))
        geom = id_to_geom.get(way_id)
        if geom is None:
            continue
        # Handle LineString or MultiLineString
        geoms_to_plot = []
        try:
            geoms_to_plot = list(getattr(geom, 'geoms', []))
        except Exception:
            geoms_to_plot = []
        if not geoms_to_plot:
            geoms_to_plot = [geom]

        proposed = p.get("proposed_value") or ""
        if proposed == "bad":
            color = "#e74c3c"  # red
        elif proposed == "intermediate":
            color = "#f39c12"  # orange
        elif p.get("existing_smoothness"):
            color = "#95a5a6"  # gray (already tagged)
        else:
            color = "#bdc3c7"  # light gray (skipped)

        for sub_geom in geoms_to_plot:
            try:
                coords = list(sub_geom.coords)
            except Exception:
                continue
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]

            hover = (
                f"way {way_id}<br>proposed: {p.get('proposed_value') or 'skip'}"
                f"<br>existing: {p.get('existing_smoothness') or '-'}"
                f"<br>coverage: {int((p.get('coverage_pct') or 0)*100)}%"
                f"<br>agree: {int((p.get('agree_pct') or 0)*100)}%"
                f"<br>bad_run: {p.get('bad_run_m') or 0} m"
            )
            # Each point carries a customdata URL so clicks can open OSM
            osm_url = f"https://www.openstreetmap.org/way/{way_id}"
            customdata = [osm_url] * len(lats)
            traces.append(
                go.Scattermapbox(
                    lon=lons,
                    lat=lats,
                    mode="lines",
                    line=dict(color=color, width=5),
                    hoverinfo="text",
                    text=hover,
                    name=str(way_id),
                    showlegend=False,
                    customdata=customdata,
                )
            )

    # Optional raw path trace (original GPS path)
    if raw_path_coords and len(raw_path_coords) >= 2:
        raw_lons = [c[0] for c in raw_path_coords]
        raw_lats = [c[1] for c in raw_path_coords]
        traces.append(
            go.Scattermapbox(
                lon=raw_lons,
                lat=raw_lats,
                mode="lines",
                line=dict(color="#1f77b4", width=3),
                name="raw",
                showlegend=False,
                opacity=0.7,
                hoverinfo="skip",
            )
        )

    fig = go.Figure(data=traces)
    fig.update_layout(
        mapbox=dict(
            accesstoken=mapbox_token,
            style="streets",
            center=dict(lat=center[0], lon=center[1]),
            zoom=14,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        clickmode="event+select",
    )
    return fig


def proposals_mapbox_clickable_html(
    proposals: List[Dict],
    id_to_geom: Dict[int, object],
    mapbox_token: str,
    center: Optional[Tuple[float, float]] = None,
    raw_path_coords: Optional[List[Tuple[float, float]]] = None,
):
    """
    Return an HTML snippet that renders the Plotly Mapbox figure and opens
    the OSM way in a new tab when the user clicks a segment.
    """
    import plotly.io as pio

    fig = plot_proposals_mapbox(proposals, id_to_geom, mapbox_token, center, raw_path_coords)
    div_id = "w4w_proposals_mapbox"
    post_script = f"""
    const gd = document.getElementById('{div_id}');
    if (gd) {{
      gd.on('plotly_click', function(data) {{
        try {{
          var url = data.points && data.points[0] && data.points[0].customdata;
          if (url) {{ window.open(url, '_blank'); }}
        }} catch (e) {{}}
      }});
    }}
    // Toggle controls wiring
    (function(){{
      const rawToggle = document.getElementById('w4w-toggle-raw');
      const propToggle = document.getElementById('w4w-toggle-proposals');
      function findIndices() {{
        const data = gd && gd.data ? gd.data : [];
        const rawIdx = [];
        const propIdx = [];
        for (let i=0;i<data.length;i++) {{
          if (data[i] && data[i].type === 'scattermapbox') {{
            if (data[i].name === 'raw') rawIdx.push(i); else propIdx.push(i);
          }}
        }}
        return {{rawIdx, propIdx}};
      }}
      function setVisible(indices, visible) {{
        if (!gd || !indices || !indices.length) return;
        Plotly.restyle(gd, {{visible: visible}}, indices);
      }}
      const {{rawIdx, propIdx}} = findIndices();
      if (propToggle) {{
        propToggle.addEventListener('change', (e) => setVisible(propIdx, e.target.checked));
      }}
      if (rawToggle) {{
        rawToggle.addEventListener('change', (e) => setVisible(rawIdx, e.target.checked));
      }}
    }})();
    """
    html_fig = pio.to_html(
        fig,
        include_plotlyjs="cdn",
        full_html=False,
        div_id=div_id,
        post_script=post_script,
    )
    # Controls UI (absolute positioned)
    controls = [
        "<div id=\"w4w-layer-toggle\" style=\"position:absolute;top:8px;left:8px;background:#fff;padding:8px;border-radius:4px;z-index:1;\">",
        '<label><input type="checkbox" id="w4w-toggle-proposals" checked> clipped</label>',
    ]
    if raw_path_coords and len(raw_path_coords) >= 2:
        controls.append('<label style="margin-left:8px;"><input type="checkbox" id="w4w-toggle-raw" checked> raw</label>')
    controls.append("</div>")
    return "".join(controls) + html_fig



# --- Save helpers for script-mode reuse ---
def save_raw_map_html(df, mapbox_token: str, out_html_path: Path) -> None:
    """Render raw Mapbox path and save as HTML.

    df must contain 'lat' and 'lon' columns.
    """
    import plotly.io as pio
    fig = plot_raw_map_plotly(df, mapbox_token)
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    pio.write_html(fig, file=str(out_html_path), include_plotlyjs="cdn", auto_open=False)


def save_clickable_proposals_html(
    proposals: List[Dict],
    id_to_geom: Dict[int, object],
    mapbox_token: str,
    out_html_path: Path,
    raw_path_coords: Optional[List[Tuple[float, float]]] = None,
) -> None:
    html = proposals_mapbox_clickable_html(proposals, id_to_geom, mapbox_token, None, raw_path_coords)
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_html_path, "w") as f:
        f.write(html)
