import Image from "next/image";
import Link from "next/link";
import { OsmLoginPill } from "@/components/osm-login-pill";
import { StatusPill } from "@/components/status-pill";
import { W4WWordmark } from "@/components/w4w-wordmark";
import type { ManifestRide, RideStatus } from "@/lib/manifest";
import { cn } from "@/lib/utils";

const TOOLING_REPO_URL =
  process.env.NEXT_PUBLIC_W4W_TOOLING_REPO_URL || "https://github.com/pa1ar/w4w-tooling";

interface RailItem {
  ride: ManifestRide;
  status: RideStatus;
  pushed: number;
}

export function RideRail({
  rides,
  bboxName,
  generatedAt,
  activeRideId,
}: {
  rides: RailItem[];
  bboxName?: string;
  generatedAt?: string;
  activeRideId?: string;
}) {
  const totalProposed = rides.reduce((s, r) => s + r.ride.proposed, 0);
  const totalPushed = rides.reduce((s, r) => s + r.pushed, 0);

  return (
    <aside className="w-[320px] shrink-0 border-r border-border bg-sidebar flex flex-col min-h-0">
      <div className="px-5 pt-5 pb-4 border-b border-sidebar-border">
        <Link
          href="/"
          aria-label="Wheels4Wheels dashboard"
          className="inline-flex w-full flex-col items-start gap-1.5 group"
        >
          <W4WWordmark className="max-w-[220px]" />
          <span className="font-sans text-[22px] font-light leading-5 text-[color:var(--w4w-primary)] transition-colors">
            dashboard
          </span>
        </Link>
        <div className="mt-2 text-xs text-muted-foreground">
          <a
            href="https://w4w.vercel.app"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-sidebar-foreground transition-colors"
          >
            Project
          </a>{" "}
          in collaboration with{" "}
          <a
            href="https://bolt.eu"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-sidebar-foreground transition-colors"
          >
            Bolt
          </a>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <div className="micro-label">
            {bboxName ?? "no batch"}
          </div>
          {generatedAt && (
            <div className="text-[10px] text-muted-foreground mono-num">
              {generatedAt.slice(5, 10)} · {generatedAt.slice(11, 16)}
            </div>
          )}
        </div>
      </div>

      <div className="px-5 py-3 grid grid-cols-3 gap-3 border-b border-sidebar-border bg-sidebar/50">
        <RailStat label="rides" value={rides.length} />
        <RailStat label="proposed" value={totalProposed} />
        <RailStat label="pushed" value={totalPushed} accent={totalPushed > 0} />
      </div>

      <nav className="flex-1 overflow-y-auto">
        <div className="micro-label px-5 pt-4 pb-2">rides</div>
        <ul className="px-2 space-y-0.5">
          {rides.length === 0 ? (
            <li className="px-3 py-8 text-center text-xs text-muted-foreground">
              run <code className="font-mono">select_rides.py</code> &amp;{" "}
              <code className="font-mono">run_pipeline_batch.py</code>
            </li>
          ) : (
            rides.map(({ ride, status, pushed }) => (
              <RailItem
                key={ride.ride_id}
                ride={ride}
                status={status}
                pushed={pushed}
                active={activeRideId === ride.ride_id}
              />
            ))
          )}
        </ul>
      </nav>

      <footer className="px-5 py-3 border-t border-sidebar-border bg-sidebar">
        <div className="grid grid-cols-[16px_minmax(0,1fr)] items-center gap-x-2 gap-y-2">
          <span className="flex size-4 items-center justify-center text-muted-foreground">
            <GitHubMark />
          </span>
          <a
            href={TOOLING_REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-w-0 items-center justify-between gap-2 text-[11px] text-muted-foreground hover:text-sidebar-foreground transition-colors"
          >
            <span>github repo</span>
            <OsmLoginPill />
          </a>
          <a
            href="https://1ar.io"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="1ar labs"
            className="flex size-4 items-center justify-center opacity-80 transition-opacity hover:opacity-100"
          >
            <Image
              src="/1ar-labs.svg"
              alt=""
              width={16}
              height={16}
              className="size-4 rounded-full"
            />
          </a>
          <span className="text-[10px] text-muted-foreground">
            R&amp;D by{" "}
            <a
              href="https://1arlabs.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-sidebar-foreground transition-colors"
            >
              1ar labs
            </a>
          </span>
        </div>
      </footer>
    </aside>
  );
}

function GitHubMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className="size-4 fill-current"
    >
      <path d="M8 0.2a8 8 0 0 0-2.5 15.6c0.4 0.1 0.5-0.2 0.5-0.4v-1.4c-2.2 0.5-2.7-0.9-2.7-0.9-0.4-0.9-0.9-1.1-0.9-1.1-0.7-0.5 0.1-0.5 0.1-0.5 0.8 0.1 1.2 0.8 1.2 0.8 0.7 1.2 1.9 0.9 2.3 0.7 0.1-0.5 0.3-0.9 0.5-1.1-1.8-0.2-3.6-0.9-3.6-3.9 0-0.9 0.3-1.6 0.8-2.1-0.1-0.2-0.4-1 0.1-2.1 0 0 0.7-0.2 2.2 0.8a7.5 7.5 0 0 1 4 0c1.5-1 2.2-0.8 2.2-0.8 0.4 1.1 0.2 1.9 0.1 2.1 0.5 0.6 0.8 1.3 0.8 2.1 0 3-1.8 3.7-3.6 3.9 0.3 0.2 0.6 0.7 0.6 1.5v2.2c0 0.2 0.1 0.5 0.6 0.4A8 8 0 0 0 8 0.2Z" />
    </svg>
  );
}

function RailStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="micro-label">{label}</div>
      <div
        className={cn(
          "mono-num text-base mt-0.5 leading-none",
          accent ? "text-[color:var(--accent)]" : "text-sidebar-foreground"
        )}
      >
        {value}
      </div>
    </div>
  );
}

function RailItem({
  ride,
  status,
  pushed,
  active,
}: {
  ride: ManifestRide;
  status: RideStatus;
  pushed: number;
  active: boolean;
}) {
  const isFailed = ride.status === "failed" || ride.status === "timeout";
  const href = isFailed ? "#" : `/rides/${ride.ride_id}`;
  const coverage = pushed && ride.proposed ? Math.round((pushed / ride.proposed) * 100) : 0;

  return (
    <li>
      <Link
        href={href}
        aria-disabled={isFailed}
        className={cn(
          "group relative block px-3 py-2.5 rounded-md transition-colors",
          "hover:bg-sidebar-accent/70",
          active && "bg-sidebar-accent",
          isFailed && "opacity-55 pointer-events-none"
        )}
      >
        {active && (
          <span className="absolute left-0 top-2 bottom-2 w-[2px] rounded-full bg-[color:var(--accent)]" />
        )}
        <div className="flex items-start justify-between gap-2">
          <div className="mono-num text-[13px] text-sidebar-foreground">
            {ride.ride_id}
          </div>
          <StatusPill status={status} />
        </div>
        <div className="mt-1 flex items-center gap-2 text-[10.5px] text-muted-foreground">
          <span className="mono-num">path {ride.path_id || "-"}</span>
          <span className="opacity-40">·</span>
          <span className="mono-num">{(ride.points_in_bbox ?? 0).toLocaleString()} pts</span>
        </div>
        <div className="mt-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[10.5px]">
            <span className="text-muted-foreground">
              <span className="mono-num text-sidebar-foreground">{ride.proposed}</span>
              {" "}proposed
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
          {coverage > 0 && (
            <div className="w-12 h-[3px] rounded-full bg-border overflow-hidden">
              <div
                className="h-full bg-[color:var(--accent)]"
                style={{ width: `${coverage}%` }}
              />
            </div>
          )}
        </div>
      </Link>
    </li>
  );
}
