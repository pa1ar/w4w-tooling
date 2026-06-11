import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import { mapboxToken, OUTPUT_DIR } from "@/lib/paths";
import path from "node:path";

// w4w palette (mirrors ../../w4w/src/lib/smoothnessColors.ts and the
// dashboard globals.css --w4w-pavement-* tokens). The pipeline-generated
// HTML hardcodes plotly-ish defaults; we substitute at serve time so the
// iframe feels at home in the dashboard without re-running the pipeline.
const W4W_STYLE = "mapbox://styles/mapbox/dark-v11";
const COLOR_MAP: Record<string, string> = {
  // filtered-lines layer
  "'#e74c3c'": "'#F8D1DC'", // "bad" red -> w4w pavement-bad pink
  "'#2ecc71'": "'#2A9C64'", // "target/intermediate" green -> w4w primary green
  "'#95a5a6'": "'#5B6F65'", // "already tagged" gray -> w4w greenscale-300
  "'#bdc3c7'": "'#44544C'", // "skipped" light gray -> w4w greenscale-400
  // path-z layer (raw line by smoothness bucket)
  "'#00bcd4'": "'#8ECE90'", // excellent -> w4w pavement-good
  "'#1f77b4'": "'#2A9C64'", // good -> w4w primary
  // keep agreement colors (yellow/orange/red) - those encode semantic drift,
  // not smoothness class.
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ rideId: string }> }
) {
  const { rideId } = await params;
  const url = new URL(_req.url);
  const kind = url.searchParams.get("kind") ?? "review";
  const fileName =
    kind === "raw"
      ? `raw_map_${rideId}.html`
      : `smoothness_proposals_${rideId}.html`;
  const full = path.join(OUTPUT_DIR, fileName);
  try {
    let html = await fs.readFile(full, "utf8");
    html = html.replaceAll("__MAPBOX_ACCESS_TOKEN__", mapboxToken(false));
    html = html.replace(/mapbox:\/\/styles\/mapbox\/streets-v1[12]/g, W4W_STYLE);
    for (const [from, to] of Object.entries(COLOR_MAP)) {
      html = html.split(from).join(to);
    }
    // dark body so the map frame matches the dashboard card while the tiles load,
    // and invert the pipeline's white legend/menu chrome to match.
    const darkChrome = `
      <style>
        body { background:#0B1410 !important; color:#EAFFF5 !important; font-family: Inter, ui-sans-serif, system-ui, sans-serif !important; }
        .legend { background: rgba(19,27,23,0.92) !important; border: 1px solid rgba(255,255,255,0.12); color: #EAFFF5 !important; box-shadow: 0 1px 2px rgba(0,0,0,0.4) !important; border-radius: 10px !important; font-size: 11.5px !important; }
        .legend h4 { color: rgba(255,255,255,0.55) !important; font-size: 10.5px !important; font-weight: 500 !important; letter-spacing: 0.04em; text-transform: uppercase; }
        .legend-color { border-radius: 1px; }
        #menu { background: rgba(19,27,23,0.92) !important; color: #EAFFF5 !important; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px !important; font-size: 11.5px !important; }
        .mapboxgl-popup-content { background: #1D2622 !important; color: #EAFFF5 !important; border: 1px solid rgba(255,255,255,0.12) !important; border-radius: 10px !important; }
        .mapboxgl-popup-tip { border-top-color: #1D2622 !important; border-bottom-color: #1D2622 !important; }
        .mapboxgl-popup-content a { color: #8ECE90 !important; }
        .mapboxgl-ctrl-attrib, .mapboxgl-ctrl-attrib a { background: rgba(11,20,16,0.6) !important; color: #91AA9D !important; }
      </style>
    `;
    html = html.replace(/<\/head>/i, `${darkChrome}</head>`);
    return new NextResponse(html, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new NextResponse("Not found", { status: 404 });
  }
}
