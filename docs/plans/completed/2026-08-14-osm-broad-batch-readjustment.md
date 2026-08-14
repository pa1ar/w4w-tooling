# Broad OSM batch readjustment

Craft issue: `1SS-446`

## Outcome

Replace the 312-row conservative-only plan with the full 2,399-row broad
gap-only source pool. Preserve the conservative research subset as the first
priority tier.

## Scope

- Select `potential=True` rows, all of which lacked `smoothness=*` in the source
  snapshot.
- Refresh all source candidates against current public OSM state.
- Exclude every way that now has `smoothness=*` or is missing.
- Sort the conservative subset first, then pathway types and evidence strength.
- Record Pavel's internal approval for eventual automatic processing of the full
  eligible pool.
- Keep `upload_allowed=false` until validation and OSM community gates pass.
- Generate eight local review batches from August 14 through August 25.
- Correct the tracked plan, runbook, README, and supplied skill.

## Verification

- Live refresh: 2,398 unique current gaps, 311 high-confidence first, then 2,087
  broad candidates; one already-tagged trial excluded and no ways missing.
- Every generated item has operator approval recorded, `upload_allowed=false`,
  and no observed live `smoothness` value.
- Six Python tests, three dashboard tests, and dashboard lint pass.
- No OSM writes were made.
