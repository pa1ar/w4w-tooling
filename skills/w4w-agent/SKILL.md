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
- Do not overwrite an existing tag without an explicit review decision.
- Use one changeset per way so every result is independently auditable.
- After an ambiguous error, inspect the live way and local log before retrying.
- Do not commit `.env`, `.osm_token.json`, telemetry, `output/`, or
  `pending_upload/`.

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

## Reversal

Do not call a closed changeset revoked or deleted. Create a corrective changeset.

1. Read the recorded prior value or absence and prior OSM version.
2. Fetch the current way and detect edits made after the W4W changeset.
3. Restore only the W4W tag, not the complete historical way.
4. Require explicit human approval for the corrective write.
5. Log and link the corrective changeset.

The dashboard currently has no revert button and the CLI has no tag-removal
command. Do not claim one-click reversal.

## Verified reference trial

On 2026-08-14, ride `257673408` pushed only way `987191899` as
`smoothness=intermediate` with 95% coverage and 100% agreement. OSM changeset
`187435440` changed the way from version 13 to 14. The prior state had no
`smoothness` tag. Way `1456825967` stayed unselected at 87% agreement. The local
audit displays `absent -> intermediate`, `v13 -> v14`, with the public changeset
link.
