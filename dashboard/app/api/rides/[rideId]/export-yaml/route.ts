import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";
import { ensurePendingDir, pendingYaml } from "@/lib/manifest";
import { IS_DEMO_MODE, REPO_ROOT } from "@/lib/paths";

interface Row {
  way_id: number;
  key: string;
  value: string;
  coverage_pct?: number;
  agree_pct?: number;
  bad_run_m?: number;
  existing?: string | null;
  comment: string;
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ rideId: string }> }
) {
  if (IS_DEMO_MODE) {
    return NextResponse.json(
      {
        error: "YAML export is disabled in demo mode. Clone the tooling repo to run the dashboard with your own local output.",
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

  await ensurePendingDir();
  const out = pendingYaml(rideId);
  const doc = {
    ride_id: rideId,
    generated_at: new Date().toISOString(),
    source_csv: path.posix.join("output", `smoothness_proposals_${rideId}.csv`),
    changeset_comment_template: `[w4w] smoothness from scooter telemetry (ride ${rideId})`,
    edits: rows.map((r) => ({
      way_id: r.way_id,
      key: r.key,
      value: r.value,
      coverage_pct: r.coverage_pct,
      agree_pct: r.agree_pct,
      bad_run_m: r.bad_run_m,
      existing: r.existing ?? null,
    })),
  };
  await fs.writeFile(out, yaml.dump(doc, { lineWidth: 120, sortKeys: false }), "utf8");
  return NextResponse.json({
    path: path.relative(REPO_ROOT, out),
    count: rows.length,
  });
}
