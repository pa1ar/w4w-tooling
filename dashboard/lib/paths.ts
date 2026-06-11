// server-only: resolve paths to repo-root artifacts in local mode and committed
// demo artifacts in hosted demo mode.

import "server-only";
import path from "node:path";
import { config as loadEnv } from "dotenv";

export const APP_ROOT = process.cwd();
export const REPO_ROOT = path.resolve(APP_ROOT, "..");
export const IS_DEMO_MODE =
  process.env.NEXT_PUBLIC_W4W_DEMO_MODE === "1" ||
  process.env.W4W_DASHBOARD_MODE === "demo" ||
  process.env.VERCEL === "1";
export const DATA_ROOT = IS_DEMO_MODE ? path.join(APP_ROOT, "demo-output") : REPO_ROOT;
export const TELEMETRY_DIR = path.join(DATA_ROOT, "telemetry_json");
export const OUTPUT_DIR = path.join(DATA_ROOT, "output");
export const GEOJSON_DIR = path.join(OUTPUT_DIR, "proposals_geojson");
export const PENDING_UPLOAD_DIR = path.join(DATA_ROOT, "pending_upload");

export const SELECTED_RIDES = path.join(OUTPUT_DIR, "selected_rides.json");
export const BATCH_MANIFEST = path.join(OUTPUT_DIR, "batch_manifest.json");
export const UPLOAD_LOG = path.join(OUTPUT_DIR, "upload_log.jsonl");
export const DEMO_UPLOAD_LOG = path.join(OUTPUT_DIR, "demo_upload_log.jsonl");
export const OSM_TOKEN_FILE = path.join(REPO_ROOT, ".osm_token.json");

// load the repo-root .env once per server lifetime
loadEnv({ path: path.join(REPO_ROOT, ".env") });

export function mapboxToken(required = true): string {
  const t = process.env.MAPBOX_ACCESS_TOKEN ?? process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN;
  if (!t && required) throw new Error("MAPBOX_ACCESS_TOKEN missing");
  if (!t) return "";
  return t;
}

export function proposalsCsv(rideId: string) {
  return path.join(OUTPUT_DIR, `smoothness_proposals_${rideId}.csv`);
}

export function rideGeojson(rideId: string, pathId: string) {
  return path.join(GEOJSON_DIR, `${rideId}-${pathId}.geojson`);
}

export function waysGeojson(rideId: string, pathId: string) {
  return path.join(GEOJSON_DIR, `${rideId}-${pathId}_ways.geojson`);
}

export function pendingYaml(rideId: string) {
  return path.join(PENDING_UPLOAD_DIR, `${rideId}.yaml`);
}
