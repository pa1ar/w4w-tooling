import { RideRail } from "@/components/ride-rail";
import { readBatchManifest, deriveRideStatus, countPushedWays } from "@/lib/manifest";
import { IS_DEMO_MODE } from "@/lib/paths";
import { readBroadBatchSummaries } from "@/lib/broad-batches";

export default async function ReviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const manifest = await readBatchManifest();
  const batches = IS_DEMO_MODE ? [] : await readBroadBatchSummaries();
  const rails = manifest
    ? await Promise.all(
        manifest.rides.map(async (r) => ({
          ride: r,
          status: await deriveRideStatus(r),
          pushed: await countPushedWays(r.ride_id),
        }))
      )
    : [];

  return (
    <>
      <div className="hidden min-[900px]:flex h-dvh w-full flex-col overflow-hidden">
        {IS_DEMO_MODE ? (
          <div className="flex shrink-0 items-center gap-2 border-b border-border bg-background px-5 py-1.5">
            <span className="inline-flex items-center rounded-[4px] px-1.5 py-0.5 font-mono text-[10px] font-normal uppercase tracking-[0.04em] ring-1 ring-inset bg-[color:var(--w4w-greenscale-800)] text-[color:var(--w4w-greenscale-200)] ring-[color:var(--w4w-cloudy-12)]">
              demo
            </span>
            <span className="mono-num text-[11px] text-muted-foreground">
              sample excerpt of rides in tallinn · not full coverage · may be
              outdated · for demonstration only
            </span>
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <RideRail
            rides={rails}
            batches={batches}
            bboxName={manifest?.bbox_name}
            generatedAt={manifest?.generated_at}
          />
          <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-background">
            {children}
          </main>
        </div>
      </div>
      <main className="flex min-[900px]:hidden h-dvh w-full items-center justify-center bg-background px-6 text-center">
        <div className="max-w-[360px]">
          <div className="micro-label">dashboard unavailable</div>
          <h1 className="mt-2 text-2xl font-light tracking-tight text-foreground">
            Small screens are not supported.
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Please use a tablet or desktop computer with a minimum width of
            900px to review OSM proposals.
          </p>
        </div>
      </main>
    </>
  );
}
