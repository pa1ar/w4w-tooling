export interface OsmAuditSnapshot {
  version: number;
  changeset_id: string | null;
  tag_present: boolean;
  tag_value: string | null;
}

export interface OsmAuditSnapshots {
  before?: OsmAuditSnapshot;
  after?: OsmAuditSnapshot;
}

const AUDIT_PREFIXES = {
  before: "W4W_AUDIT_BEFORE:",
  after: "W4W_AUDIT_AFTER:",
} as const;

export function parseOsmAuditSnapshots(stdout: string): OsmAuditSnapshots {
  const snapshots: OsmAuditSnapshots = {};

  for (const line of stdout.split("\n")) {
    for (const [phase, prefix] of Object.entries(AUDIT_PREFIXES) as [
      keyof OsmAuditSnapshots,
      string,
    ][]) {
      if (!line.startsWith(prefix)) continue;
      try {
        const parsed = JSON.parse(line.slice(prefix.length)) as unknown;
        if (isAuditSnapshot(parsed)) snapshots[phase] = parsed;
      } catch {
        // Human-readable CLI output must not make an otherwise valid push fail.
      }
    }
  }

  return snapshots;
}

function isAuditSnapshot(value: unknown): value is OsmAuditSnapshot {
  if (!value || typeof value !== "object") return false;
  const snapshot = value as Record<string, unknown>;
  return (
    Number.isInteger(snapshot.version) &&
    (typeof snapshot.changeset_id === "string" || snapshot.changeset_id === null) &&
    typeof snapshot.tag_present === "boolean" &&
    (typeof snapshot.tag_value === "string" || snapshot.tag_value === null)
  );
}
