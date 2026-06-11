// server-only helpers to read the locally-stored OSM OAuth token
// and probe the OSM API for token validity.

import "server-only";
import fs from "node:fs/promises";
import { IS_DEMO_MODE, OSM_TOKEN_FILE } from "./paths";

export type TokenProbe =
  | { ok: true; username: string; userId: number }
  | { ok: true; username: "authed"; userId: 0; scopeLimited: true }
  | { ok: false; reason: "missing-token" | "invalid-json" | "unauthorized" | "network"; detail?: string };

export async function readAccessToken(): Promise<string | null> {
  try {
    const raw = await fs.readFile(OSM_TOKEN_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return typeof parsed.access_token === "string" ? parsed.access_token : null;
  } catch {
    return null;
  }
}

export async function probeToken(): Promise<TokenProbe> {
  if (IS_DEMO_MODE) return { ok: false, reason: "missing-token" };

  const token = await readAccessToken();
  if (!token) return { ok: false, reason: "missing-token" };

  const base = process.env.OSM_BASE_URL ?? "https://api.openstreetmap.org";
  try {
    const res = await fetch(`${base}/api/0.6/user/details.json`, {
      headers: {
        Authorization: `Bearer ${token}`,
        "User-Agent": "W4W-Dashboard/0.1",
      },
      cache: "no-store",
    });
    if (res.status === 401) {
      return { ok: false, reason: "unauthorized" };
    }
    // 403 from /user/details means the token is valid but lacks read_prefs scope.
    // write_api-only tokens can still push edits - treat as authed-but-scope-limited.
    if (res.status === 403) {
      return { ok: true, username: "authed", userId: 0, scopeLimited: true };
    }
    if (!res.ok) {
      return { ok: false, reason: "network", detail: `HTTP ${res.status}` };
    }
    const body = await res.json();
    const user = body?.user ?? {};
    return { ok: true, username: user.display_name ?? "?", userId: user.id ?? 0 };
  } catch (err) {
    return { ok: false, reason: "network", detail: String(err) };
  }
}
