import Link from "next/link";
import {
  readBatchManifest,
  deriveRideStatus,
  countPushedWays,
  readUploadLog,
} from "@/lib/manifest";
import { computeImpact, formatMeters } from "@/lib/impact";
import { IS_DEMO_MODE } from "@/lib/paths";
import { StatusPill } from "@/components/status-pill";
import { SmoothnessDot } from "@/components/smoothness-badge";

const SMOOTH_ORDER = [
  "excellent",
  "good",
  "intermediate",
  "bad",
  "very_bad",
] as const;

export const dynamic = "force-dynamic";

export default async function LandingPage() {
  const manifest = await readBatchManifest();
  const logEntries = await readUploadLog();
  const recentPushes = logEntries.slice(0, 12);

  if (!manifest) {
    return <EmptyState />;
  }

  const rows = await Promise.all(
    manifest.rides.map(async (r) => ({
      ride: r,
      status: await deriveRideStatus(r),
      pushed: await countPushedWays(r.ride_id),
    }))
  );

  const totalProposed = rows.reduce((s, r) => s + r.ride.proposed, 0);
  const totalPushed = rows.reduce((s, r) => s + r.pushed, 0);
  const failed = rows.filter((r) => r.status === "failed");
  const firstReviewable = rows.find((r) => r.status !== "failed")?.ride.ride_id;
  const impact = await computeImpact();
  const impactTotal = formatMeters(impact.totalMeters);
  const maxClassMeters = Math.max(
    1,
    ...Object.values(impact.byClass).map((v) => v.meters)
  );

  return (
    <>
      {/* 52px header strip (same as ride detail) */}
      <header className="shrink-0 border-b border-border px-6 h-[52px] flex items-center justify-between">
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="micro-label">batch</span>
            <span className="mono-num text-[15px] tracking-tight">
              {manifest.bbox_name}
            </span>
          </div>
          <span className="h-4 w-px bg-border" />
          <div className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
            <span>
              <span className="micro-label mr-1.5">generated</span>
              <span className="mono-num text-foreground">
                {manifest.generated_at.slice(0, 10)}
              </span>
            </span>
            <span className="opacity-40">·</span>
            <span>
              <span className="mono-num text-foreground">{rows.length}</span> rides
            </span>
            <span className="opacity-40">·</span>
            <span>
              <span className="mono-num text-foreground">{totalProposed}</span> proposed
            </span>
            {totalPushed > 0 && (
              <>
                <span className="opacity-40">·</span>
                  <span className="text-[color:var(--accent)]">
                  <span className="mono-num">{totalPushed}</span>{" "}
                  {IS_DEMO_MODE ? "demo pushed" : "pushed"}
                </span>
              </>
            )}
          </div>
        </div>
        {firstReviewable && (
          <Link
            href={`/rides/${firstReviewable}`}
            className="shrink-0 inline-flex items-center gap-2 rounded-md bg-[color:var(--accent)] text-[color:var(--accent-foreground)] px-3 py-1.5 text-[12px] font-medium hover:opacity-90 transition-opacity"
          >
            start with {firstReviewable}
            <span aria-hidden>→</span>
          </Link>
        )}
      </header>

      {/* main split: rides table (left) + summary rail (right) */}
      <div className="flex-1 grid grid-cols-[minmax(0,1fr)_380px] min-h-0">
        {/* LEFT: rides */}
        <section className="overflow-y-auto min-w-0">
          <div className="px-6 py-6">
            {/* impact headline */}
            <div className="pb-5 border-b border-border">
              <div className="micro-label">
                impact · {IS_DEMO_MODE ? "demo sample" : "pushed to openstreetmap"}
              </div>
              <h1 className="mt-1 flex items-baseline gap-3 font-normal tracking-tight">
                <span
                  className={
                    "text-[56px] leading-none mono-num " +
                    (impact.totalMeters > 0
                      ? "text-[color:var(--accent)]"
                      : "text-muted-foreground")
                  }
                >
                  {impactTotal.value}
                </span>
                <span className="text-[20px] text-muted-foreground">
                  {impactTotal.unit} of surface classified
                </span>
              </h1>
              <p className="mt-2 text-[12.5px] text-muted-foreground max-w-[58ch]">
                {impact.uniqueWays > 0 ? (
                  <>
                    <span className="mono-num text-foreground">
                      {impact.uniqueWays}
                    </span>{" "}
                    {IS_DEMO_MODE ? "sample ways" : "ways"} across{" "}
                    <span className="mono-num text-foreground">
                      {impact.ridesTouched}
                    </span>{" "}
                    rides ·{" "}
                    <span className="mono-num text-foreground">
                      {impact.newCount}
                    </span>{" "}
                    new /{" "}
                    <span className="mono-num text-foreground">
                      {impact.overrideCount}
                    </span>{" "}
                    overridden existing tags
                    {impact.missingLength > 0 && (
                      <>
                        {" "}
                        ·{" "}
                        <span className="mono-num text-muted-foreground">
                          {impact.missingLength}
                        </span>{" "}
                        without measured length
                      </>
                    )}
                  </>
                ) : (
                  <>
                    No pushes yet. Pick a ride from the rail, review its
                    proposals, and click{" "}
                    <span className="mono-num text-foreground">push to osm</span>{" "}
                    to log your first edit.
                  </>
                )}
              </p>
            </div>

            {/* by-class breakdown */}
            <div className="mt-6 rounded-md border border-border overflow-hidden">
              <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
                <span className="micro-label">by smoothness class</span>
                <span className="text-[10.5px] text-muted-foreground">
                  meters · ways
                </span>
              </div>
              <ul>
                {SMOOTH_ORDER.map((cls) => {
                  const bucket = impact.byClass[cls];
                  const meters = bucket?.meters ?? 0;
                  const count = bucket?.count ?? 0;
                  const pct = meters / maxClassMeters;
                  const fmt = formatMeters(meters);
                  return (
                    <li
                      key={cls}
                      className="px-4 py-2.5 flex items-center gap-4 border-b border-border/60 last:border-b-0"
                    >
                      <div className="flex items-center gap-2 w-28 shrink-0">
                        <SmoothnessDot value={cls} />
                        <span className="text-[11.5px] uppercase tracking-[0.04em] text-muted-foreground">
                          {cls.replace("_", " ")}
                        </span>
                      </div>
                      <div className="flex-1 h-[6px] rounded-full bg-[color:var(--w4w-greenscale-800)] overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.max(pct * 100, meters > 0 ? 2 : 0)}%`,
                            background: `var(--smooth-${cls.replace("_", "-")})`,
                          }}
                        />
                      </div>
                      <div className="flex items-baseline gap-1 w-28 justify-end">
                        <span
                          className={
                            "mono-num text-[13px] " +
                            (meters > 0 ? "text-foreground" : "text-muted-foreground")
                          }
                        >
                          {fmt.value}
                        </span>
                        <span className="text-[10.5px] text-muted-foreground">
                          {fmt.unit}
                        </span>
                      </div>
                      <div className="w-10 text-right">
                        <span
                          className={
                            "mono-num text-[11.5px] " +
                            (count > 0 ? "text-foreground" : "text-muted-foreground opacity-60")
                          }
                        >
                          {count}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>

            {/* queue header */}
            <div className="mt-8 pb-4 border-b border-border flex items-end justify-between gap-6">
              <div>
                <div className="micro-label">queue</div>
                <h2 className="mt-1 text-[18px] tracking-tight font-normal">
                  {rows.length} rides ·{" "}
                  <span className="text-muted-foreground">
                    {totalProposed} proposed ways
                  </span>
                </h2>
              </div>
              <p className="text-[11.5px] text-muted-foreground max-w-[44ch] text-right">
                Pick a ride from the rail to review smoothness proposals.
              </p>
            </div>

            {/* failures */}
            {failed.length > 0 && (
              <div className="mt-6 rounded-md border border-destructive/30 bg-[color-mix(in_oklab,var(--destructive)_8%,transparent)] px-4 py-2.5 text-[12px] flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-destructive" />
                <span className="text-muted-foreground">
                  <span className="mono-num text-foreground">{failed.length}</span> ride
                  {failed.length > 1 ? "s" : ""} failed (likely Overpass rate-limit). Re-run:{" "}
                  <code className="font-mono text-foreground">
                    uv run python scripts/OSM/run_pipeline_batch.py --force
                  </code>
                </span>
              </div>
            )}

            {/* rides table */}
            <table className="mt-6 w-full text-[12px] border-t border-b border-border">
              <thead>
                <tr className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
                  <th className="font-medium text-left py-2.5 pr-4">ride</th>
                  <th className="font-medium text-left py-2.5 pr-4">path</th>
                  <th className="font-medium text-right py-2.5 pr-4">pts</th>
                  <th className="font-medium text-right py-2.5 pr-4">proposed</th>
                  <th className="font-medium text-right py-2.5 pr-4">pushed</th>
                  <th className="font-medium text-left py-2.5">status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ ride, status, pushed }) => {
                  const disabled = status === "failed";
                  return (
                    <tr
                      key={ride.ride_id}
                      className="border-t border-border/60 hover:bg-muted/40 transition-colors"
                    >
                      <td className="py-2.5 pr-4">
                        {disabled ? (
                          <span className="mono-num opacity-50">{ride.ride_id}</span>
                        ) : (
                          <Link
                            href={`/rides/${ride.ride_id}`}
                            className="mono-num text-foreground hover:text-[color:var(--accent)] transition-colors"
                          >
                            {ride.ride_id}
                          </Link>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 mono-num text-[11px] text-muted-foreground">
                        {ride.path_id ?? "-"}
                      </td>
                      <td className="py-2.5 pr-4 mono-num text-[11px] text-muted-foreground text-right">
                        {(ride.points_in_bbox ?? 0).toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 mono-num text-right">
                        {ride.proposed}
                      </td>
                      <td className="py-2.5 pr-4 mono-num text-right">
                        {pushed > 0 ? (
                          <span className="text-[color:var(--accent)]">{pushed}</span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="py-2.5">
                        <StatusPill status={status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* RIGHT: summary rail */}
        <aside className="border-l border-border bg-card flex flex-col min-h-0">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <div className="micro-label">
              {IS_DEMO_MODE ? "recent demo pushes" : "recent pushes"}
            </div>
            <Link
              href="/logs"
              className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
            >
              all →
            </Link>
          </div>
          <div className="flex-1 overflow-y-auto">
            {recentPushes.length === 0 ? (
              <div className="p-5">
                <div className="rounded-md border border-dashed border-border px-4 py-8 text-center text-[12px] text-muted-foreground">
                  no pushes yet.
                  <br />
                  export yaml or push a ride to start.
                </div>
              </div>
            ) : (
              <ul className="divide-y divide-border/60">
                {recentPushes.map((e, i) => (
                  <li
                    key={i}
                    className="px-5 py-2.5 flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <SmoothnessDot value={e.value} />
                      <div className="min-w-0">
                        <div className="mono-num text-[11.5px] truncate">
                          way {e.way_id}
                        </div>
                        <div className="mono-num text-[10px] text-muted-foreground">
                          ride {e.ride_id}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {e.changeset_url ? (
                        <a
                          href={e.changeset_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[10.5px] mono-num text-[color:var(--accent)] hover:underline"
                        >
                          cs {e.changeset_id}
                        </a>
                      ) : (
                        <span className="text-[10.5px] text-muted-foreground">
                          {e.source === "demo" ? "demo" : "error"}
                        </span>
                      )}
                      <span className="text-[10px] text-muted-foreground mono-num">
                        {e.ts.slice(11, 16)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* pipeline commands at bottom */}
          <div className="border-t border-border px-5 py-4">
            <div className="micro-label mb-2">pipeline</div>
            <pre className="rounded-md border border-border bg-background px-3 py-2.5 font-mono text-[10.5px] leading-relaxed overflow-x-auto text-muted-foreground">
{`uv run python scripts/OSM/select_rides.py
uv run python scripts/OSM/run_pipeline_batch.py`}
            </pre>
          </div>
        </aside>
      </div>
    </>
  );
}

function EmptyState() {
  return (
    <>
      <header className="shrink-0 border-b border-border px-6 h-[52px] flex items-center">
        <div className="flex items-baseline gap-2">
          <span className="micro-label">batch</span>
          <span className="mono-num text-[15px] tracking-tight text-muted-foreground">
            no data
          </span>
        </div>
      </header>
      <div className="flex-1 grid place-items-center p-8">
        <div className="max-w-lg w-full">
          <div className="micro-label">no batch</div>
          <h1 className="mt-2 text-2xl tracking-tight">Nothing to review yet.</h1>
          <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
            Run the two pipeline steps from repo root, then refresh this page.
          </p>
          <pre className="mt-5 rounded-md border border-border bg-muted px-4 py-3 font-mono text-xs leading-relaxed overflow-x-auto">
{`uv run python scripts/OSM/select_rides.py --top-n 10
uv run python scripts/OSM/run_pipeline_batch.py`}
          </pre>
        </div>
      </div>
    </>
  );
}
