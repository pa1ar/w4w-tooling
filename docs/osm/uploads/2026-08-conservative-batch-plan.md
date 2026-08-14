# August 2026 conservative OSM batch plan

Date prepared: 2026-08-14

## Readiness

Offline preparation is complete. Systematic upload is blocked.

The cached citywide estimate contains 2,399 broad potential gaps, but only 312
meet the conservative threshold. A live, read-only OSM refresh at
`2026-08-14T13:50:42Z` found:

- 311 ways still without `smoothness=*`
- 1 way already tagged: way `987191899`, the first guarded W4W trial
- 0 missing or deleted ways
- 188 proposed `intermediate`, 123 proposed `bad`
- 124 pathway types: `cycleway`, `footway`, `path`, or `pedestrian`

The 311 rows are preflight candidates, not upload-ready claims. The citywide
spatial matcher recovered only 55.4% of known ride-pipeline ways in its available
validation sample, so every candidate still needs ride-level pipeline evidence.

## Review schedule

There are eight weekdays from August 14 through August 25 after excluding the
two weekends.

| Batch | Planned review date | Candidates | State |
|---:|:---|---:|:---|
| 1 | 2026-08-14 | 100 | preflight only |
| 2 | 2026-08-17 | 31 | preflight only |
| 3 | 2026-08-18 | 30 | preflight only |
| 4 | 2026-08-19 | 30 | preflight only |
| 5 | 2026-08-20 | 30 | preflight only |
| 6 | 2026-08-21 | 30 | preflight only |
| 7 | 2026-08-24 | 30 | preflight only |
| 8 | 2026-08-25 | 30 | preflight only |
| | Total | 311 | |

The local per-way ledger and JSON manifests are in
`pending_upload/osm-conservative-2026-08/`. They are generated operational data
and remain gitignored. Actual successful edits continue to be recorded in
`output/upload_log.jsonl`; approved audit summaries must be copied into tracked
documentation for durable reporting.

## Required gates

Treat the planned run as a systematic external-data edit and satisfy both the
import and automated-edit process unless the OSM community or Data Working Group
confirms a narrower classification.

1. Re-run each candidate through the ride-level pipeline and review exact evidence.
2. Confirm the telemetry source, permission, and ODbL-compatible licensing.
3. Publish the method, sample output, consultation, opt-out, and revert plan.
4. Complete local/community review. The current Import Guidelines allow an import
   to start only after 14 days and after all concerns are addressed.
5. Use a suitable account and changeset metadata, including `mechanical=yes` or
   `bot=yes` and a public `description=*` documentation link when applicable.
6. Group approved objects into sensible small geographic changesets. Do not create
   one changeset per way at this scale.
7. Refresh OSM state immediately before every write. The create-only CLI guard must
   refuse any way that gained `smoothness=*` after preparation.

Because the public review has not begun, August 25 cannot be the upload-completion
deadline. It can remain the offline review-completion target.

## Current tooling boundary

- The dashboard and legacy batch CLI now always invoke `--create-only`.
- Generated manifests carry `upload_allowed=false` and no upload command.
- The current editor still creates one changeset per way and lacks systematic
  `mechanical` and `description` tags. It is suitable for isolated reviewed trials,
  not this 311-way run.
- No OSM writes were made while preparing this plan.

## Policy sources

- [OSM Import Guidelines](https://wiki.openstreetmap.org/wiki/Import_guidelines)
- [OSM Automated Edits code of conduct](https://wiki.openstreetmap.org/wiki/Automated_Edits/Code_of_Conduct)
- [OSMF API Usage policy](https://operations.osmfoundation.org/policies/api/)
