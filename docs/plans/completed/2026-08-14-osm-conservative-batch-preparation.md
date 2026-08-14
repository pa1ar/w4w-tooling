# Guarded OSM batch preparation

Craft issue: `1SS-446`

## Outcome

Prepare the conservative Tallinn gap candidates as deterministic, local review
batches with a per-way ledger. Do not write to OSM.

## Scope

- Start only from `conservative=True` rows in the cached citywide estimate.
- Refresh every candidate against the current public OSM API.
- Exclude ways that now have `smoothness=*` or no longer exist.
- Rank pathway types first, then intermediate proposals, evidence strength, and
  match distance.
- Split the resulting candidates over the eight weekdays from August 14 to 25,
  with 100 in the first review batch.
- Mark every row as preflight-only and blocked from upload pending ride-level
  pipeline validation and OSM community process.
- Add a hard create-only guard to every dashboard and batch CLI write.
- Update the operating reference and supplied W4W skill for scaled edits.

## Verification

- Python unit tests cover filtering, ordering, splitting, output blocking, and
  create-only safety.
- The local ledger totals were verified against refreshed OSM state.
- Dashboard tests and lint pass. The production build was deferred because the
  16 GB host was under sustained memory and CPU pressure.
- Only source, tests, and tracked documentation are committed. Generated
  candidates remain in gitignored `pending_upload/`.

## External gates

- Validate each candidate through the ride-level pipeline before exact approval.
- Document the dataset, source/licensing, method, consultation, and revert plan.
- Complete the applicable OSM import or automated-edit discussion and waiting
  period before any systematic upload.
- Group approved edits into sensible geographic changesets with required metadata.
