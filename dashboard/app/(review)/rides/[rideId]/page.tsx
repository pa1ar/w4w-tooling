import Link from "next/link";
import { notFound } from "next/navigation";
import { findRide, deriveRideStatus, countPushedWays } from "@/lib/manifest";
import { readProposals } from "@/lib/proposals";
import { RideReview } from "./ride-review";
import { StatusPill } from "@/components/status-pill";

export const dynamic = "force-dynamic";

export default async function RidePage({
  params,
}: {
  params: Promise<{ rideId: string }>;
}) {
  const { rideId } = await params;
  const ride = await findRide(rideId);
  if (!ride) notFound();

  const [proposals, status, pushed] = await Promise.all([
    readProposals(rideId),
    deriveRideStatus(ride),
    countPushedWays(rideId),
  ]);

  return (
    <>
      <header className="shrink-0 border-b border-border px-6 h-[52px] flex items-center justify-between">
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="micro-label">ride</span>
            <span className="mono-num text-[15px] tracking-tight truncate">
              {rideId}
            </span>
          </div>
          <span className="h-4 w-px bg-border" />
          <div className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
            <span>
              <span className="micro-label mr-1.5">path</span>
              <span className="mono-num text-foreground">{ride.path_id}</span>
            </span>
            <span className="opacity-40">·</span>
            <span>
              <span className="mono-num text-foreground">
                {(ride.points_in_bbox ?? 0).toLocaleString()}
              </span>{" "}
              pts
            </span>
            <span className="opacity-40">·</span>
            <span>
              <span className="mono-num text-foreground">{proposals.length}</span> ways
            </span>
            <span className="opacity-40">·</span>
            <span>
              <span className="mono-num text-foreground">{ride.new}</span> new /{" "}
              <span className="mono-num text-foreground">{ride.override}</span> override
            </span>
            {pushed > 0 && (
              <>
                <span className="opacity-40">·</span>
                <span className="text-[color:var(--accent)]">
                  <span className="mono-num">{pushed}</span> pushed
                </span>
              </>
            )}
          </div>
          <StatusPill status={status} />
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Link
            href={`/api/maps/${rideId}?kind=raw`}
            target="_blank"
            className="text-[11px] text-muted-foreground hover:text-foreground"
          >
            raw gps ↗
          </Link>
          <Link
            href={`/api/maps/${rideId}`}
            target="_blank"
            className="text-[11px] text-muted-foreground hover:text-foreground"
          >
            full map ↗
          </Link>
        </div>
      </header>

      <RideReview rideId={rideId} proposals={proposals} />
    </>
  );
}
