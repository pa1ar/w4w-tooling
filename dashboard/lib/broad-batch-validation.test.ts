import { describe, expect, test } from "bun:test";
import { validateReviewedBatchRow } from "./broad-batch-validation";

const expected = { way_id: 42, proposed_value: "intermediate", status: "needs_pipeline_validation" };

describe("validateReviewedBatchRow", () => {
  test("accepts a reviewed matching candidate", () => {
    expect(validateReviewedBatchRow(
      { way_id: 42, value: "intermediate", manual_reviewed: true },
      expected,
    )).toBeNull();
  });

  test("rejects an unchecked candidate", () => {
    expect(validateReviewedBatchRow(
      { way_id: 42, value: "intermediate" },
      expected,
    )).toContain("not manually reviewed");
  });

  test("rejects a changed proposal or a pushed candidate", () => {
    expect(validateReviewedBatchRow(
      { way_id: 42, value: "bad", manual_reviewed: true },
      expected,
    )).toContain("does not match");
    expect(validateReviewedBatchRow(
      { way_id: 42, value: "intermediate", manual_reviewed: true },
      { ...expected, status: "pushed" },
    )).toContain("already pushed");
  });
});
