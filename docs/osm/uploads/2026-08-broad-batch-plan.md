# August 2026 broad OSM batch plan

Date prepared: 2026-08-14

## Decision and current scope

Pavel approved eventual automatic processing of the full broad gap-only source
pool, with the high-confidence subset first.

The source snapshot contains 2,399 broad candidate ways. Every source row lacked
`smoothness=*` when the estimate was generated. A live, read-only OSM refresh at
`2026-08-14T14:08:09Z` found:

- 2,398 ways still without `smoothness=*`
- 1 excluded way already tagged: way `987191899`, the first W4W trial
- 0 missing or deleted ways
- 311 current high-confidence candidates
- 2,087 remaining broad candidates
- 1,856 proposed `intermediate`, 542 proposed `bad`
- 800 current pathway types: `cycleway`, `footway`, `path`, or `pedestrian`

The 312 source-row high-confidence tier is an experimental research safeguard,
not the production pipeline's official threshold. It requires at least 70%
modeled coverage and evidence from at least two rides. The full broad pool uses
at least 30% modeled coverage, at least one ride, and a valid proposal.

## Priority and review schedule

Rows are sorted by confidence tier first. Within a tier, pathway types precede
other highways, followed by proposal and evidence strength.

| Batch | Planned review date | Candidates | High confidence | Broad | State |
|---:|:---|---:|---:|---:|:---|
| 1 | 2026-08-14 | 100 | 100 | 0 | preflight only |
| 2 | 2026-08-17 | 329 | 211 | 118 | preflight only |
| 3 | 2026-08-18 | 329 | 0 | 329 | preflight only |
| 4 | 2026-08-19 | 328 | 0 | 328 | preflight only |
| 5 | 2026-08-20 | 328 | 0 | 328 | preflight only |
| 6 | 2026-08-21 | 328 | 0 | 328 | preflight only |
| 7 | 2026-08-24 | 328 | 0 | 328 | preflight only |
| 8 | 2026-08-25 | 328 | 0 | 328 | preflight only |
| | Total | 2,398 | 311 | 2,087 | |

The active local per-way ledger and JSON manifests are in
`pending_upload/osm-broad-2026-08/`. The older conservative-only directory is
superseded. Generated operational data remains gitignored. Actual successful
edits continue to be recorded in `output/upload_log.jsonl`; approved audit
summaries must be copied into tracked documentation for durable reporting.

After each successful upload, the dashboard propagates the upload event into the
matching batch JSON row and rebuilds `summary.json` and `upload_ledger.md`. The
row becomes `pushed` and records the changeset link, upload time, ride ID,
applied value, prior tag/version state, and resulting version. Propagation is
idempotent. A propagation failure is returned by the push API and appended to
`output/ledger_sync_errors.jsonl`; the primary upload log remains authoritative.

## Approval boundary

Pavel's approval authorizes automatic processing of every source candidate that:

1. passes candidate-level pipeline validation;
2. still lacks `smoothness=*` immediately before the write;
3. remains inside the documented and community-reviewed scope.

It does not authorize uploading a mismatched candidate, overwriting a newly added
tag, ignoring an opt-out, or proceeding over unresolved community concerns. Every
manifest records the internal approval and keeps `upload_allowed=false` until the
external gates pass.

## Required external gates

Treat the run as a systematic external-data edit and satisfy both the import and
automated-edit process unless the OSM community or Data Working Group confirms a
narrower classification.

Source permission is confirmed. On 2026-08-14 Pavel confirmed that
Bolt permits publishing telemetry-derived smoothness tags to
OpenStreetMap. Raw telemetry remains private.

1. Re-run each candidate through the production ride-level pipeline and retain
   the supporting ride IDs and evidence.
2. Publish the method, sample output, consultation, opt-out, and revert plan.
3. Complete local/community review. The current Import Guidelines allow an import
   to start only after 14 days and after all concerns are addressed.
4. Use a suitable account and changeset metadata, including `mechanical=yes` or
   `bot=yes` and a public `description=*` documentation link when applicable.
5. Group approved objects into sensible small geographic changesets.
6. Refresh OSM state immediately before every write. The create-only guard must
   refuse any way that gained `smoothness=*` after preparation.

August 25 remains the offline review target. It cannot be the systematic
upload-completion date because public review has not begun.

## Reversal boundary

The W4W audit captures prior tag values, versions, and changesets, which makes a
corrective changeset traceable. This reduces risk but does not make mass editing
freely reversible. OSM warns that rollback can become hard or impossible after
other mappers edit the same objects. Reversal readiness is a gate, not a substitute
for validation and community approval.

## Current tooling boundary

- The dashboard and legacy batch CLI invoke `--create-only`.
- Generated manifests carry the operator approval, `upload_allowed=false`, and no
  upload command.
- The current editor still creates one changeset per way and lacks systematic
  `mechanical` and `description` tags. A regional systematic uploader must be built
  only after the documented scope is accepted.
- No OSM writes were made while preparing or readjusting this plan.

## Policy sources

- [OSM Import Guidelines](https://wiki.openstreetmap.org/wiki/Import_guidelines)
- [OSM Automated Edits code of conduct](https://wiki.openstreetmap.org/wiki/Automated_Edits/Code_of_Conduct)
- [OSMF API Usage policy](https://operations.osmfoundation.org/policies/api/)
