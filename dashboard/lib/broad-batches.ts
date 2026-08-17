import "server-only";

import fs from "node:fs/promises";
import path from "node:path";
import { ACTIVE_UPLOAD_LEDGER_DIR } from "./paths";

export interface BroadBatchItem {
  rank: number;
  way_id: number;
  highway: string;
  proposed_value: "intermediate" | "bad";
  confidence_tier: "high_confidence" | "broad";
  coverage_pct: number;
  rides: number;
  dominant_class: string;
  dominant_share_pct: number;
  bad_run_m: number;
  mean_match_distance_m: number;
  observed_version: number;
  observed_smoothness: string | null;
  observed_tags?: Record<string, string>;
  status: string;
  changeset_id?: string | null;
  changeset_url?: string | null;
}

export interface BroadBatchManifest {
  batch: number;
  planned_review_date: string;
  generated_at: string;
  status: string;
  items: BroadBatchItem[];
}

export interface BroadBatchSummary {
  batch: number;
  plannedReviewDate: string;
  count: number;
  pushed: number;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "LineString"; coordinates: number[][] };
    properties: Record<string, string | number>;
  }>;
}

export async function readBroadBatchManifest(
  batchId: number,
  directory = ACTIVE_UPLOAD_LEDGER_DIR,
): Promise<BroadBatchManifest | null> {
  const file = await findBatchFile(batchId, ".json", directory);
  if (!file) return null;
  return JSON.parse(await fs.readFile(file, "utf8")) as BroadBatchManifest;
}

export async function readBroadBatchGeojson(
  batchId: number,
  directory = ACTIVE_UPLOAD_LEDGER_DIR,
): Promise<FeatureCollection | null> {
  const file = await findBatchFile(batchId, ".geojson", directory);
  if (!file) return null;
  return JSON.parse(await fs.readFile(file, "utf8")) as FeatureCollection;
}

export async function readBroadBatchSummaries(
  directory = ACTIVE_UPLOAD_LEDGER_DIR,
): Promise<BroadBatchSummary[]> {
  let names: string[];
  try {
    names = await fs.readdir(directory);
  } catch {
    return [];
  }
  const manifests = names
    .filter((name) => /^batch-\d+-.+\.json$/.test(name))
    .sort();
  return Promise.all(
    manifests.map(async (name) => {
      const manifest = JSON.parse(
        await fs.readFile(path.join(/* turbopackIgnore: true */ directory, name), "utf8"),
      ) as BroadBatchManifest;
      return {
        batch: manifest.batch,
        plannedReviewDate: manifest.planned_review_date,
        count: manifest.items.length,
        pushed: manifest.items.filter((item) => item.status === "pushed").length,
      };
    }),
  );
}

async function findBatchFile(
  batchId: number,
  extension: ".json" | ".geojson",
  directory: string,
): Promise<string | null> {
  if (!Number.isInteger(batchId) || batchId < 1 || batchId > 99) return null;
  const prefix = `batch-${String(batchId).padStart(2, "0")}-`;
  try {
    const names = await fs.readdir(directory);
    const name = names.find(
      (candidate) => candidate.startsWith(prefix) && candidate.endsWith(extension),
    );
    return name ? path.join(/* turbopackIgnore: true */ directory, name) : null;
  } catch {
    return null;
  }
}
