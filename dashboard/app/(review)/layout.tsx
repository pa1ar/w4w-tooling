import { RideRail } from "@/components/ride-rail";
import { readBatchManifest, deriveRideStatus, countPushedWays } from "@/lib/manifest";

export default async function ReviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const manifest = await readBatchManifest();
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
      <div className="hidden min-[900px]:flex h-dvh w-full overflow-hidden">
        <RideRail
          rides={rails}
          bboxName={manifest?.bbox_name}
          generatedAt={manifest?.generated_at}
        />
        <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-background">
          {children}
        </main>
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
