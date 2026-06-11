import "server-only";
import fs from "node:fs/promises";
import { proposalsCsv } from "./paths";

export interface Proposal {
  way_id: number;
  proposed_value: string;
  coverage_pct: number;
  bad_run_m: number;
  agree_pct: number;
  existing_smoothness: string;
  counts: Record<string, number>;
  confidence_wheelchair?: number;
  predicted_way_class?: string;
  osm_match?: string;
  osm_match_pct?: number;
  comment: string;
}

// extremely small csv parser. the pipeline-produced csvs quote only the
// counts column (json object), so we only need to handle double-quoted
// fields with embedded commas.
function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cur += ch;
      }
    } else {
      if (ch === '"') inQuotes = true;
      else if (ch === ",") {
        out.push(cur);
        cur = "";
      } else cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function parseCounts(raw: string): Record<string, number> {
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export async function readProposals(rideId: string): Promise<Proposal[]> {
  const path = proposalsCsv(rideId);
  let raw: string;
  try {
    raw = await fs.readFile(path, "utf8");
  } catch {
    return [];
  }
  const lines = raw.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = parseCsvLine(lines[0]);
  const idx = (name: string) => headers.indexOf(name);
  const rows: Proposal[] = [];
  for (let i = 1; i < lines.length; i++) {
    const fields = parseCsvLine(lines[i]);
    if (fields.length < headers.length) continue;
    const p: Proposal = {
      way_id: Number(fields[idx("way_id")]),
      proposed_value: (fields[idx("proposed_value")] || "").trim(),
      coverage_pct: Number(fields[idx("coverage_pct")] || 0),
      bad_run_m: Number(fields[idx("bad_run_m")] || 0),
      agree_pct: Number(fields[idx("agree_pct")] || 0),
      existing_smoothness: (fields[idx("existing_smoothness")] || "").trim(),
      counts: parseCounts(fields[idx("counts")] || ""),
      confidence_wheelchair: idx("confidence_wheelchair") >= 0
        ? Number(fields[idx("confidence_wheelchair")] || 0)
        : undefined,
      predicted_way_class: idx("predicted_way_class") >= 0
        ? (fields[idx("predicted_way_class")] || "").trim()
        : undefined,
      osm_match: idx("osm_match") >= 0 ? (fields[idx("osm_match")] || "").trim() : undefined,
      osm_match_pct: idx("osm_match_pct") >= 0
        ? Number(fields[idx("osm_match_pct")] || 0)
        : undefined,
      comment: (fields[idx("comment")] || "").trim(),
    };
    rows.push(p);
  }
  return rows;
}
