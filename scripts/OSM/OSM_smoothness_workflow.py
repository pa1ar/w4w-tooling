# %% [markdown]
# # Wheels4Wheels: OSM Smoothness Workflow (End-to-End, script)
#
# This script runs the full workflow using reusable pipeline functions (no code duplication):
# 1. Load ride telemetry (JSON/CSV)
# 2. Smooth and classify per-point smoothness
# 3. Map-match with Mapbox (walking)
# 4. Fetch OSM ways (Overpass) and assign points to ways
# 5. Aggregate per-way and propose smoothness tags
# 6. Export proposals CSV and a review map (Mapbox GL JS)
# 7. (Optional) Dry-run batch apply to OSM via existing CLI
#
#

# %% [markdown]
# ### Setup: environment and tokens
# Load `.env`, locate the repo root (works in script or notebook), and assert that `MAPBOX_ACCESS_TOKEN` is available. This cell does not write any files.
#

# %%
# prerequisites: uv install has provided dependencies
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Resolve repository root when running in a notebook (no __file__)

def find_repo_root(start: Path) -> Path:
    cur = start
    for _ in range(6):
        if (cur / 'scripts').exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start

PROJECT_ROOT = find_repo_root(Path.cwd())
ENV_PATH = PROJECT_ROOT / '.env'
load_dotenv(ENV_PATH)

# %% [markdown]
# ### Import pipeline functions
# Dynamically import `scripts/OSM/prepare_smoothness_from_ride.py` as `prep` to reuse CLI-ready functions in the notebook without duplication.
#

# %%
# reuse pipeline functions from scripts (no duplication)
import importlib.util, sys
scripts_osm = PROJECT_ROOT / 'scripts' / 'OSM'

# dynamic import of prepare_smoothness_from_ride functions
prep_path = scripts_osm / 'prepare_smoothness_from_ride.py'
spec = importlib.util.spec_from_file_location('prep', prep_path)
prep = importlib.util.module_from_spec(spec)
sys.modules['prep'] = prep
spec.loader.exec_module(prep)

print('Imported from:', prep_path)



# %% [markdown]
# ### CLI arguments and I/O paths
# Parse inputs and outputs via CLI. Defaults preserve current behavior.
#
#

# %%
parser = argparse.ArgumentParser(description='Wheels4Wheels: OSM Smoothness Workflow (clipped pipeline)')
parser.add_argument('--input', type=str, default=str(PROJECT_ROOT / 'telemetry_json' / '258276934-579126.json'), help='Path to ride telemetry (JSON/CSV)')
parser.add_argument('--out-csv', type=str, default=str(PROJECT_ROOT / 'output' / 'smoothness_proposals.csv'), help='Output CSV for proposals')
parser.add_argument('--out-map', type=str, default=str(PROJECT_ROOT / 'output' / 'smoothness_proposals.html'), help='Output HTML Mapbox review map')
parser.add_argument('--raw-map-html', type=str, default=str(PROJECT_ROOT / 'output' / 'raw_map.html'), help='Output HTML for raw GPS map')
parser.add_argument('--out-ways-geojson', type=str, help='Output GeoJSON with proposal way geometries (defaults to output/proposals_geojson/<source>.geojson)')
parser.add_argument('--out-gps-geojson', type=str, default=str(PROJECT_ROOT / 'output' / 'gps_path.json'), help='Output GeoJSON with raw GPS path')
parser.add_argument('--buffer-m', type=float, default=18.0, help='Corridor clip buffer width in meters')
parser.add_argument('--bbox-pad', type=float, default=0.002, help='Bounding box padding in degrees')
parser.add_argument('--tolerance-m', type=float, default=25.0, help='Assignment tolerance in meters')
parser.add_argument('--bad-run', type=float, default=30.0, help='Bad run threshold in meters')
parser.add_argument('--no-plots', action='store_true', help='Skip interactive plot displays (still writes HTML files)')
parser.add_argument('--smoke', action='store_true', help='Run legacy single-pass pipeline (unclipped), for quick verification')
parser.add_argument('--path-id', type=int, help='Optional path identifier used in gps_paths_colored.json for this telemetry file')

args, _unknown_cli = parser.parse_known_args()

if not os.getenv('MAPBOX_ACCESS_TOKEN'):
    raise SystemExit('Missing MAPBOX_ACCESS_TOKEN in .env')

# inputs and outputs
INPUT = Path(args.input)
OUT_CSV = Path(args.out_csv)
OUT_MAP = Path(args.out_map)
OUT_RAWMAP = Path(args.raw_map_html)
OUT_GPS_GEOJSON = Path(args.out_gps_geojson)
if args.out_ways_geojson:
    OUT_WAY_GEOJSON = Path(args.out_ways_geojson)
else:
    default_geojson_dir = PROJECT_ROOT / 'output' / 'proposals_geojson'
    OUT_WAY_GEOJSON = default_geojson_dir / f"{INPUT.stem}.geojson"

print(INPUT)



# %% [markdown]
# ### Quick smoke test: legacy single-pass pipeline
# Run the original single-pass pipeline using `prep` functions. It writes a CSV and Mapbox GL HTML review map. Kept for quick verification; the detailed sections below redo steps with corridor clipping.
#

# %%
if args.smoke:
    # run the legacy single-pass pipeline (unclipped) for quick verification only
    df_raw = prep.load_points(INPUT, fmt='json')
    df_cls = prep.smooth_and_classify(df_raw, window_pts=25)
    coords = [(float(row['lon']), float(row['lat'])) for _, row in df_cls.iterrows()]
    snapped = prep.mapbox_match(coords, os.getenv('MAPBOX_ACCESS_TOKEN'), profile='mapbox/walking')
    lats = [lat for item in snapped if item for _, lat in [item]] or list(df_cls['lat'].values)
    lons = [lon for item in snapped if item for lon, _ in [item]] or list(df_cls['lon'].values)
    bbox_pad = float(args.bbox_pad)
    min_lat, max_lat = min(lats) - bbox_pad, max(lats) + bbox_pad
    min_lon, max_lon = min(lons) - bbox_pad, max(lons) + bbox_pad
    import time
    primary = os.getenv('OVERPASS_URL','https://overpass-api.de/api/interpreter')
    fallbacks = [u for u in getattr(prep, 'OVERPASS_FALLBACKS', [
        'https://overpass.kumi.systems/api/interpreter',
        'https://overpass-api.de/api/interpreter',
        'https://overpass.openstreetmap.ru/api/interpreter',
    ]) if u != primary]
    ways = []
    for url in [primary] + fallbacks:
        try:
            ways = prep.fetch_osm_ways_bbox(min_lat, min_lon, max_lat, max_lon, url, timeout_s=90)
            if ways:
                print(f'Smoke Overpass OK: {url} (ways={len(ways)})')
                break
        except Exception as e:
            print(f'Smoke Overpass failed: {url} -> {e}')
            time.sleep(1.0)
    assert ways, 'No ways returned from Overpass (smoke)'
    (tree, id_to_geom, id_to_tags, geoms, geom_way_ids) = prep.build_way_index(ways)
    to_assign = []
    for idx, s in enumerate(snapped):
        if s is not None:
            to_assign.append(s)
        else:
            to_assign.append((float(df_cls.iloc[idx]['lon']), float(df_cls.iloc[idx]['lat'])))
    assigned = prep.assign_points_to_ways(to_assign, tree, geoms, geom_way_ids, tolerance_m=25)
    if all(v is None for v in assigned):
        assigned = prep.assign_points_to_ways_bruteforce(to_assign, geoms, geom_way_ids, tolerance_m=25)
    import pandas as pd
    df_pts = df_cls.copy()
    df_pts['lon_snapped'] = [pt[0] if pt else float('nan') for pt in to_assign]
    df_pts['lat_snapped'] = [pt[1] if pt else float('nan') for pt in to_assign]
    df_pts['way_id'] = assigned
    df_assigned = df_pts.dropna(subset=['way_id']).copy()
    proposals = prep.aggregate_by_way(df_assigned, id_to_geom, id_to_tags, bad_run_threshold_m=float(args.bad_run))
    import csv
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['way_id','proposed_value','coverage_pct','bad_run_m','agree_pct','existing_smoothness','counts','comment'])
        writer.writeheader()
        for p in proposals:
            writer.writerow(p)
    print('wrote CSV', OUT_CSV)
    prep.make_map(proposals, id_to_geom, OUT_MAP)
    print('wrote MAP', OUT_MAP)



# %% [markdown]
# ### Quick preview of high-confidence proposals (from smoke test)
# Read the just-written CSV and show a few likely candidates.
#

# %%
# optional: preview first 10 high-confidence proposals from smoke
if os.getenv('W4W_SMOKE') == '1':
    import pandas as pd
    pdf = pd.read_csv(OUT_CSV)
    preview = pdf[(pdf['proposed_value'].isin(['intermediate','bad'])) & (pdf['coverage_pct']>=0.7) & (pdf['agree_pct']>=0.7)].head(10)
    preview


# %% [markdown]
# ### Plot utilities and renderer setup
# Import `plot_utils.py` and configure Plotly rendering.
#

# %%
# import plotting utilities
import importlib.util
plot_path = scripts_osm / 'plot_utils.py'
spec_p = importlib.util.spec_from_file_location('plot_utils', plot_path)
plot_utils = importlib.util.module_from_spec(spec_p)
spec_p.loader.exec_module(plot_utils)
print('Imported plots from:', plot_path)

# ensure plotly renders inline
import plotly.io as pio
try:
    pio.renderers.default = 'plotly_mimetype'
except Exception:
    pio.renderers.default = 'notebook_connected'



# %% [markdown]
# ### Plot 1: raw ride path (Mapbox, no margins)
# Visual sanity check of the raw GPS trace before map-matching.
#

# %%
# Plot 1: raw ride path on a Mapbox map
# Ensure df_cls exists (recompute minimal pipeline if needed)
if 'df_cls' not in globals():
    df_raw = prep.load_points(INPUT, fmt='json')
    df_cls = prep.smooth_and_classify(df_raw, window_pts=25)

# Configure Plotly renderer + Mapbox token and show the figure
import plotly.io as pio, plotly.express as px
px.set_mapbox_access_token(os.getenv('MAPBOX_ACCESS_TOKEN'))
try:
    pio.renderers.default = 'plotly_mimetype'  # works in Jupyter and nbconvert
except Exception:
    pio.renderers.default = 'notebook_connected'

# Skip inline raw GPS figure to streamline workflow (HTML written later)

# Export raw GPS path (GeoJSON LineString)
try:
    import importlib.util as _imp_export
    _exp_path = scripts_osm / 'export_gps_path_geojson.py'
    _exp_spec = _imp_export.spec_from_file_location('export_gps', _exp_path)
    export_gps = _imp_export.module_from_spec(_exp_spec)
    _exp_spec.loader.exec_module(export_gps)  # type: ignore
    export_gps.write_gps_path_geojson(df_cls[['lon','lat']], OUT_GPS_GEOJSON)
    print(f'Wrote GPS path GeoJSON: {OUT_GPS_GEOJSON}')
except Exception as _exp_err:
    print('GPS path export skipped:', _exp_err)


# %% [markdown]
# ### Plot 2: three-panel z-axis analysis
# Show raw z-std, smoothed z-std, and categorical smoothness. Stationary segments are masked (`pd.NA`).
#

# %%
# Plot 2: three-panel smoothness analysis

# recompute df_cls to get NA for stationary
df_raw = prep.load_points(INPUT, fmt='json')
df_cls = prep.smooth_and_classify(df_raw, window_pts=25)

# In script mode, avoid module reload gymnastics; we already imported plot_utils above

# redraw
fig_panels = plot_utils.plot_smoothness_panels(df_cls)

# %% [markdown]
# ### Step 3: Map-match and assign (clipped workflow)
# Orchestrated end-to-end run that includes map-matching, Overpass fetch (with retries),
# corridor clipping, spatial assignment, and aggregation.
#

# %% [markdown]
# ### Map-match with Mapbox
# (Performed inside the orchestrator)
#

# %% [markdown]
# ### Build spatial index and clip to rider corridor
# - Build an STRtree over OSM way geometries
# - Clip ways to a narrow buffer around the snapped rider trace (`clip_ways_to_trace`).
# - Rebuild the index over clipped fragments to avoid “hallucinated” parallel ways.
# - Assign each point to the nearest clipped way (with brute-force fallback).
#

# %%
# Map-match with Mapbox walking profile
coords = [(float(row['lon']), float(row['lat'])) for _, row in df_cls.iterrows()]
snapped = prep.mapbox_match(coords, os.getenv('MAPBOX_ACCESS_TOKEN'), profile='mapbox/walking')

print(f'Original points: {len(coords)}')
print(f'Snapped points: {len([s for s in snapped if s is not None])}')


# %% [markdown]
# ### Fetch OSM ways via Overpass (with retries)
# (Performed inside the orchestrator)
#

# %%
# Fetch OSM ways in ride bounding box via Overpass
lats = [lat for item in snapped if item for _, lat in [item]] or list(df_cls['lat'].values)
lons = [lon for item in snapped if item for lon, _ in [item]] or list(df_cls['lon'].values)
bbox_pad = float(args.bbox_pad)
min_lat, max_lat = min(lats) - bbox_pad, max(lats) + bbox_pad
min_lon, max_lon = min(lons) - bbox_pad, max(lons) + bbox_pad

# Robust Overpass fetch with fallbacks
import time
primary = os.getenv('OVERPASS_URL','https://overpass-api.de/api/interpreter')
fallbacks = [u for u in getattr(prep, 'OVERPASS_FALLBACKS', [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.openstreetmap.ru/api/interpreter',
]) if u != primary]
ways = []
for url in [primary] + fallbacks:
    try:
        ways = prep.fetch_osm_ways_bbox(min_lat, min_lon, max_lat, max_lon, url, timeout_s=90)
        if ways:
            print(f'Overpass OK: {url} (ways={len(ways)})')
            break
    except Exception as e:
        print(f'Overpass failed: {url} -> {e}')
        time.sleep(1.0)
assert ways, 'No ways returned from Overpass'


# %% [markdown]
# ### Step 3 (continued): build index, clip corridor, and assign
# Clip OSM ways to a narrow buffer around the rider's snapped trace, rebuild the index on clipped fragments,
# and assign points to the nearest clipped segment (with brute-force fallback).
#

# %%
# Import orchestrator without package context
import importlib.util as _importlib_util
_orc_path = scripts_osm / 'workflow_orchestrator.py'
_orc_spec = _importlib_util.spec_from_file_location('workflow_orchestrator', _orc_path)
workflow_orchestrator = _importlib_util.module_from_spec(_orc_spec)
sys.modules['workflow_orchestrator'] = workflow_orchestrator
_orc_spec.loader.exec_module(workflow_orchestrator)  # type: ignore
run_clipped_workflow = workflow_orchestrator.run_clipped_workflow

overpass_urls = [
    os.getenv('OVERPASS_URL','https://overpass-api.de/api/interpreter'),
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.openstreetmap.ru/api/interpreter',
]
res = run_clipped_workflow(
    input_path=INPUT,
    mapbox_token=os.getenv('MAPBOX_ACCESS_TOKEN'),
    overpass_urls=overpass_urls,
    buffer_m=float(args.buffer_m),
    bbox_pad=float(args.bbox_pad),
    tolerance_m=float(args.tolerance_m),
    bad_run_m=float(args.bad_run),
)
proposals = res.proposals
id_to_geom_clip = res.id_to_geom_clip
df_assigned = res.df_assigned
print(f"Points total assigned: {res.stats['assigned_pct']:.1f}% | proposals={int(res.stats['proposals'])}")


# %% [markdown]
# ### Unified preview of clipped segments
# The same standalone Mapbox GL review map is displayed inline after writing it.

# %%
_display_map_inline = True and not args.no_plots

# %% [markdown]
# ## Step 4: Aggregate by way and generate proposals
# For each OSM way, compute coverage, category distribution, and longest "bad" run, then apply the tagging policy.
#

# %% [markdown]
# ### High-confidence proposals table
# Show a compact table of proposals exceeding coverage and agreement thresholds for quick inspection.
#

# %%
# proposals already computed by the orchestrator
print(f'Generated {len(proposals)} proposals')


# %% [markdown]
# ## Step 5: Export proposals and review map
# Write a CSV for batch upload and a Mapbox GL review map generated from the clipped fragments.
#

# %%
# %% [markdown]
# ### Calibration against OSM tags (threshold tuning)
# We calibrate thresholds using smoothed z values (exclude stationary ~0 mg; clip >800 mg) and
# OSM smoothness=* tags as ground truth on tagged ways. Focus range ~50–600 mg; most travel should be
# excellent/good/intermediate; prolonged high-mg implies bad. The calibrated thresholds (mg) are saved
# to output/calibrated_thresholds.json and used for re-aggregation.

# Calibrate multiclass thresholds from df_assigned and existing tags on ways
try:
    import importlib.util as _imp_cal
    _cal_path = scripts_osm / 'calibration.py'
    _cal_spec = _imp_cal.spec_from_file_location('calibration', _cal_path)
    calibration = _imp_cal.module_from_spec(_cal_spec)
    _cal_spec.loader.exec_module(calibration)  # type: ignore

    # way_id -> existing smoothness from initial proposals
    way_to_label = {}
    for p in proposals:
        wid = int(p['way_id'])
        lbl = p.get('existing_smoothness')
        if lbl:
            way_to_label[wid] = lbl

    z_col = 'z_std_smooth' if 'z_std_smooth' in df_assigned.columns else ('z_std_mg' if 'z_std_mg' in df_assigned.columns else None)
    xs, ys = calibration.collect_labeled_samples(df_assigned, way_to_label, z_col, min_mg=5.0, max_mg=800.0) if z_col else ([], [])

    thr_obj = None
    if xs and ys:
        thr_obj = calibration.search_thresholds_grid(xs, ys)
        thr_json_path = PROJECT_ROOT / 'output' / 'calibrated_thresholds.json'
        calibration.save_thresholds_json(thr_obj, thr_json_path)

        # Apply thresholds to classifier and re-aggregate proposals
        import importlib.util as _imp_prep2
        _prep2_spec = _imp_prep2.spec_from_file_location('prep2', prep_path)
        prep2 = _imp_prep2.module_from_spec(_prep2_spec)
        _prep2_spec.loader.exec_module(prep2)  # type: ignore
        prep2.set_classification_thresholds(thr_obj.excellent_max, thr_obj.good_max, thr_obj.intermediate_max, thr_obj.bad_max)

        # Recompute per-point category using calibrated thresholds and compute per-point prediction
        if z_col:
            df_assigned['pred_label'] = df_assigned[z_col].apply(prep2.classify_point)
            df_assigned['smoothness_point'] = df_assigned['pred_label']

        # Build synthetic id_to_tags from existing labels
        id_to_tags_synth = {int(p['way_id']): ({'smoothness': p.get('existing_smoothness')} if p.get('existing_smoothness') else {}) for p in proposals}

        # Per-way agreement metrics vs OSM tags
        import pandas as _pd
        def _norm(lbl: str | None) -> str | None:
            if not lbl:
                return None
            t = str(lbl).strip().lower()
            return 'very_bad' if t in {'very-bad','very bad'} else t

        # per-point match flag for tagged ways
        way_to_norm = {wid: _norm(lbl) for wid, lbl in way_to_label.items()}
        df_assigned['_osm_tag'] = df_assigned['way_id'].map(lambda w: way_to_norm.get(int(w)) if _pd.notna(w) else None)
        df_assigned['_match_flag'] = _pd.Series([
            (str(pl) == str(osm)) if (pl is not None and osm is not None and str(osm) != '') else _pd.NA
            for pl, osm in zip(df_assigned.get('pred_label'), df_assigned.get('_osm_tag'))
        ])

        # Re-aggregate with calibrated labels and add agreement fields
        proposals_cal = prep2.aggregate_by_way(df_assigned, id_to_geom_clip, id_to_tags_synth, bad_run_threshold_m=float(args.bad_run))
        # attach predicted_way_class and osm_match metrics per way
        pred_by_way = df_assigned.dropna(subset=['way_id','pred_label']).groupby('way_id')['pred_label'].agg(lambda s: s.value_counts().idxmax()).to_dict()
        match_pct_by_way = df_assigned.dropna(subset=['way_id']).groupby('way_id')['_match_flag'].apply(lambda s: float(s.dropna().mean()) if s.dropna().size > 0 else 0.0).to_dict()
        for p in proposals_cal:
            wid = int(p['way_id'])
            p['predicted_way_class'] = str(pred_by_way.get(wid, ''))
            if p.get('existing_smoothness'):
                p['osm_match'] = ( _norm(p.get('existing_smoothness')) == p['predicted_way_class'] )
                p['osm_match_pct'] = round(match_pct_by_way.get(wid, 0.0), 3)
            else:
                p['osm_match'] = ''
                p['osm_match_pct'] = ''

        # Agreement metrics on ways with existing tags
        import collections as _cx
        tagged_way_ids = [int(p['way_id']) for p in proposals if p.get('existing_smoothness')]
        old_map = {int(p['way_id']): p.get('proposed_value') for p in proposals if int(p['way_id']) in tagged_way_ids}
        new_map = {int(p['way_id']): p.get('proposed_value') for p in proposals_cal if int(p['way_id']) in tagged_way_ids}
        agree_cnt = sum(1 for wid in tagged_way_ids if (old_map.get(wid) == new_map.get(wid)))
        agree_rate = (agree_cnt / len(tagged_way_ids)) if tagged_way_ids else 0.0

        # Confusion matrix between OSM tag and predicted class of samples
        preds = [calibration.predict_label_from_z(x, thr_obj) for x in xs]
        # Build simple confusion counts
        cm = _cx.Counter()
        for yt, yp in zip(ys, preds):
            cm[(yt, yp)] += 1

        # Write calibration report (add overall point-level match where applicable)
        rep_path = PROJECT_ROOT / 'output' / 'calibration_report.md'
        lines = []
        lines.append('# Calibration Report')
        lines.append('')
        lines.append(f"Thresholds (mg): excellent<{thr_obj.excellent_max:.1f}, good<{thr_obj.good_max:.1f}, intermediate<{thr_obj.intermediate_max:.1f}, bad<{thr_obj.bad_max:.1f}, else very_bad")
        lines.append('')
        lines.append('Agreement on tagged ways (baseline vs calibrated proposals):')
        lines.append(f"- ways compared: {len(tagged_way_ids)}")
        lines.append(f"- unchanged proposals: {agree_cnt} ({agree_rate*100:.1f}%)")
        # point-level match rate across tagged ways
        try:
            _pt_match = float(_pd.to_numeric(df_assigned['_match_flag'], errors='coerce').dropna().mean())
            lines.append(f"- point-level match vs OSM tag: {(_pt_match*100):.1f}%")
        except Exception:
            pass
        lines.append('')
        lines.append('Confusion matrix (OSM tag → predicted by calibrated thresholds):')
        for yt in ['excellent','good','intermediate','bad','very_bad']:
            row = []
            for yp in ['excellent','good','intermediate','bad','very_bad']:
                row.append(str(cm.get((yt, yp), 0)))
            lines.append(f"- {yt}: " + ", ".join(row))
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        rep_path.write_text("\n".join(lines), encoding='utf-8')

        # Replace proposals with calibrated ones for downstream CSV/map
        proposals = proposals_cal
        print(f"Applied calibrated thresholds; proposals now {len(proposals)} (report: {rep_path})")
    else:
        print('Calibration skipped: insufficient labeled samples')
except Exception as _cal_err:
    print('Calibration step failed:', _cal_err)
# ### Wheelchair-focused confidence (per-way)
# We compute two confidence metrics per point and aggregate them per way:
# - old_confidence: threshold-distance confidence based on z-std distance to thresholds (50,100,200,400 mg)
# - wheelchair_confidence: combines threshold clarity with speed appropriateness and recent-movement continuity
#
# Then we average wheelchair_confidence per way_id and attach `confidence_wheelchair` to each proposal.

# %%
def _calculate_threshold_confidence(std_dev: float) -> float:
    try:
        val = float(std_dev)
    except Exception:
        return 0.0
    thresholds = [60.0, 110.0, 180.0, 250.0]
    min_distance = min(abs(val - t) for t in thresholds)
    confidence = 0.5 + (min_distance / 20.0) if min_distance < 10.0 else 1.0
    if confidence < 0.0:
        return 0.0
    if confidence > 1.0:
        return 1.0
    return confidence

def _calculate_wheelchair_confidence(std_dev: float, speed_kmh: float, recent_speeds_kmh: list[float]) -> float:
    base_conf = _calculate_threshold_confidence(std_dev)
    # speed factor
    try:
        v = float(speed_kmh)
    except Exception:
        v = 0.0
    if v == 0:
        speed_factor = 0.3
    elif 2.0 <= v <= 6.0:
        speed_factor = 1.0
    elif v > 10.0:
        speed_factor = 0.4
    elif v > 6.0:
        speed_factor = 0.7
    else:
        speed_factor = 0.8
    # continuity factor from recent stops
    continuity_factor = 1.0
    try:
        if recent_speeds_kmh:
            recent_stops = sum(1 for s in recent_speeds_kmh if float(s) == 0.0)
            continuity_factor = max(0.5, 1.0 - (recent_stops / float(len(recent_speeds_kmh))))
    except Exception:
        continuity_factor = 1.0
    final_conf = base_conf * speed_factor * continuity_factor
    return max(0.0, min(1.0, final_conf))

# Compute per-point confidence columns and aggregate per way
try:
    import pandas as _pd
    _df_conf = df_assigned.copy()
    # choose z std column
    _z_col = 'z_std_mg' if 'z_std_mg' in _df_conf.columns else ('z_std_smooth' if 'z_std_smooth' in _df_conf.columns else None)
    # derive speed in km/h
    if 'speed_kmh' in _df_conf.columns:
        _df_conf['_speed_kmh'] = _pd.to_numeric(_df_conf['speed_kmh'], errors='coerce').fillna(0.0)
    elif 'speed' in _df_conf.columns:
        # speed already in km/h after load_points conversion (raw 1/10 km/h / 10)
        _df_conf['_speed_kmh'] = _pd.to_numeric(_df_conf['speed'], errors='coerce').fillna(0.0)
    else:
        _df_conf['_speed_kmh'] = 0.0
    # threshold confidence
    if _z_col:
        _df_conf['old_confidence'] = _df_conf[_z_col].apply(_calculate_threshold_confidence)
    else:
        _df_conf['old_confidence'] = 0.0
    # wheelchair confidence with short lookback window of speeds (last 5)
    _wc_values: list[float] = []
    _speeds = _df_conf['_speed_kmh'].tolist()
    _stds = _df_conf[_z_col].tolist() if _z_col else [None] * len(_df_conf)
    for i in range(len(_df_conf)):
        recent = _speeds[max(0, i-4):i+1]
        stdv = _stds[i] if i < len(_stds) else None
        _wc_values.append(_calculate_wheelchair_confidence(stdv if stdv is not None else 0.0, _speeds[i], recent))
    _df_conf['wheelchair_confidence'] = _wc_values
    # per-way aggregation (mean)
    _wc_by_way = _df_conf.groupby('way_id')['wheelchair_confidence'].mean().to_dict()
    # attach to proposals
    for p in proposals:
        wid = int(p['way_id'])
        p['confidence_wheelchair'] = round(float(_wc_by_way.get(wid, 0.0)), 3)
except Exception as _e:
    print('confidence computation skipped:', _e)

import importlib.util as _imp
_io_path = scripts_osm / 'io_utils.py'
_io_spec = _imp.spec_from_file_location('io_utils', _io_path)
io_utils = _imp.module_from_spec(_io_spec)
sys.modules['io_utils'] = io_utils
_io_spec.loader.exec_module(io_utils)  # type: ignore

io_utils.write_proposals_csv(proposals, OUT_CSV)
print(f'Wrote proposals CSV: {OUT_CSV}')
# Provide per-point z for gradient path coloring when available
_rp = []
for _, row in df_cls.iterrows():
    try:
        lon = float(row['lon']); lat = float(row['lat'])
        z = None
        if 'z_std_smooth' in row and row['z_std_smooth'] == row['z_std_smooth']:
            z = float(row['z_std_smooth'])
        elif 'z_std_mg' in row and row['z_std_mg'] == row['z_std_mg']:
            z = float(row['z_std_mg'])
        _rp.append({'lon': lon, 'lat': lat, 'z': z})
    except Exception:
        continue
raw_path_coords = _rp if _rp else [(float(row['lon']), float(row['lat'])) for _, row in df_cls.iterrows()]
io_utils.write_review_map(proposals, id_to_geom_clip, OUT_MAP, raw_path_coords=raw_path_coords)
print(f'Wrote review map: {OUT_MAP}')
io_utils.write_proposals_geojson(
    proposals,
    id_to_geom_clip,
    OUT_WAY_GEOJSON,
    source_file=INPUT.name,
    path_id=args.path_id,
)
print(f'Wrote proposals GeoJSON: {OUT_WAY_GEOJSON}')
if _display_map_inline:
    try:
        from IPython.display import display, HTML as _HTML  # type: ignore
        _map_html_text = OUT_MAP.read_text(encoding='utf-8')
        display(_HTML(_map_html_text))
    except Exception:
        pass


# %%
# Plot 1: raw ride path on a Mapbox map
# Ensure df_cls exists (recompute minimal pipeline if needed)
if 'df_cls' not in globals():
    df_raw = prep.load_points(INPUT, fmt='json')
    df_cls = prep.smooth_and_classify(df_raw, window_pts=25)

# Configure Plotly renderer + Mapbox token and show the figure
import plotly.io as pio, plotly.express as px
px.set_mapbox_access_token(os.getenv('MAPBOX_ACCESS_TOKEN'))
try:
    pio.renderers.default = 'plotly_mimetype'  # works in Jupyter and nbconvert
except Exception:
    pio.renderers.default = 'notebook_connected'

fig_map = plot_utils.plot_raw_map_plotly(df_cls, os.getenv('MAPBOX_ACCESS_TOKEN'))
OUT_RAWMAP.parent.mkdir(parents=True, exist_ok=True)
import plotly.io as _pio_write
_pio_write.write_html(fig_map, file=str(OUT_RAWMAP), auto_open=False, include_plotlyjs='cdn')
print(f'wrote raw map HTML {OUT_RAWMAP}')





# %% [markdown]
# ### What the Mapbox tooltip shows
#
# - **way <id>**: The OpenStreetMap way identifier. Clicking a segment opens this way on OSM in a new tab.
# - **proposed**: The single smoothness tag we propose for the whole way based on telemetry (e.g., `bad` or `intermediate`).
# - **existing**: Current `smoothness=*` tag already present on the way in OSM. A dash (`-`) means there is no existing tag.
# - **coverage**: The share of the way length covered by our matched samples (sum of distances between consecutive assigned points on the same way ÷ total way length).
# - **agree**: Among labeled samples on this way, the fraction that are "intermediate-or-better" (`excellent`, `good`, or `intermediate`). Stationary samples are excluded.
# - **bad_run**: Length (meters) of the longest contiguous run of samples classified as `bad` or `very_bad` on this way.
#
# Policy reminder:
# - We propose `smoothness=bad` if `bad_run ≥ 30 m`.
# - Otherwise we propose `smoothness=intermediate` if `agree ≥ 70%`.
# - We do not propose a tag for ways that already have a `smoothness=*` tag in OSM.
#

# %%
# Display top proposals with high confidence
import pandas as pd
df_proposals = pd.DataFrame(proposals)
df_proposals_filtered = df_proposals[
    (df_proposals['proposed_value'] != '') &
    (df_proposals['coverage_pct'] > 0.3) &
    (df_proposals['agree_pct'] > 0.6)
].sort_values('coverage_pct', ascending=False)

print(f'\nHigh-confidence proposals (coverage>30%, agree>60%): {len(df_proposals_filtered)}')
df_proposals_filtered.head(10)


# %% [markdown]
# ## Next Steps
#
# 1. **Manual Review**: Open `output/smoothness_proposals.html` in a browser to review the proposed tags on an **interactive Mapbox GL JS map**.
#    - **Color legend**:
#      - 🔴 Red = `smoothness=bad` (≥30m bad run)
#      - 🟠 Orange = `smoothness=intermediate` (≥70% agree, no bad run)
#      - ⚫ Gray = Already has smoothness tag (skipped)
#      - ⚪ Light gray = No proposal (low coverage or doesn't meet policy)
#    - Click any way segment to see:
#      - Proposed vs. existing tag
#      - Coverage %, agreement %, bad run length
#      - Point counts by category
#      - Link to view/edit on OpenStreetMap
#
# 2. **Filter CSV**: Keep only high-confidence proposals:
#    ```python
#    import pandas as pd
#    df = pd.read_csv('output/smoothness_proposals.csv')
#    df_filtered = df[
#        (df['proposed_value'] != '') &
#        (df['coverage_pct'] > 0.7) &
#        (df['agree_pct'] > 0.7)
#    ]
#    df_filtered.to_csv('output/smoothness_proposals_filtered.csv', index=False)
#    ```
#
# 3. **Batch Upload**: Run `scripts/OSM/apply_smoothness_batch.py` to upload filtered proposals to OSM using the authenticated CLI.
#
# ### Dry-run example (no actual OSM writes):
# ```bash
# uv run python scripts/OSM/apply_smoothness_batch.py \
#   --csv output/smoothness_proposals_filtered.csv \
#   --min-coverage 0.7 \
#   --min-agree 0.7 \
#   --dry-run
# ```
#
# ### Important notes:
# - Only ways **without existing smoothness tags** receive proposals (safe gap-filling)
# - Stationary segments (speed ≤0.1 m/s or constant z) are excluded from analysis
# - Each upload includes changeset comment: `[w4w] smoothness from scooter telemetry`
#
