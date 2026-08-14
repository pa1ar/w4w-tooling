# OSM Upload Script

This script allows you to upload surface smoothness data to OpenStreetMap via the OSM API v0.6 using OAuth 2.0 authentication.

## Prerequisites

1. **OpenStreetMap Account**: You need an OSM account with editing permissions
2. **Registered OAuth Application**: Register your app at https://www.openstreetmap.org/oauth2/applications
   - Required permissions: `write_api`
   - Local CLI redirect URI: `http://127.0.0.1:8765/callback`
   - The registered URI and `OSM_REDIRECT_URI` must match exactly
3. **Mapbox Token** (for map-matching): create a token in your Mapbox account

## Setup

### 1. Install Dependencies

Using uv (recommended):

```bash
uv sync
```

Or using pip:

```bash
pip install requests requests-oauthlib python-dotenv lxml
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and fill in your OAuth credentials from the OSM OAuth application page:

```ini
OSM_CLIENT_ID=your_client_id_here
OSM_CLIENT_SECRET=your_client_secret_here
OSM_REDIRECT_URI=http://127.0.0.1:8765/callback
OSM_SCOPES=write_api

# OSM API endpoints (leave as-is for production)
OSM_BASE_URL=https://api.openstreetmap.org
OSM_OAUTH_AUTHORIZE_URL=https://www.openstreetmap.org/oauth2/authorize
OSM_OAUTH_TOKEN_URL=https://www.openstreetmap.org/oauth2/token
MAPBOX_ACCESS_TOKEN=your_mapbox_access_token_here
```

**Important**: Never commit `.env` to version control. It's already in `.gitignore`.

## Usage

### Step 1: Authenticate (One-time setup)

Run the login command:

```bash
uv run python scripts/OSM/osm_edit.py login
```

This will:
1. Print an authorization URL
2. Open it in your browser (or copy-paste it)
3. You'll authorize the application on OSM
4. OSM redirects to the temporary local callback server
5. The script exchanges the code for an access token
6. Token is saved to `.osm_token.json` (also gitignored)
7. Set the token file to owner-only permissions with `chmod 600 .osm_token.json`

If a non-local redirect is configured, the CLI falls back to manual code or
redirect-URL paste. Do not use a deployment URL unless that exact URI is
registered with the OSM application.

A `write_api`-only token may return `403` from the OSM user-details endpoint
because it lacks identity/read scopes. The dashboard treats this as
authenticated but scope-limited.

## Audit and reversal

Dashboard pushes append to `output/upload_log.jsonl` and are visible at
`/logs`. New records capture the prior tag presence/value and way version, the
resulting version, and the public changeset link.

OSM changesets cannot be deleted after closing. Restore a prior state with a
new corrective changeset after checking the current live way. Restore only the
tag changed by W4W so later edits from other mappers are preserved.

See `docs/reference/2026-08-14-guarded-osm-upload-trial.md` for the verified
first pathway upload and the complete guarded runbook.

### Step 2: Edit Ways

Once authenticated, you can modify ways:

```bash
uv run python scripts/OSM/osm_edit.py set-tag \
  --way-id 123456 \
  --key smoothness \
  --value intermediate \
  --comment "W4W: add surface smoothness from scooter telemetry"
```

#### Arguments

- `--way-id`: OSM way ID (required, or use `--lat`/`--lon`)
- `--lat`: Latitude (alternative to `--way-id`, requires `--lon`)
- `--lon`: Longitude (required when using `--lat`)
- `--radius`: Search radius in meters when using coordinates (default: 20)
- `-y`, `--yes`: Auto-confirm way selection without prompting (useful for batch processing)
- `--key`: Tag key to set/update (required)
- `--value`: Tag value (required)
- `--comment`: Changeset comment (optional, defaults to "W4W: update way tags")

#### Examples

Add smoothness tag:
```bash
uv run python scripts/OSM/osm_edit.py set-tag \
  --way-id 234567 \
  --key smoothness \
  --value good \
  --comment "W4W: surface quality from telemetry data"
```

Update surface tag:
```bash
uv run python scripts/OSM/osm_edit.py set-tag \
  --way-id 234567 \
  --key surface \
  --value asphalt \
  --comment "W4W: verified surface type"
```

## Finding Way IDs

### Method 1: Programmatically (Recommended)

Use the built-in `find-way` command with coordinates:

```bash
uv run python scripts/OSM/osm_edit.py find-way --lat 50.328132 --lon 8.738048
```

This will:
- Query the Overpass API to find ways near the coordinates
- Display all matching ways with their details (name, type, surface, existing tags)
- Let you select the correct way interactively
- Check if the way already has a smoothness tag
- Give you the exact command to edit it

Example output:
```
Searching for ways near (50.328132, 8.738048) within 20m radius...

Found 1 way(s):

1. Way 313853519: Hardbäumchesweg
   Type: track
   Surface: compacted
   Track type: grade2

Use way 313853519? [Y/n]: y

======================================================================
Selected way ID: 313853519
======================================================================
This way does not have a smoothness tag yet.

View on OSM: https://www.openstreetmap.org/way/313853519
```

You can also adjust the search radius:
```bash
uv run python scripts/OSM/osm_edit.py find-way --lat 50.328132 --lon 8.738048 --radius 50
```

For non-interactive use (e.g., in scripts), use the `-y` flag to auto-confirm:
```bash
uv run python scripts/OSM/osm_edit.py find-way --lat 50.328132 --lon 8.738048 -y
```

### Method 2: Directly in set-tag Command

You can provide coordinates directly in the `set-tag` command:

```bash
uv run python scripts/OSM/osm_edit.py set-tag \
  --lat 50.328132 \
  --lon 8.738048 \
  --key smoothness \
  --value intermediate \
  --comment "W4W: add surface smoothness"
```

This will find the way and set the tag in one step.

For automated/batch processing without prompts, add the `-y` flag:
```bash
uv run python scripts/OSM/osm_edit.py set-tag \
  --lat 50.328132 \
  --lon 8.738048 \
  --key smoothness \
  --value intermediate \
  --comment "W4W: add surface smoothness" \
  -y
```

### Method 3: Manually via OSM Website

1. Go to https://www.openstreetmap.org/
2. Navigate to your area of interest
3. Click on "Query Features" (question mark icon on right sidebar)
4. Click on a road segment
5. The way ID will be shown in the sidebar (e.g., "Way 313853519")

Example for your coordinates:
- https://www.openstreetmap.org/way/313853519

## OSM Smoothness Tag Values

The `smoothness` tag describes the quality of the surface. Standard values (from best to worst):

| Value | Description | W4W Mapping (z-std mg) |
|-------|-------------|------------------------|
| `excellent` | Perfect surface, no impedance | < 50 mg |
| `good` | Minor surface imperfections | 50-100 mg |
| `intermediate` | Some issues, suitable for city bikes, wheelchairs, scooters | 100-200 mg |
| `bad` | Degraded surface, challenging for wheelchairs | 200-400 mg |
| `very_bad` | Very rough surface | > 400 mg |
| `horrible` | Impassable for most vehicles | - |
| `very_horrible` | Extremely rough | - |
| `impassable` | Not traversable | - |

Reference: https://wiki.openstreetmap.org/wiki/Key:smoothness

## Prepare smoothness proposals from a ride

Use the workflow to take a ride file (CSV or JSON), smooth/classify, map-match via Mapbox, fetch OSM ways via Overpass (with fallbacks), and generate proposals:

```bash
uv run python scripts/OSM/OSM_smoothness_workflow.py \
  --input telemetry_json/258276934-579126.json \
  --buffer-m 18 \
  --bbox-pad 0.002 \
  --tolerance-m 25 \
  --bad-run 30 \
  --out-csv output/smoothness_proposals.csv \
  --out-map output/smoothness_proposals.html \
  --preview-html output/proposals_preview_inline.html \
  --raw-map-html output/raw_map.html
```

- Policy: tag `smoothness=intermediate` if ≥70% points are intermediate-or-better and no contiguous bad run ≥30 m; if a bad run ≥30 m is found, propose `smoothness=bad`; otherwise skip.
- The CSV contains: `way_id, proposed_value, coverage_pct, bad_run_m, agree_pct, existing_smoothness, counts, comment`.
- The HTML map colors ways by the proposed value and links to each way on OSM.
- A clickable Plotly Mapbox preview is written to `output/proposals_preview_inline.html` (segments link to the OSM way).

### Workflow CLI reference

```bash
uv run python scripts/OSM/OSM_smoothness_workflow.py --help
```

Flags (defaults in parentheses):
- `--input` (telemetry_json/258276934-579126.json): ride file path
- `--buffer-m` (18.0): corridor buffer (m) for clipping OSM ways to the ridden path
- `--bbox-pad` (0.002): padding for the Overpass query bounding box
- `--tolerance-m` (25.0): nearest-way assignment tolerance
- `--bad-run` (30.0): contiguous bad-run threshold (m)
- `--out-csv` (output/smoothness_proposals.csv): proposals CSV path
- `--out-map` (output/smoothness_proposals.html): Mapbox GL review map
- `--preview-html` (output/proposals_preview_inline.html): inline clickable preview (Plotly)
- `--raw-map-html` (output/raw_map.html): raw GPS path map
- `--smoke`: run legacy single-pass (unclipped) pipeline for quick verification
- `--no-plots`: suppress inline plotting (HTML files are still written)

Requirements:
- `.env` must include `MAPBOX_ACCESS_TOKEN`. Optional: `OVERPASS_URL` to set the primary Overpass endpoint.

Outputs:
- `output/smoothness_proposals.csv`, `output/smoothness_proposals.html`, `output/proposals_preview_inline.html`, `output/raw_map.html`

Notes:
- The workflow clips OSM ways to a narrow buffer around the map-matched trace to avoid “hallucinated” parallel ways.
- Ways that already have a `smoothness=*` tag are skipped in proposals (gap-filling policy).

## Apply proposals in batch

After reviewing and filtering the CSV (e.g., keeping rows with `coverage_pct>=0.7` and `agree_pct>=0.7`), apply in batch:

```bash
uv run python scripts/OSM/apply_smoothness_batch.py \
  --csv output/smoothness_proposals.csv \
  --min-coverage 0.7 \
  --min-agree 0.7 \
  --dry-run
```

Remove `--dry-run` when ready to upload. Each change uses our `osm_edit.py set-tag -y` command with a clear changeset comment.

## How It Works

The script follows the OSM API v0.6 workflow:

1. **Create Changeset**: Opens a new changeset to group your edits
2. **Fetch Way**: Retrieves the current way data (including version)
3. **Modify Tags**: Adds or updates the specified tag in the XML
4. **Upload Way**: Submits the modified way with the changeset ID
5. **Close Changeset**: Finalizes the edit session

## Error Handling

### 401 Unauthorized
Your token may have expired. Run `uv run python scripts/OSM/osm_edit.py login` again.

### 409 Conflict
The way was modified by someone else while you were editing. The script will tell you to fetch the latest version and try again.

### 404 Not Found
The way ID doesn't exist. Double-check the way ID.

## Current Limitations

- **Whole-way tagging**: The script applies the same tag value to the entire way
- **No granular segmentation**: Cannot tag different parts of a way with different values (would require way splitting)
- **Single tag at a time**: Each command modifies one tag

## Future Enhancements

Planned features:
1. ✅ ~~Automatic way ID lookup from GPS coordinates using Overpass API~~ (Implemented!)
2. Granular segmentation: split ways to apply different smoothness values
3. Batch processing: upload multiple ways from CSV/JSON
4. Data aggregation: compute dominant smoothness from scooter telemetry
5. Conflict detection: warn if existing smoothness tag differs significantly
6. Map-matching: align GPS traces with OSM ways for better accuracy

## References

- OSM API v0.6: https://wiki.openstreetmap.org/wiki/API_v0.6
- OAuth 2.0: https://wiki.openstreetmap.org/wiki/OAuth_2.0
- Changesets: https://wiki.openstreetmap.org/wiki/Changeset
- Smoothness key: https://wiki.openstreetmap.org/wiki/Key:smoothness

## Troubleshooting

### "Error: .env file not found"
Create `.env` file in project root with your OAuth credentials.

### "Error: Not logged in"
Run `uv run python scripts/OSM/osm_edit.py login` first.

### "Error: Failed to create changeset"
Check that your OAuth app has `write_api` permission enabled.

### Script hangs during login
Make sure you paste the FULL redirect URL, including the `code` parameter.

## Safety Notes

1. **Test first**: Consider testing on a development OSM instance
2. **Community guidelines**: Follow OSM's automated edits guidelines
3. **Data quality**: Ensure your smoothness values are accurate
4. **Attribution**: Always include meaningful changeset comments
5. **Backup**: The script doesn't create backups; OSM history tracks all changes

## License

Part of the Wheels4Wheels project.
