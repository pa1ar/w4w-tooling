import "server-only";
import fs from "node:fs/promises";
import { waysGeojson } from "./paths";
import { readBatchManifest, readUploadLog } from "./manifest";

export interface ImpactByClass {
  meters: number;
  count: number;
}

export interface Impact {
  totalMeters: number;
  uniqueWays: number;
  newCount: number;
  overrideCount: number;
  ridesTouched: number;
  byClass: Record<string, ImpactByClass>;
  missingLength: number; // ways we pushed but couldn't measure (no geojson)
}

type Coord = [number, number];

function haversineMeters(a: Coord, b: Coord): number {
  const R = 6371000;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function lineLength(coords: Coord[]): number {
  let total = 0;
  for (let i = 1; i < coords.length; i++) {
    total += haversineMeters(coords[i - 1], coords[i]);
  }
  return total;
}

interface WayFeature {
  properties: {
    way_id: number;
    existing_smoothness?: string;
  };
  geometry: { type: "LineString"; coordinates: Coord[] } | { type: string };
}

async function loadWaysByRide(
  rideId: string,
  pathId: string
): Promise<Map<number, WayFeature> | null> {
  try {
    const raw = await fs.readFile(waysGeojson(rideId, pathId), "utf8");
    const fc = JSON.parse(raw) as { features: WayFeature[] };
    const map = new Map<number, WayFeature>();
    for (const f of fc.features ?? []) {
      if (f.properties?.way_id != null) map.set(f.properties.way_id, f);
    }
    return map;
  } catch {
    return null;
  }
}

export async function computeImpact(): Promise<Impact> {
  const [log, manifest] = await Promise.all([
    readUploadLog(),
    readBatchManifest(),
  ]);

  const pathByRide = new Map<string, string>();
  if (manifest) {
    for (const r of manifest.rides) {
      if (r.path_id) pathByRide.set(r.ride_id, r.path_id);
    }
  }

  // group successful pushes per ride
  const perRide = new Map<string, { way_id: number; value: string }[]>();
  for (const e of log) {
    if (e.status !== "ok") continue;
    if (!perRide.has(e.ride_id)) perRide.set(e.ride_id, []);
    perRide.get(e.ride_id)!.push({ way_id: e.way_id, value: e.value });
  }

  const impact: Impact = {
    totalMeters: 0,
    uniqueWays: 0,
    newCount: 0,
    overrideCount: 0,
    ridesTouched: perRide.size,
    byClass: {},
    missingLength: 0,
  };

  const seenWays = new Set<number>();

  for (const [rideId, ways] of perRide) {
    const pathId = pathByRide.get(rideId);
    const byWay = pathId ? await loadWaysByRide(rideId, pathId) : null;

    for (const w of ways) {
      if (seenWays.has(w.way_id)) continue;
      seenWays.add(w.way_id);

      const bucket = impact.byClass[w.value] ?? { meters: 0, count: 0 };
      bucket.count += 1;

      const feat = byWay?.get(w.way_id);
      if (feat && feat.geometry.type === "LineString") {
        const len = lineLength(
          (feat.geometry as { coordinates: Coord[] }).coordinates
        );
        bucket.meters += len;
        impact.totalMeters += len;
        if (feat.properties.existing_smoothness) impact.overrideCount += 1;
        else impact.newCount += 1;
      } else {
        impact.missingLength += 1;
      }

      impact.byClass[w.value] = bucket;
    }
  }

  impact.uniqueWays = seenWays.size;
  return impact;
}

export function formatMeters(m: number): { value: string; unit: string } {
  if (m >= 1000) return { value: (m / 1000).toFixed(2), unit: "km" };
  return { value: Math.round(m).toString(), unit: "m" };
}
