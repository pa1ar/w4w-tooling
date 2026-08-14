import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import path from "node:path";
import { IS_DEMO_MODE, REPO_ROOT } from "@/lib/paths";
import { appendUploadLog } from "@/lib/manifest";
import { probeToken } from "@/lib/osm-token";
import { OsmAuditSnapshot, parseOsmAuditSnapshots } from "@/lib/osm-audit";

interface Row {
  way_id: number;
  key: string;
  value: string;
  comment: string;
}

interface PushResult {
  way_id: number;
  value: string;
  status: "ok" | "error";
  changeset_id?: string;
  changeset_url?: string;
  before?: OsmAuditSnapshot;
  after?: OsmAuditSnapshot;
  ledger_updated?: boolean;
  ledger_error?: string;
  error?: string;
}

export const maxDuration = 10;

const OSM_EDIT_SCRIPT = path.join(REPO_ROOT, "scripts", "OSM", "osm_edit.py");
const PYTHON = path.join(REPO_ROOT, ".venv", "bin", "python");

export async function POST(
  req: Request,
  { params }: { params: Promise<{ rideId: string }> }
) {
  if (IS_DEMO_MODE) {
    return NextResponse.json(
      {
        error: "OSM push is disabled in demo mode. Clone the tooling repo to run the dashboard from your own infrastructure.",
      },
      { status: 403 }
    );
  }

  const { rideId } = await params;
  const body = (await req.json()) as { rows?: Row[] };
  const rows = body.rows ?? [];
  if (rows.length === 0) {
    return NextResponse.json({ error: "no rows" }, { status: 400 });
  }

  const probe = await probeToken();
  if (!probe.ok) {
    return NextResponse.json(
      { error: `osm token ${probe.reason}`, hint: "run `uv run python scripts/OSM/osm_edit.py login`" },
      { status: probe.reason === "unauthorized" ? 401 : 503 }
    );
  }

  const results: PushResult[] = [];
  for (const row of rows) {
    const res = await runSetTag(row, rideId);
    const ledger = await appendUploadLog({
      ts: new Date().toISOString(),
      ride_id: rideId,
      way_id: row.way_id,
      key: row.key,
      value: row.value,
      status: res.status,
      changeset_id: res.changeset_id,
      changeset_url: res.changeset_url,
      before_version: res.before?.version,
      before_changeset_id: res.before?.changeset_id ?? undefined,
      before_tag_present: res.before?.tag_present,
      before_tag_value: res.before?.tag_value,
      after_version: res.after?.version,
      error: res.error,
    });
    res.ledger_updated = ledger.updated;
    res.ledger_error = ledger.error;
    results.push(res);
  }

  return NextResponse.json({ results });
}

function runSetTag(row: Row, rideId: string): Promise<PushResult> {
  return new Promise((resolve) => {
    const args = [
      OSM_EDIT_SCRIPT,
      "set-tag",
      "--way-id", String(row.way_id),
      "--key", row.key,
      "--value", row.value,
      "--comment", row.comment || `[w4w] smoothness (ride ${rideId})`,
      "--create-only",
      "-y",
    ];
    const proc = spawn(PYTHON, args, { cwd: REPO_ROOT, env: process.env });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (b) => (stdout += b.toString()));
    proc.stderr.on("data", (b) => (stderr += b.toString()));
    proc.on("close", (code) => {
      const audit = parseOsmAuditSnapshots(stdout);
      if (code === 0) {
        // parse changeset id / url out of osm_edit stdout
        const csMatch = stdout.match(/Changeset:\s+(https:\/\/\S+changeset\/(\d+))/i)
          ?? stdout.match(/Created changeset:\s+(\d+)/i);
        let changeset_id: string | undefined;
        let changeset_url: string | undefined;
        if (csMatch) {
          if (csMatch[2]) {
            changeset_id = csMatch[2];
            changeset_url = csMatch[1];
          } else {
            changeset_id = csMatch[1];
            changeset_url = `https://www.openstreetmap.org/changeset/${changeset_id}`;
          }
        }
        resolve({
          way_id: row.way_id,
          value: row.value,
          status: "ok",
          changeset_id,
          changeset_url,
          before: audit.before,
          after: audit.after,
        });
      } else {
        const tail = (stderr || stdout).split("\n").filter(Boolean).slice(-5).join(" | ");
        resolve({
          way_id: row.way_id,
          value: row.value,
          status: "error",
          before: audit.before,
          after: audit.after,
          error: tail || `exit ${code}`,
        });
      }
    });
    proc.on("error", (err) => {
      resolve({
        way_id: row.way_id,
        value: row.value,
        status: "error",
        error: String(err),
      });
    });
  });
}
