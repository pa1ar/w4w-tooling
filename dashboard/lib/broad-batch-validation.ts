export interface ReviewedBatchRow {
  way_id: number;
  value: string;
  manual_reviewed?: boolean;
}

export interface ExpectedBatchItem {
  way_id: number;
  proposed_value: string;
  status: string;
}

export function validateReviewedBatchRow(
  row: ReviewedBatchRow,
  expected: ExpectedBatchItem | undefined,
): string | null {
  if (!row.manual_reviewed) return `way ${row.way_id} was not manually reviewed`;
  if (!expected) return `way ${row.way_id} is not in this batch`;
  if (expected.status === "pushed") return `way ${row.way_id} was already pushed`;
  if (row.value !== expected.proposed_value) {
    return `way ${row.way_id} value does not match the reviewed proposal`;
  }
  return null;
}
