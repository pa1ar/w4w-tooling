import "server-only";
import fs from "node:fs/promises";
import path from "node:path";
import {
  BATCH_MANIFEST,
  BROAD_UPLOAD_LEDGER_DIR,
  DEMO_UPLOAD_LOG,
  IS_DEMO_MODE,
  LEDGER_SYNC_ERROR_LOG,
  PENDING_UPLOAD_DIR,
  UPLOAD_LOG,
  proposalsCsv,
  rideGeojson,
  waysGeojson,
  pendingYaml,
} from "./paths";
import {
  LedgerPropagationResult,
  propagateUploadToLedger,
} from "./upload-ledger";

export interface ManifestRide {
  ride_id: string;
  path_id: string | null;
  file: string;
  status: "ok" | "skipped-cached" | "failed" | "timeout" | string;
  rows: number;
  proposed: number;
  new: number;
  override: number;
  points_in_bbox?: number;
  total_gps_points?: number;
  first_gps?: [number, number] | null;
  last_gps?: [number, number] | null;
  csv?: string | null;
  html?: string | null;
  raw_html?: string | null;
  duration_s?: number;
  stderr_tail?: string[];
}

export interface BatchManifest {
  generated_at: string;
  bbox_name: string;
  bbox: [number, number, number, number];
  rides: ManifestRide[];
}

export async function readBatchManifest(): Promise<BatchManifest | null> {
  try {
    const raw = await fs.readFile(BATCH_MANIFEST, "utf8");
    return JSON.parse(raw) as BatchManifest;
  } catch {
    return null;
  }
}

export async function findRide(rideId: string): Promise<ManifestRide | null> {
  const m = await readBatchManifest();
  if (!m) return null;
  return m.rides.find((r) => r.ride_id === rideId) ?? null;
}

export type RideStatus = "pending" | "yaml-exported" | "partially-pushed" | "fully-pushed" | "failed";

export async function deriveRideStatus(ride: ManifestRide): Promise<RideStatus> {
  if (ride.status === "failed" || ride.status === "timeout") return "failed";
  const yamlPath = pendingYaml(ride.ride_id);
  const hasYaml = await fileExists(yamlPath);

  const pushedWays = await countPushedWays(ride.ride_id);
  if (pushedWays > 0 && ride.proposed > 0) {
    return pushedWays >= ride.proposed ? "fully-pushed" : "partially-pushed";
  }
  if (hasYaml) return "yaml-exported";
  return "pending";
}

async function fileExists(p: string) {
  try {
    await fs.stat(p);
    return true;
  } catch {
    return false;
  }
}

export async function countPushedWays(rideId: string): Promise<number> {
  try {
    const raw = await fs.readFile(uploadLogReadPath(), "utf8");
    let n = 0;
    for (const line of raw.split("\n")) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line);
        if (entry.ride_id === rideId && entry.status === "ok") n++;
      } catch {
        // skip malformed line
      }
    }
    return n;
  } catch {
    return 0;
  }
}

export interface UploadLogEntry {
  ts: string;
  ride_id: string;
  way_id: number;
  key: string;
  value: string;
  status: "ok" | "error";
  changeset_id?: string;
  changeset_url?: string;
  before_version?: number;
  before_changeset_id?: string;
  before_tag_present?: boolean;
  before_tag_value?: string | null;
  after_version?: number;
  error?: string;
  source?: "demo";
}

export async function readUploadLog(): Promise<UploadLogEntry[]> {
  try {
    const raw = await fs.readFile(uploadLogReadPath(), "utf8");
    const entries: UploadLogEntry[] = [];
    for (const line of raw.split("\n")) {
      if (!line.trim()) continue;
      try {
        entries.push(JSON.parse(line) as UploadLogEntry);
      } catch {
        // skip malformed
      }
    }
    return entries.reverse();
  } catch {
    return [];
  }
}

export async function appendUploadLog(entry: UploadLogEntry): Promise<LedgerPropagationResult> {
  await fs.mkdir(path.dirname(UPLOAD_LOG), { recursive: true });
  await fs.appendFile(UPLOAD_LOG, JSON.stringify(entry) + "\n", "utf8");
  if (entry.status !== "ok") return { matched: false, updated: false };
  try {
    return await propagateUploadToLedger(entry, BROAD_UPLOAD_LEDGER_DIR);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    try {
      await fs.appendFile(
        LEDGER_SYNC_ERROR_LOG,
        JSON.stringify({ ts: new Date().toISOString(), way_id: entry.way_id, error: message }) + "\n",
        "utf8",
      );
    } catch {
      // The primary upload log was already persisted; surface the sync failure in the response.
    }
    return { matched: false, updated: false, error: message };
  }
}

function uploadLogReadPath() {
  return IS_DEMO_MODE ? DEMO_UPLOAD_LOG : UPLOAD_LOG;
}

export async function ensurePendingDir() {
  await fs.mkdir(PENDING_UPLOAD_DIR, { recursive: true });
}

export { proposalsCsv, rideGeojson, waysGeojson, pendingYaml };
