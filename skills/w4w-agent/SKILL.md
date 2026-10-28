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
4. For the prepared broad queue, open `/batches/1`, inspect the exact OSM paths,
   and select only the legitimate ones. Selections persist locally and begin empty.
5. Require the user to click the push button and accept its confirmation.
6. Verify each live OSM way and closed changeset after the push.
7. Check `/logs` and `output/upload_log.jsonl` for the local audit record.

Never interpret a generated proposal as an upload-ready claim. Keep the final
external OSM write under explicit human control.

For multi-way work, treat every selected path as manually reviewed. The user's
single confirmation may start the selected queue, but every item must still pass
the live create-only check and be logged separately.

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
- Create one changeset per reviewed path with a transparent `[w4w]` comment and
  the authenticated operator account.
- After an ambiguous error, inspect the live way and local log before retrying.
- Do not commit `.env`, `.osm_token.json`, telemetry, `output/`, or
  `pending_upload/`.

## Systematic batch preparation

Read `docs/osm/uploads/2026-08-broad-batch-plan.md` before a multi-way run.

Prepare the full broad local ledger with:

```bash
uv run python scripts/OSM/prepare_upload_batches.py
```

The command refreshes current public OSM state, excludes existing
`smoothness=*`, captures the live public tags and exact way geometry, and writes
review manifests under `pending_upload/osm-broad-2026-08/`. It never writes to
OSM. It prioritizes the experimental conservative subset, then the remaining
broad candidates.

The dashboard exposes these manifests as a path review queue. The operator
checks the map and evidence, explicitly selects legitimate paths, and starts the
selected queue with one confirmation. Requests run sequentially and stop on the
first conflict, upload error, or ledger error.

For the August 2026 broad batch, Pavel confirmed on 2026-08-14 that
Bolt permits publishing telemetry-derived smoothness tags to OSM.
Treat this source-permission gate as complete; raw telemetry remains private.

Pavel approved processing the full broad gap-only pool on 2026-08-14 after he
manually reviews and selects the paths. Each selected path must remain untagged
at write time. Changesets use the `[w4w]` comment and Pavel's authenticated OSM
account; no regional grouping is used.

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

Publication threshold for way-level tags: at least 70% way coverage and at
least two distinct rides, where a ride counts only if it covers at least 10%
of the way on its own. Count duplicated telemetry files once. Recheck uploaded
ways with `scripts/OSM/recheck_uploaded_ways.py` before any new batch.

On 2026-08-14, ride `257673408` pushed only way `987191899` as
`smoothness=intermediate` with 95% coverage and 100% agreement. OSM changeset
`187435440` changed the way from version 13 to 14. The prior state had no
`smoothness` tag. Way `1456825967` stayed unselected at 87% agreement. The local
audit displays `absent -> intermediate`, `v13 -> v14`, with the public changeset
link.

## Verified batch 1

On 2026-08-14, Pavel manually selected the 99 remaining paths in broad batch 1.
The queue completed with 100 of 100 unique ways pushed across 100 changesets,
including the already recorded first path. The batch contains 76
`smoothness=intermediate` and 24 `smoothness=bad` edits. The local upload log
recorded 100 successful batch rows, no upload errors, and no ledger-sync errors.
A fresh public OSM multi-fetch returned all 100 ways and confirmed that every
live tag value and latest changeset ID matched the batch ledger.
