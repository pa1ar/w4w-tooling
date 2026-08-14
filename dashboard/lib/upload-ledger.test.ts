import { afterEach, describe, expect, test } from "bun:test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { propagateUploadToLedger } from "./upload-ledger";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => (
    fs.rm(directory, { recursive: true, force: true })
  )));
});

describe("propagateUploadToLedger", () => {
  test("adds the changeset and audit fields to JSON, summary, and Markdown", async () => {
    const ledgerDir = await fs.mkdtemp(path.join(os.tmpdir(), "w4w-ledger-"));
    temporaryDirectories.push(ledgerDir);
    await fs.writeFile(
      path.join(ledgerDir, "batch-01-2026-08-14.json"),
      JSON.stringify({
        batch: 1,
        planned_review_date: "2026-08-14",
        items: [{
          rank: 1,
          way_id: 123,
          confidence_tier: "high_confidence",
          highway: "footway",
          proposed_value: "intermediate",
          rides: 3,
          coverage_pct: 100,
          observed_version: 7,
          status: "needs_pipeline_validation",
          upload_allowed: false,
        }],
      }),
    );
    await fs.writeFile(
      path.join(ledgerDir, "summary.json"),
      JSON.stringify({ live_untagged_preflight_candidates: 1 }),
    );

    const result = await propagateUploadToLedger({
      ts: "2026-08-14T14:30:00Z",
      ride_id: "257",
      way_id: 123,
      key: "smoothness",
      value: "intermediate",
      status: "ok",
      changeset_id: "999",
      changeset_url: "https://www.openstreetmap.org/changeset/999",
      before_version: 7,
      before_tag_present: false,
      before_tag_value: null,
      after_version: 8,
    }, ledgerDir);

    const manifest = JSON.parse(
      await fs.readFile(path.join(ledgerDir, "batch-01-2026-08-14.json"), "utf8"),
    );
    const summary = JSON.parse(await fs.readFile(path.join(ledgerDir, "summary.json"), "utf8"));
    const ledger = await fs.readFile(path.join(ledgerDir, "upload_ledger.md"), "utf8");
    expect(result).toMatchObject({ matched: true, updated: true });
    expect(manifest.items[0]).toMatchObject({
      status: "pushed",
      changeset_id: "999",
      changeset_url: "https://www.openstreetmap.org/changeset/999",
      uploaded_at: "2026-08-14T14:30:00Z",
      before_version: 7,
      after_version: 8,
    });
    expect(summary).toMatchObject({ pushed_candidates: 1, remaining_candidates: 0 });
    expect(ledger).toContain("[999](https://www.openstreetmap.org/changeset/999)");
    expect(ledger).toContain("| pushed |");

    await propagateUploadToLedger({
      ts: "2026-08-14T14:30:00Z",
      ride_id: "257",
      way_id: 123,
      key: "smoothness",
      value: "intermediate",
      status: "ok",
      changeset_id: "999",
      changeset_url: "https://www.openstreetmap.org/changeset/999",
    }, ledgerDir);
    const afterRetry = JSON.parse(
      await fs.readFile(path.join(ledgerDir, "summary.json"), "utf8"),
    );
    const manifestAfterRetry = JSON.parse(
      await fs.readFile(path.join(ledgerDir, "batch-01-2026-08-14.json"), "utf8"),
    );
    expect(afterRetry).toMatchObject({ pushed_candidates: 1, remaining_candidates: 0 });
    expect(manifestAfterRetry.items[0]).toMatchObject({ before_version: 7, after_version: 8 });
  });
});
