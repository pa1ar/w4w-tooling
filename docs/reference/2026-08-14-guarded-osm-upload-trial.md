# First guarded OSM pathway upload

Date: 2026-08-14

## Outcome

The local review dashboard completed its first user-confirmed pathway edit to
OpenStreetMap.

- Ride: `257673408`
- Path: `530155`
- Selected way: [987191899](https://www.openstreetmap.org/way/987191899)
- Applied tag: `smoothness=intermediate`
- Evidence: 95% ride coverage and 100% proposal agreement
- Changeset: [187435440](https://www.openstreetmap.org/changeset/187435440)
- OSM user: `pa1ar`
- Changeset state: closed, one changed object
- Way transition: version 13 to version 14

Way `1456825967` remained unselected because its 87% agreement was below the
default 90% review threshold.

## What changed in the tooling

Commit `06ca149` hardened the review and push path:

- Raised the default agreement threshold from 70% to 90%, leaving the weaker
  second candidate unchecked.
- Ran the push through the repository Python environment instead of a global
  `python3`.
- Added a current Overpass fallback, request identity, and support for cached or
  pathway-filtered way responses.

Commit `8404a09` added reversible local audit state:

- The CLI emits machine-readable snapshots immediately before and after a tag
  write.
- `output/upload_log.jsonl` stores prior tag presence/value, prior way version,
  resulting version, status, changeset ID, and changeset URL.
- `/logs` renders the transition and public OSM evidence.
- The first record was backfilled as `absent -> intermediate`, `v13 -> v14`.
- Parser tests cover absent tags, overwritten values, malformed output, and
  legacy output.

## OAuth setup learned

The original authorization failed because `.env` used a Vercel redirect that
did not match the registered OSM application.

For the local CLI, register and use this exact redirect URI:

```ini
OSM_REDIRECT_URI=http://127.0.0.1:8765/callback
OSM_SCOPES=write_api
```

Run:

```bash
uv run python scripts/OSM/osm_edit.py login
chmod 600 .osm_token.json
```

The local callback server receives the authorization code and saves the token
to `.osm_token.json`. The file and `.env` are gitignored. A `write_api`-only
token may return `403` for user details because it lacks identity/read scopes;
that does not mean the write token is invalid.

## Guarded upload sequence

1. Start the local dashboard and open the ride review.
2. Confirm the dashboard shows `osm · authed`.
3. Review the current OSM way, existing tags, proposed value, coverage, and
   agreement.
4. Select only the intended way.
5. Let the user click `push 1 to osm` and accept the browser confirmation.
6. Check the Pushed tab and `output/upload_log.jsonl`.
7. Verify the live way and closed changeset through the public OSM API or the
   links in `/logs`.
8. If a request fails ambiguously, inspect the live way and local log before
   retrying. Never create a second changeset blindly.

Each selected way creates one OSM changeset. Nothing is written to OSM until
the user confirms the push.

## Audit and reversal

Closed OSM changesets are immutable. Reversal means creating a corrective
changeset that restores the prior value or removes the tag if it was absent.

Before reversing:

1. Read the recorded prior tag state and prior version.
2. Fetch the current live way and check whether another mapper changed it.
3. Restore only the tag changed by W4W. Do not restore the entire historical
   object and overwrite unrelated edits.
4. Record and link the corrective changeset.

For changeset `187435440`, way version 13 had no `smoothness` tag. A reversal
would therefore remove only `smoothness=intermediate` in a new changeset.

The current dashboard has no revert button and the CLI has no tag-removal
command. Reversal is recoverable from the audit record and OSM history, but it
remains a deliberate manual operation.

## Local retention boundary

`output/upload_log.jsonl` is append-only during normal operation, but `output/`
is gitignored. It is local evidence, not a durable repository record. Export or
copy approved audit summaries into tracked documentation when they must survive
machine cleanup or support stakeholder reporting.

Never commit raw telemetry, `.env`, `.osm_token.json`, generated `output/`, or
`pending_upload/` manifests.
