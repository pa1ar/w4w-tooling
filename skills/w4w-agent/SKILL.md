---
name: w4w-agent
description: Operate Wheels4Wheels telemetry processing, the local review dashboard, and guarded OpenStreetMap smoothness uploads. Use for W4W setup, ride processing, proposal review, OSM OAuth, user-confirmed pushes, audit verification, or corrective changesets.
---

# W4W agent

Operate from the W4W tooling repository root. Read
`docs/reference/2026-08-14-guarded-osm-upload-trial.md` before an OSM push or
reversal.

## Core workflow

1. Keep raw telemetry local and gitignored.
2. Generate proposals and review the map, coverage, agreement, bad-run evidence,
   and current OSM tags.
3. Start the local dashboard and verify `osm · authed`.
4. Select a small, auditable set of ways. Default to one way for the first push.
5. Require the user to click the push button and accept its confirmation.
6. Verify each live OSM way and closed changeset after the push.
7. Check `/logs` and `output/upload_log.jsonl` for the local audit record.

Never interpret a generated proposal as an upload-ready claim. Keep the final
external OSM write under explicit human control.

For systematic or external-data edits, record the user's automation approval but
do not treat it as a replacement for candidate validation or the OSM community
process. Prepare offline first and keep every manifest at `upload_allowed=false`
until all gates pass.

## OAuth

Use the exact redirect registered for the OSM application. For the local CLI:

```ini
OSM_REDIRECT_URI=http://127.0.0.1:8765/callback
OSM_SCOPES=write_api
```

Authenticate with:

```bash
uv run python scripts/OSM/osm_edit.py login
chmod 600 .osm_token.json
```

Treat `401` as unauthorized. A `403` from `/api/0.6/user/details.json` can mean
the token is valid but limited to `write_api`; do not force broader scopes only
to display an identity badge.

## Push safety

- Fetch the current way before editing.
- Use `--create-only` for gap filling and refuse every existing target tag, even
  when the command is auto-confirmed.
- A single guarded trial may use one changeset for one way. For a systematic run,
  group approved objects into small geographic changesets so history stays readable.
- For automated edits, include the required `mechanical=yes` or `bot=yes`, a useful
  comment, and a public `description=*` documentation link.
- After an ambiguous error, inspect the live way and local log before retrying.
- Do not commit `.env`, `.osm_token.json`, telemetry, `output/`, or
  `pending_upload/`.

## Systematic batch preparation

Read `docs/osm/uploads/2026-08-broad-batch-plan.md` and the current OSM
Import Guidelines plus Automated Edits code before a multi-way run.

Prepare the full broad local ledger with:

```bash
uv run python scripts/OSM/prepare_upload_batches.py
```

The command refreshes current public OSM state, excludes existing
`smoothness=*`, and writes preflight-only manifests under
`pending_upload/osm-broad-2026-08/`. It never writes to OSM. It prioritizes the
experimental conservative subset, then the remaining broad candidates. Do not
turn the citywide spatial estimates into uploads until every row has been
validated by the ride-level pipeline.

Before a systematic upload, require:

1. source permission and license confirmation;
2. public method, sample, opt-out, and revert documentation;
3. applicable community review and waiting period completed;
4. exact manifest validation after a fresh OSM-state check;
5. regional changeset grouping and required metadata implemented.

Pavel approved eventual automatic processing of the full broad gap-only pool on
2026-08-14. That internal approval applies only to candidates that pass every
gate, remain untagged, and stay inside the community-reviewed scope. It removes
the need for a repeated per-way click after the gates pass; it does not authorize
uploads before then.

## Audit contract

Require successful upload records to include:

- `ride_id`, `way_id`, `key`, and applied `value`
- `before_tag_present` and `before_tag_value`
- `before_version` and `before_changeset_id`
- `after_version`
- `status`, `changeset_id`, and `changeset_url`

Treat `output/upload_log.jsonl` as append-only operational evidence. It is
gitignored and local, so capture durable summaries in tracked documentation.
Keep older log entries readable when fields are absent.

For a successful way in the active broad plan, require `ledger_updated=true` in
the push response. Confirm that its batch JSON and `upload_ledger.md` show
`status=pushed`, upload time, before/after versions, and the changeset link. If
propagation fails, preserve the authoritative upload log, inspect
`output/ledger_sync_errors.jsonl`, and reconcile the ledger before continuing.

## Reversal

Do not call a closed changeset revoked or deleted. Create a corrective changeset.

1. Read the recorded prior value or absence and prior OSM version.
2. Fetch the current way and detect edits made after the W4W changeset.
3. Restore only the W4W tag, not the complete historical way.
4. Require explicit human approval for the corrective write.
5. Log and link the corrective changeset.

The dashboard currently has no revert button and the CLI has no tag-removal
command. Do not claim one-click reversal.

Audit data makes corrections traceable, but does not make a mass edit easily
reversible after other mappers change the same objects.

## Verified reference trial

On 2026-08-14, ride `257673408` pushed only way `987191899` as
`smoothness=intermediate` with 95% coverage and 100% agreement. OSM changeset
`187435440` changed the way from version 13 to 14. The prior state had no
`smoothness` tag. Way `1456825967` stayed unselected at 87% agreement. The local
audit displays `absent -> intermediate`, `v13 -> v14`, with the public changeset
link.
