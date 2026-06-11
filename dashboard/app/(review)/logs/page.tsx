import Link from "next/link";
import { readUploadLog } from "@/lib/manifest";
import { IS_DEMO_MODE } from "@/lib/paths";
import { SmoothnessBadge, SmoothnessDot } from "@/components/smoothness-badge";

export const dynamic = "force-dynamic";

const SMOOTH_ORDER = [
  "excellent",
  "good",
  "intermediate",
  "bad",
  "very_bad",
] as const;

export default async function LogsPage() {
  const entries = await readUploadLog();
  const ok = entries.filter((e) => e.status === "ok").length;
  const err = entries.length - ok;

  // by value
  const byValue: Record<string, number> = {};
  for (const e of entries) {
    if (e.status !== "ok") continue;
    byValue[e.value] = (byValue[e.value] ?? 0) + 1;
  }

  // by ride (top 6)
  const byRide = new Map<string, number>();
  for (const e of entries) {
    if (e.status !== "ok") continue;
    byRide.set(e.ride_id, (byRide.get(e.ride_id) ?? 0) + 1);
  }
  const topRides = Array.from(byRide.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  // unique ways
  const uniqueWays = new Set(
    entries.filter((e) => e.status === "ok").map((e) => e.way_id)
  ).size;

  const latest = entries[0];

  return (
    <>
      {/* 52px header strip */}
      <header className="shrink-0 border-b border-border px-6 h-[52px] flex items-center justify-between">
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="micro-label">file</span>
            <span className="mono-num text-[13px] tracking-tight text-muted-foreground">
              {IS_DEMO_MODE
                ? "demo-output/output/demo_upload_log.jsonl"
                : "output/upload_log.jsonl"}
            </span>
          </div>
          <span className="h-4 w-px bg-border" />
          <div className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
            <span>
              <span className="mono-num text-foreground">{entries.length}</span>{" "}
              total
            </span>
            <span className="opacity-40">·</span>
            <span className="text-[color:var(--smooth-excellent)]">
              <span className="mono-num">{ok}</span> ok
            </span>
            <span className="opacity-40">·</span>
            <span className="text-destructive">
              <span className="mono-num">{err}</span> error
            </span>
          </div>
        </div>
      </header>

      {/* main split: entries table (left) + summary rail (right) */}
      <div className="flex-1 grid grid-cols-[minmax(0,1fr)_380px] min-h-0">
        {/* LEFT: log table */}
        <section className="overflow-y-auto min-w-0">
          <div className="px-6 py-6">
            <div className="pb-5 border-b border-border">
              <div className="micro-label">audit</div>
              <h1 className="mt-1 text-[28px] tracking-tight font-normal">
                {IS_DEMO_MODE ? "Demo upload log" : "Upload log"}
              </h1>
              <p className="mt-2 text-[12.5px] text-muted-foreground max-w-[52ch]">
                {IS_DEMO_MODE
                  ? "Sample pushed routes for preview only. OSM writes are disabled."
                  : "Every OSM push appended, newest first. Append-only by design."}
              </p>
            </div>

            {entries.length === 0 ? (
              <div className="mt-8 rounded-md border border-dashed border-border px-6 py-16 text-center">
                <div className="micro-label">empty</div>
                <p className="mt-2 text-[13px] text-muted-foreground">
                  No pushes yet. Review a ride and click{" "}
                  <span className="mono-num text-foreground">push to osm</span>{" "}
                  to populate the log.
                </p>
              </div>
            ) : (
              <table className="mt-6 w-full text-[12px] border-t border-b border-border">
                <thead>
                  <tr className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
                    <th className="font-medium text-left py-2.5 pr-4">when</th>
                    <th className="font-medium text-left py-2.5 pr-4">ride</th>
                    <th className="font-medium text-left py-2.5 pr-4">way</th>
                    <th className="font-medium text-left py-2.5 pr-4">value</th>
                    <th className="font-medium text-left py-2.5 pr-4">status</th>
                    <th className="font-medium text-left py-2.5 pr-4">
                      changeset
                    </th>
                    <th className="font-medium text-left py-2.5">error</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e, i) => (
                    <tr
                      key={i}
                      className="border-t border-border/60 hover:bg-muted/40 transition-colors"
                    >
                      <td className="py-2.5 pr-4 mono-num text-[11px] text-muted-foreground">
                        {e.ts.slice(5, 10)} {e.ts.slice(11, 19)}
                      </td>
                      <td className="py-2.5 pr-4 mono-num">
                        <Link
                          href={`/rides/${e.ride_id}`}
                          className="hover:text-[color:var(--accent)] transition-colors"
                        >
                          {e.ride_id}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4 mono-num">
                        <a
                          href={`https://www.openstreetmap.org/way/${e.way_id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:text-[color:var(--accent)] transition-colors"
                        >
                          {e.way_id}
                        </a>
                      </td>
                      <td className="py-2.5 pr-4">
                        <SmoothnessBadge value={e.value} />
                      </td>
                      <td className="py-2.5 pr-4">
                        {e.status === "ok" ? (
                          <span className="mono-num text-[11px] text-[color:var(--smooth-excellent)]">
                            ok
                          </span>
                        ) : (
                          <span className="mono-num text-[11px] text-destructive">
                            error
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4">
                        {e.changeset_url ? (
                          <a
                            className="text-[11px] mono-num text-[color:var(--accent)] hover:underline"
                            href={e.changeset_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            cs {e.changeset_id}
                          </a>
                        ) : (
                          <span className="text-muted-foreground">
                            {e.source === "demo" ? "demo" : "-"}
                          </span>
                        )}
                      </td>
                      <td
                        className="py-2.5 text-[11px] text-destructive max-w-[240px] truncate"
                        title={e.error ?? ""}
                      >
                        {e.error ?? ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* RIGHT: summary rail */}
        <aside className="border-l border-border bg-card flex flex-col min-h-0 overflow-y-auto">
          {/* summary */}
          <div className="px-5 py-4 border-b border-border">
            <div className="micro-label mb-3">summary</div>
            <div className="grid grid-cols-2 gap-3">
              <SummaryStat label="total" value={entries.length} />
              <SummaryStat
                label="ok"
                value={ok}
                accentClass="text-[color:var(--smooth-excellent)]"
              />
              <SummaryStat
                label="error"
                value={err}
                accentClass={err > 0 ? "text-destructive" : undefined}
              />
              <SummaryStat label="unique ways" value={uniqueWays} />
            </div>
          </div>

          {/* by value */}
          <div className="px-5 py-4 border-b border-border">
            <div className="micro-label mb-3">by smoothness</div>
            {ok === 0 ? (
              <div className="text-[11.5px] text-muted-foreground">
                nothing pushed yet.
              </div>
            ) : (
              <ul className="space-y-2">
                {SMOOTH_ORDER.map((cls) => {
                  const count = byValue[cls] ?? 0;
                  const pct = ok > 0 ? count / ok : 0;
                  return (
                    <li key={cls} className="flex items-center gap-3">
                      <SmoothnessDot value={cls} />
                      <span className="text-[11.5px] text-muted-foreground w-24 uppercase tracking-[0.04em]">
                        {cls.replace("_", " ")}
                      </span>
                      <div className="flex-1 h-[3px] rounded-full bg-border overflow-hidden">
                        <div
                          className="h-full"
                          style={{
                            width: `${pct * 100}%`,
                            background: `var(--smooth-${cls.replace("_", "-")})`,
                          }}
                        />
                      </div>
                      <span className="mono-num text-[11.5px] w-6 text-right">
                        {count}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* top rides */}
          <div className="px-5 py-4 border-b border-border">
            <div className="micro-label mb-3">top rides</div>
            {topRides.length === 0 ? (
              <div className="text-[11.5px] text-muted-foreground">
                no activity.
              </div>
            ) : (
              <ul className="space-y-1.5">
                {topRides.map(([rideId, count]) => (
                  <li
                    key={rideId}
                    className="flex items-center justify-between text-[12px]"
                  >
                    <Link
                      href={`/rides/${rideId}`}
                      className="mono-num hover:text-[color:var(--accent)] transition-colors"
                    >
                      {rideId}
                    </Link>
                    <span className="mono-num text-muted-foreground">
                      {count} pushes
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* latest activity */}
          {latest && (
            <div className="px-5 py-4">
              <div className="micro-label mb-2">last activity</div>
              <div className="text-[11.5px] text-muted-foreground mono-num">
                {latest.ts.slice(0, 10)} {latest.ts.slice(11, 19)}
              </div>
              <div className="mt-1 text-[11.5px]">
                ride{" "}
                <Link
                  href={`/rides/${latest.ride_id}`}
                  className="mono-num hover:text-[color:var(--accent)] transition-colors"
                >
                  {latest.ride_id}
                </Link>
              </div>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

function SummaryStat({
  label,
  value,
  accentClass,
}: {
  label: string;
  value: number;
  accentClass?: string;
}) {
  return (
    <div>
      <div className="micro-label">{label}</div>
      <div
        className={`mt-1 mono-num text-xl leading-none ${
          accentClass ?? "text-foreground"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
