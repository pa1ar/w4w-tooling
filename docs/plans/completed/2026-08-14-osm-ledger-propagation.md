# OSM ledger propagation

Craft issue: `1SS-446`

## Outcome

Every successful dashboard upload automatically updates the active broad batch
manifest, summary, and Markdown ledger with the changeset URL and audit fields.

## Contract

- Append `output/upload_log.jsonl` first as the durable local event record.
- Propagate only successful uploads that match a planned way.
- Mark the row `pushed` and store upload time, changeset ID and URL, applied
  value, ride ID, before state, and after version.
- Rebuild the Markdown ledger from JSON manifests so links and counts agree.
- Update summary pushed and remaining counts.
- Make writes atomic and propagation idempotent.
- Return ledger propagation state in the push response and surface failures in
  the dashboard.

## Verification

- Four dashboard tests pass, including changeset propagation and retry behavior.
- Dashboard lint passes.
- No OSM writes were made.
