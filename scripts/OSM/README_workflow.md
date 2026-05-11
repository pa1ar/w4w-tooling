# OSM Smoothness Workflow (Clipped Pipeline)

This workflow processes a ride (CSV/JSON), computes per-point smoothness, map-matches to roads (Mapbox), fetches OSM ways (Overpass with fallbacks), clips ways to a narrow corridor around the ridden path, assigns points to clipped segments, and aggregates proposals for the OSM `smoothness` tag.

## Prerequisites
- `.env` with `MAPBOX_ACCESS_TOKEN`
- Optional: `OVERPASS_URL` (primary Overpass endpoint); the workflow retries across fallback endpoints
- Dependencies installed via `uv` (preferred) or `pip`

## Run
```bash
uv run python scripts/OSM/OSM_smoothness_workflow.py \
  --input telemetry_json/258276934-579126.json \
  --buffer-m 18 \
  --bbox-pad 0.002 \
  --tolerance-m 25 \
  --bad-run 30 \
  --out-csv output/smoothness_proposals.csv \
  --out-map output/smoothness_proposals.html \
  --raw-map-html output/raw_map.html
```

## What it produces
- `output/smoothness_proposals.csv`: per-way proposals with coverage/agree/bad-run metrics, wheelchair confidence, and agreement metrics.
  - New columns:
    - `predicted_way_class`: majority predicted class on the way using calibrated thresholds
    - `osm_match`: whether predicted matches existing OSM tag (if present)
    - `osm_match_pct`: share of points (on tagged ways) where per-point prediction matches OSM
- `output/smoothness_proposals.html`: Mapbox GL review map with toggles:
  - "filtered": policy-applied segments (gray if already tagged)
  - "segments": all detected segments, colored by detected smoothness
  - "confidence": color by smoothness, width by wheelchair confidence
  - "agreement": green/gray/yellow/orange/red visualizing predicted vs OSM tag agreement (see below)
  - "path": raw GPS trace
  This map is also displayed inline in interactive environments.
- `output/raw_map.html`: raw GPS path on Mapbox (no margins)

### Map toggles
- filtered: policy-colored segments (gray if already tagged, colored by proposed value otherwise)
- segments: all detected segments colored by proposed value, ignoring existing tags
- confidence: smoothness by color, line width ∝ wheelchair confidence
- agreement: predicted vs OSM tag agreement coloring
  - green: predicted == existing OSM tag
  - gray: no OSM tag on the way
  - yellow: one level off (e.g., good vs intermediate)
  - orange: two levels off
  - red: >2 levels off (unlikely post-calibration)
- path: raw GPS LineString path

## Flags
Run `--help` for full list. Common flags:
- `--buffer-m` (18.0): corridor buffer in meters
- `--bbox-pad` (0.002): pad degrees for Overpass bbox
- `--tolerance-m` (25.0): nearest-way assignment tolerance
- `--bad-run` (30.0): contiguous bad run threshold in meters
- `--smoke`: legacy single-pass (unclipped) run for quick sanity check
- `--no-plots`: suppress inline plotting (HTML written regardless)

## Tagging policy
- Propose `smoothness=bad` if longest contiguous bad run ≥ `--bad-run`
- Otherwise propose `smoothness=intermediate` if ≥70% points are intermediate-or-better
- Skip ways that already have `smoothness=*` in OSM
- Stationary points are excluded from analysis

## Calibration (z-std mg ↔ OSM smoothness)
- We calibrate thresholds using smoothed z-axis values (`z_std_smooth`) and OSM `smoothness=*` tags as ground truth on tagged ways.
- Assumptions and constraints:
  - Exclude stationary periods: continuous ~0 mg indicates no movement.
  - Treat >800 mg as outliers; focus on 50–600 mg range.
  - Most scooter travel falls into excellent/good/intermediate; prolonged high-mg stretches imply bad.
  - Use smoothed values to suppress outliers; raw outlier analysis may combine photos in the future (requires privacy/legal review).
- Outputs:
  - `output/calibrated_thresholds.json`: chosen mg thresholds for excellent/good/intermediate (else bad).
  - `output/calibration_report.md`: thresholds, agreement on tagged ways, confusion matrix, and proposal deltas.

All visualizations (including the path gradient) use the calibrated thresholds. "Intermediate" is the primary target class and is colored green on the path; good/excellent use blue/cyan; bad uses red. We do not render a separate "very_bad" class.

### Agreement metrics (predicted vs OSM)
- We compute per-point predictions with calibrated thresholds and compare to existing `smoothness=*` where present.
- Per-way metrics in CSV:
  - `predicted_way_class` (majority vote of per-point predictions on the way)
  - `osm_match` (predicted class equals existing OSM tag)
  - `osm_match_pct` (share of matching points on tagged ways)
- The Mapbox "agreement" layer visualizes agreement differences by color (see toggles above). Clicking a segment shows existing tag, predicted class, match status/%, and a link to OSM.

### Optional: 4‑panel z-series analysis
- A 4‑panel plot function is available to visualize calibration and agreement at a glance: `plot_smoothness_panels_4(df, calibrated_thresholds, point_osm_labels)`
  1) Raw z proxy (z_std_mg)
  2) Smoothed z with calibrated threshold bands
  3) Predicted class per point (calibrated)
  4) Correlation strip (green=match, red=mismatch, gray=untagged)

## Notes
- Corridor clipping prevents assigning points to parallel/nearby ways not ridden (“hallucinated” ways)
- Overpass retries across multiple public endpoints and increases timeout for robustness
- The workflow reuses core functions from `prepare_smoothness_from_ride.py` and the orchestrator

## Next steps
- Manually review `output/smoothness_proposals.html`
- Filter CSV (e.g., `coverage_pct>=0.7` and `agree_pct>=0.7`)
- Batch-apply via `scripts/OSM/apply_smoothness_batch.py` (uses `osm_edit.py set-tag -y` under the hood)
