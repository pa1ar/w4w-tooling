import { probeToken } from "@/lib/osm-token";
import { IS_DEMO_MODE } from "@/lib/paths";
import { cn } from "@/lib/utils";

export async function OsmLoginPill() {
  const base =
    "inline-flex items-center gap-1.5 rounded-[4px] px-1.5 py-0.5 font-mono text-[10px] font-normal uppercase tracking-[0.04em] ring-1 ring-inset";

  if (IS_DEMO_MODE) {
    return (
      <span
        className={cn(
          base,
          "bg-[color-mix(in_oklab,var(--accent)_14%,transparent)] text-[color:var(--accent)] ring-[color-mix(in_oklab,var(--accent)_36%,transparent)]"
        )}
        title="OSM writes are disabled in demo mode"
      >
        <span className="size-1.5 rounded-full bg-[color:var(--accent)]" />
        demo mode
      </span>
    );
  }

  const p = await probeToken();
  if (p.ok) {
    const label = "scopeLimited" in p ? "authed" : p.username;
    return (
      <span
        className={cn(
          base,
          "bg-[color-mix(in_oklab,var(--smooth-excellent)_16%,transparent)] text-[color:var(--smooth-excellent)] ring-[color-mix(in_oklab,var(--smooth-excellent)_36%,transparent)]"
        )}
      >
        <span className="size-1.5 rounded-full bg-[color:var(--smooth-excellent)]" />
        osm · {label}
      </span>
    );
  }
  const label =
    p.reason === "missing-token"
      ? "not logged in"
      : p.reason === "unauthorized"
      ? "token expired"
      : p.reason;
  return (
    <span
      className={cn(
        base,
        "bg-[color-mix(in_oklab,var(--destructive)_14%,transparent)] text-[color:var(--destructive)] ring-[color-mix(in_oklab,var(--destructive)_36%,transparent)]"
      )}
      title="run `uv run python scripts/OSM/osm_edit.py login` in terminal"
    >
      <span className="size-1.5 rounded-full bg-[color:var(--destructive)]" />
      osm · {label}
    </span>
  );
}
