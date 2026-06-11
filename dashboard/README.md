# w4w review dashboard

ui for reviewing osm smoothness proposals per ride.

Two modes:

- local mode reads `../output`, can export YAML, and can push to OSM when OAuth is configured.
- demo mode reads committed `demo-output/output`, blocks YAML export, OSM push, pipeline runs, and iD editor links.

## run

```
cd w4w-tooling/dashboard
pnpm install
pnpm dev
```

opens on `http://localhost:3000`. local mode reads from the parent repo's `.env` and pipeline outputs.

Demo mode locally:

```
pnpm dev:demo
```

## vercel demo

Deploy `w4w-tooling/dashboard` as the Vercel project root.

Required env:

```
MAPBOX_ACCESS_TOKEN=...
NEXT_PUBLIC_W4W_DEMO_MODE=1
W4W_DASHBOARD_MODE=demo
```

Optional env:

```
NEXT_PUBLIC_W4W_TOOLING_REPO_URL=https://github.com/<org>/w4w-tooling
```

`vercel.json` sets the demo-mode flags by default. Do not set OSM OAuth vars on the public demo.

## prerequisites

1. repo root `.env` with `MAPBOX_ACCESS_TOKEN` + osm oauth vars (see `../.env.example`)
2. valid `../.osm_token.json` - if missing or expired, run once from repo root:
   ```
   uv run python scripts/OSM/osm_edit.py login
   ```
3. pipeline artifacts generated via:
   ```
   uv run python scripts/OSM/select_rides.py --top-n 10
   uv run python scripts/OSM/run_pipeline_batch.py
   ```
   or `POST /api/run-batch` from the dashboard (spawns both).

## flow

- landing page `/` lists selected rides from `output/batch_manifest.json`
- click "Review" on a ride -> detail page with mapbox map (iframe of pipeline's generated html) + proposals table
- adjust min-coverage / min-agree sliders to auto-include/exclude rows; manual checkboxes override
- "Export YAML" writes `pending_upload/<ride_id>.yaml` - safe, local only
- "Push to OSM" spawns `osm_edit.py set-tag` per approved row, one changeset per way. token probe runs before push; 401 blocks with terminal instructions
- every push appends to `output/upload_log.jsonl`; view at `/logs`

## state

| file | what | reset |
|------|------|-------|
| `output/selected_rides.json` | last ride selection | re-run `select_rides.py` |
| `output/batch_manifest.json` | last pipeline batch | re-run `run_pipeline_batch.py` |
| `pending_upload/*.yaml` | exported manifests | `rm pending_upload/*.yaml` |
| `output/upload_log.jsonl` | all osm pushes ever | `> output/upload_log.jsonl` (append-only by design) |

## safety

- all state is local. nothing is pushed anywhere until you click "Push to OSM" in the ui.
- each push creates one osm changeset per way (per-way granularity chosen so every change is visible on osm.org/way/<id> history independently).
- pre-flight token probe blocks pushes when expired.
- failed pipeline rides (e.g. overpass rate-limit) are surfaced as "pipeline error" on the ride list; re-run the batch to retry.
- in demo mode, server routes hard-block mutations even if the client is modified.
