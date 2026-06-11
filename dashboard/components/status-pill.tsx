import { cn } from "@/lib/utils";
import type { RideStatus } from "@/lib/manifest";

const STYLES: Record<RideStatus, string> = {
  pending:
    "bg-[color:var(--w4w-greenscale-800)] text-[color:var(--w4w-greenscale-200)] ring-[color:var(--w4w-cloudy-12)]",
  "yaml-exported":
    "bg-[color-mix(in_oklab,var(--accent)_14%,transparent)] text-[color:var(--accent)] ring-[color-mix(in_oklab,var(--accent)_35%,transparent)]",
  "partially-pushed":
    "bg-[color-mix(in_oklab,var(--smooth-intermediate)_14%,transparent)] text-[color:var(--smooth-intermediate)] ring-[color-mix(in_oklab,var(--smooth-intermediate)_30%,transparent)]",
  "fully-pushed":
    "bg-[color-mix(in_oklab,var(--smooth-excellent)_18%,transparent)] text-[color:var(--smooth-excellent)] ring-[color-mix(in_oklab,var(--smooth-excellent)_38%,transparent)]",
  failed:
    "bg-[color-mix(in_oklab,var(--destructive)_16%,transparent)] text-[color:var(--destructive)] ring-[color-mix(in_oklab,var(--destructive)_38%,transparent)]",
};

const LABELS: Record<RideStatus, string> = {
  pending: "pending",
  "yaml-exported": "yaml",
  "partially-pushed": "partial",
  "fully-pushed": "uploaded",
  failed: "failed",
};

export function StatusPill({ status, className }: { status: RideStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] px-1.5 py-0.5 font-mono text-[10px] font-normal uppercase tracking-[0.04em] ring-1 ring-inset",
        STYLES[status],
        className
      )}
    >
      {LABELS[status]}
    </span>
  );
}
