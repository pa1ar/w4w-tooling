import { describe, expect, test } from "bun:test";
import { parseOsmAuditSnapshots } from "./osm-audit";

describe("parseOsmAuditSnapshots", () => {
  test("captures an absent tag before a successful write", () => {
    const stdout = [
      "Fetching way 987191899...",
      'W4W_AUDIT_BEFORE:{"version":13,"changeset_id":"175363615","tag_present":false,"tag_value":null}',
      'W4W_AUDIT_AFTER:{"version":14,"changeset_id":"187435440","tag_present":true,"tag_value":"intermediate"}',
      "SUCCESS",
    ].join("\n");

    expect(parseOsmAuditSnapshots(stdout)).toEqual({
      before: {
        version: 13,
        changeset_id: "175363615",
        tag_present: false,
        tag_value: null,
      },
      after: {
        version: 14,
        changeset_id: "187435440",
        tag_present: true,
        tag_value: "intermediate",
      },
    });
  });

  test("captures an overwritten prior value", () => {
    const stdout =
      'W4W_AUDIT_BEFORE:{"version":4,"changeset_id":"12","tag_present":true,"tag_value":"good"}';

    expect(parseOsmAuditSnapshots(stdout).before?.tag_value).toBe("good");
  });

  test("ignores malformed and legacy output", () => {
    expect(parseOsmAuditSnapshots("W4W_AUDIT_BEFORE:not-json\nSUCCESS")).toEqual({});
    expect(parseOsmAuditSnapshots("SUCCESS: way 1 v1 -> v2")).toEqual({});
  });
});
