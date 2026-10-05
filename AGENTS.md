# W4W Tooling

- W4W OP in Craft, the durable project page with state, decisions, features and ops. Start here: craftdocs://open?spaceId=8ac88104-eb82-9c72-9014-d28fdea88b25&blockId=2999DD75-F660-429F-BCBD-B9AC2FC6E46F
- Tasks: Pavel intents live on The Board in Craft, project W4W OP. Dev issues live in this repo as GitHub issues. Linear and LABS Issues are retired.

## Project

Python pipeline + CLIs for Wheels4Wheels OSM smoothness proposals.

Main entrypoint:

```bash
uv run python scripts/OSM/OSM_smoothness_workflow.py \
  --input example_data/258276934-579126.json \
  --out-csv output/smoothness_proposals.csv \
  --out-map output/smoothness_proposals.html
```

Batch:

```bash
uv run python scripts/OSM/select_rides.py --top-n 10
uv run python scripts/OSM/run_pipeline_batch.py
```

OSM auth/edit:

```bash
uv run python scripts/OSM/osm_edit.py login
uv run python scripts/OSM/osm_edit.py set-tag --way-id 123 --key smoothness --value good
```

## Environment

- Python 3.12.8+
- Use `uv`
- `.env` required for `MAPBOX_ACCESS_TOKEN`
- OSM OAuth env only needed for `osm_edit.py`
- Generated output in `output/`
- Raw telemetry in `telemetry_json/`
- Dashboard demo app in `dashboard/`; Vercel demo reads `dashboard/demo-output/output`

## Data Safety

- Never commit `.env`, `.osm_token.json`, raw telemetry, generated output, or OAuth credentials.
- `example_data/` is the only committed telemetry sample.
- Review generated maps before publishing; HTML may embed public Mapbox tokens.

## Code Notes

- Python `snake_case.py`
- No AI attribution in commits.
- Commit message short: `feat:`, `fix:`, `chore:` ok.
- Verify before done: run command, read output, state result.
- Fix root cause. No masking hacks.
- Matplotlib backend: set `matplotlib.use("Agg")` before pyplot.
- Telemetry already sorted by device uptime.
- Photo timestamps are unreliable; use sequence numbers only.

## Repo Shape

```text
scripts/OSM/       pipeline + OSM CLIs
dashboard/         Next.js review dashboard + committed demo artifacts
example_data/      committed sample ride
telemetry_json/    local raw telemetry, gitignored
output/            generated artifacts, gitignored
pending_upload/    local YAML upload manifests, gitignored
docs/reference/    data/unit/reference notes
```
