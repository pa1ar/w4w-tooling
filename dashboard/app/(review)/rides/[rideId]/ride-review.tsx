"use client";

import { useMemo, useState, useTransition } from "react";
import type { Proposal } from "@/lib/proposals";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { SmoothnessBadge, SmoothnessDot } from "@/components/smoothness-badge";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const SMOOTH_ORDER = ["excellent", "good", "intermediate", "bad", "very_bad"] as const;
const CLIENT_DEMO_MODE = process.env.NEXT_PUBLIC_W4W_DEMO_MODE === "1";
const TOOLING_REPO_URL = process.env.NEXT_PUBLIC_W4W_TOOLING_REPO_URL ?? "";

export function RideReview({
  rideId,
  proposals,
}: {
  rideId: string;
  proposals: Proposal[];
}) {
  const [minCoverage, setMinCoverage] = useState(0.7);
  const [minAgree, setMinAgree] = useState(0.9);
  const [manualChecks, setManualChecks] = useState<Record<number, boolean | null>>({});
  const [pushing, startPush] = useTransition();
  const [exporting, startExport] = useTransition();
  const [pushResults, setPushResults] = useState<PushResult[]>([]);
  const [tab, setTab] = useState<"proposals" | "pushed">("proposals");
  const [demoDialogOpen, setDemoDialogOpen] = useState(false);

  const derivedChecked = useMemo(() => {
    return proposals.map((p) => {
      const manual = manualChecks[p.way_id];
      if (manual !== undefined && manual !== null) return manual;
      return (
        p.proposed_value !== "" &&
        p.coverage_pct >= minCoverage &&
        p.agree_pct >= minAgree
      );
    });
  }, [proposals, manualChecks, minCoverage, minAgree]);

  const approved = proposals
    .map((p, i) => ({ p, ok: derivedChecked[i] }))
    .filter(({ ok, p }) => ok && p.proposed_value !== "")
    .map(({ p }) => p);

  const proposalsWithValue = proposals.filter((p) => p.proposed_value !== "");

  // class counts for the legend strip
  const classCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of proposalsWithValue) {
      c[p.proposed_value] = (c[p.proposed_value] ?? 0) + 1;
    }
    return c;
  }, [proposalsWithValue]);

  function toggleRow(wayId: number, next: boolean) {
    setManualChecks((m) => ({ ...m, [wayId]: next }));
  }

  function selectAll() {
    const next: Record<number, boolean> = {};
    for (const p of proposalsWithValue) next[p.way_id] = true;
    setManualChecks(next);
  }

  function selectNone() {
    const next: Record<number, boolean> = {};
    for (const p of proposals) next[p.way_id] = false;
    setManualChecks(next);
  }

  function resetToThresholds() {
    setManualChecks({});
  }

  async function exportYaml() {
    if (CLIENT_DEMO_MODE) {
      setDemoDialogOpen(true);
      return;
    }

    startExport(async () => {
      const res = await fetch(`/api/rides/${rideId}/export-yaml`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: approvedPayload(approved, rideId) }),
      });
      if (!res.ok) {
        toast.error(`Export failed: ${await res.text()}`);
        return;
      }
      const out = await res.json();
      toast.success(`Wrote ${out.path}`, { description: `${out.count} edits` });
    });
  }

  async function pushToOsm() {
    if (CLIENT_DEMO_MODE) {
      setDemoDialogOpen(true);
      return;
    }

    if (approved.length === 0) {
      toast.error("No approved rows to push.");
      return;
    }
    if (!confirm(`Push ${approved.length} way edits to OSM? One changeset per way.`)) return;
    startPush(async () => {
      setPushResults([]);
      setTab("pushed");
      const res = await fetch(`/api/rides/${rideId}/push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: approvedPayload(approved, rideId) }),
      });
      if (res.status === 401) {
        toast.error("OSM token expired.", {
          description: "Run `uv run python scripts/OSM/osm_edit.py login` in terminal.",
        });
        return;
      }
      if (!res.ok) {
        toast.error(`Push failed: ${await res.text()}`);
        return;
      }
      const out = (await res.json()) as { results: PushResult[] };
      setPushResults(out.results);
      const ok = out.results.filter((r) => r.status === "ok").length;
      const ledgerUpdated = out.results.filter((r) => r.ledger_updated).length;
      const ledgerErrors = out.results.filter((r) => r.ledger_error);
      if (ledgerErrors.length > 0) {
        toast.error(`Pushed ${ok}, but ${ledgerErrors.length} ledger update failed`, {
          description: "Check output/ledger_sync_errors.jsonl before continuing.",
        });
      } else {
        toast.success(`Pushed ${ok} of ${out.results.length}`, {
          description: `${ledgerUpdated} broad ledger row${ledgerUpdated === 1 ? "" : "s"} updated.`,
        });
      }
    });
  }

  function openAllInEditor() {
    if (CLIENT_DEMO_MODE) {
      setDemoDialogOpen(true);
      return;
    }

    if (approved.length === 0) return;
    if (approved.length > 15 && !confirm(`Open ${approved.length} tabs?`)) return;
    for (const p of approved) {
      window.open(`https://www.openstreetmap.org/edit?way=${p.way_id}`, "_blank");
    }
  }

  return (
    <div className="flex-1 grid grid-cols-[minmax(0,1fr)_520px] min-h-0">
      <DemoModeDialog open={demoDialogOpen} onOpenChange={setDemoDialogOpen} />

      {/* MAP column — fill available space, 20px padding */}
      <section className="flex min-h-0 min-w-0 flex-col gap-4 overflow-hidden border-r border-border bg-muted/30 p-5">
        <div className="flex shrink-0 items-center justify-between">
          <div className="micro-label">trace · osm ways</div>
          <div className="text-[11px] text-muted-foreground">
            mapbox review map
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-card shadow-[0_1px_0_rgb(0_0_0/0.02)]">
          <iframe
            title={`ride-${rideId}-map`}
            src={`/api/maps/${rideId}`}
            className="h-full w-full bg-card"
            loading="eager"
          />
        </div>

        <div className="grid shrink-0 grid-cols-5 gap-px overflow-hidden rounded-md border border-border bg-border">
          {SMOOTH_ORDER.map((cls) => (
            <div key={cls} className="bg-card px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <SmoothnessDot value={cls} />
                <span className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
                  {cls.replace("_", " ")}
                </span>
              </div>
              <div className="mt-1 mono-num text-lg leading-none">
                {classCounts[cls] ?? 0}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* INSPECTOR column */}
      <section className="flex flex-col min-h-0 bg-card">
        {/* thresholds */}
        <div className="px-5 py-4 border-b border-border grid grid-cols-2 gap-5">
          <div>
            <div className="flex items-center justify-between">
              <span className="micro-label">min coverage</span>
              <span className="mono-num text-[12px]">{minCoverage.toFixed(2)}</span>
            </div>
            <Slider
              min={0}
              max={1}
              step={0.05}
              value={[minCoverage]}
              onValueChange={(v) => setMinCoverage(Array.isArray(v) ? v[0] : v)}
              className="mt-2.5"
            />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <span className="micro-label">min agree</span>
              <span className="mono-num text-[12px]">{minAgree.toFixed(2)}</span>
            </div>
            <Slider
              min={0}
              max={1}
              step={0.05}
              value={[minAgree]}
              onValueChange={(v) => setMinAgree(Array.isArray(v) ? v[0] : v)}
              className="mt-2.5"
            />
          </div>
        </div>

        {/* tabs */}
        <div className="flex items-center justify-between px-5 pt-3 pb-2 border-b border-border">
          <div className="flex items-center gap-4">
            <TabButton active={tab === "proposals"} onClick={() => setTab("proposals")}>
              proposals{" "}
              <span className="mono-num text-muted-foreground ml-1">
                {approved.length}/{proposals.length}
              </span>
            </TabButton>
            <TabButton active={tab === "pushed"} onClick={() => setTab("pushed")}>
              push results{" "}
              <span className="mono-num text-muted-foreground ml-1">
                {pushResults.length}
              </span>
            </TabButton>
          </div>
          {tab === "proposals" && (
            <div className="flex items-center gap-2 text-[10.5px] uppercase tracking-[0.05em] text-muted-foreground">
              <button
                onClick={selectAll}
                className="hover:text-foreground transition-colors"
              >
                all
              </button>
              <span className="opacity-40">·</span>
              <button
                onClick={selectNone}
                className="hover:text-foreground transition-colors"
              >
                none
              </button>
              <span className="opacity-40">·</span>
              <button
                onClick={resetToThresholds}
                className="hover:text-foreground transition-colors"
              >
                thresholds
              </button>
            </div>
          )}
        </div>

        {/* table area */}
        <div className="flex-1 overflow-y-auto">
          {tab === "proposals" ? (
            <ProposalsTable
              proposals={proposals}
              derivedChecked={derivedChecked}
              toggleRow={toggleRow}
              onDemoBlocked={() => setDemoDialogOpen(true)}
            />
          ) : (
            <PushResultsTable results={pushResults} />
          )}
        </div>

        {/* footer actions */}
        <footer className="shrink-0 border-t border-border px-5 py-3 flex items-center justify-between gap-3 bg-card">
          <div className="text-[11.5px] text-muted-foreground">
            <span className="mono-num text-foreground">{approved.length}</span> approved
            <span className="opacity-60"> of </span>
            <span className="mono-num">{proposalsWithValue.length}</span> non-empty
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={openAllInEditor}
              disabled={approved.length === 0}
              className="uppercase tracking-[0.05em]"
            >
              {CLIENT_DEMO_MODE ? "iD disabled" : "open in iD"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={exportYaml}
              disabled={exporting || approved.length === 0}
            >
              {CLIENT_DEMO_MODE ? "export disabled" : exporting ? "exporting…" : "export yaml"}
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={pushToOsm}
              disabled={pushing || approved.length === 0}
            >
              {CLIENT_DEMO_MODE
                ? "push disabled"
                : pushing
                ? "pushing…"
                : `push ${approved.length || ""} to osm`.trim()}
            </Button>
          </div>
        </footer>
      </section>
    </div>
  );
}

function TabButton({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "relative py-1.5 text-[12px] uppercase tracking-[0.06em] transition-colors",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
      {active && (
        <span className="absolute left-0 right-0 -bottom-[9px] h-[2px] bg-[color:var(--accent)]" />
      )}
    </button>
  );
}

function ProposalsTable({
  proposals,
  derivedChecked,
  toggleRow,
  onDemoBlocked,
}: {
  proposals: Proposal[];
  derivedChecked: boolean[];
  toggleRow: (wayId: number, next: boolean) => void;
  onDemoBlocked: () => void;
}) {
  return (
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 bg-card z-10 border-b border-border">
        <tr className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
          <th className="font-medium text-left pl-5 pr-2 py-2 w-8"></th>
          <th className="font-medium text-left px-2 py-2">way</th>
          <th className="font-medium text-left px-2 py-2">proposed</th>
          <th className="font-medium text-right px-2 py-2">cov</th>
          <th className="font-medium text-right px-2 py-2">agree</th>
          <th className="font-medium text-left px-2 py-2">existing</th>
          <th className="font-medium text-right pl-2 pr-5 py-2">links</th>
        </tr>
      </thead>
      <tbody>
        {proposals.map((p, i) => {
          const checked = derivedChecked[i];
          const disabled = p.proposed_value === "";
          return (
            <tr
              key={p.way_id}
              className={cn(
                "border-b border-border/60 hover:bg-muted/50 transition-colors",
                disabled && "opacity-40"
              )}
            >
              <td className="pl-5 pr-2 py-2 align-middle">
                <Checkbox
                  checked={checked}
                  disabled={disabled}
                  onCheckedChange={(v) => toggleRow(p.way_id, !!v)}
                />
              </td>
              <td className="px-2 py-2 align-middle">
                <div className="mono-num text-foreground">{p.way_id}</div>
                {p.bad_run_m > 0 && (
                  <div className="mono-num text-[10px] text-[color:var(--smooth-bad)]">
                    bad {p.bad_run_m.toFixed(0)}m
                  </div>
                )}
              </td>
              <td className="px-2 py-2 align-middle">
                {p.proposed_value ? (
                  <SmoothnessBadge value={p.proposed_value} />
                ) : (
                  <span className="text-[10px] text-muted-foreground">-</span>
                )}
              </td>
              <td className="px-2 py-2 align-middle text-right mono-num">
                {formatPct(p.coverage_pct)}
              </td>
              <td className="px-2 py-2 align-middle text-right mono-num">
                {formatPct(p.agree_pct)}
              </td>
              <td className="px-2 py-2 align-middle">
                {p.existing_smoothness ? (
                  <SmoothnessBadge value={p.existing_smoothness} variant="ghost" />
                ) : (
                  <span className="text-[10px] text-muted-foreground uppercase tracking-[0.06em]">new</span>
                )}
              </td>
              <td className="pl-2 pr-5 py-2 align-middle text-right whitespace-nowrap">
                <a
                  className="text-[10.5px] text-muted-foreground hover:text-foreground mr-2.5"
                  href={`https://www.openstreetmap.org/way/${p.way_id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  osm
                </a>
                {CLIENT_DEMO_MODE ? (
                  <button
                    type="button"
                    className="text-[10.5px] text-muted-foreground hover:text-foreground"
                    onClick={onDemoBlocked}
                  >
                    iD
                  </button>
                ) : (
                  <a
                    className="text-[10.5px] text-[color:var(--accent)] hover:underline"
                    href={`https://www.openstreetmap.org/edit?way=${p.way_id}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    iD
                  </a>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function DemoModeDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <div className="space-y-2">
          <DialogTitle>Demo mode</DialogTitle>
          <DialogDescription>
            OSM push, YAML export, and iD editor links are disabled here. Clone
            the tooling repo and run the dashboard against your own pipeline
            output to make edits.
          </DialogDescription>
        </div>
        <DialogFooter>
          {TOOLING_REPO_URL ? (
            <a
              href={TOOLING_REPO_URL}
              target="_blank"
              rel="noreferrer"
              className={buttonVariants()}
            >
              Open tooling repo
            </a>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PushResultsTable({ results }: { results: PushResult[] }) {
  if (results.length === 0) {
    return (
      <div className="p-8 text-center text-[12px] text-muted-foreground">
        no pushes this session.
        <br />
        results appear here after clicking <span className="mono-num text-foreground">push to osm</span>.
      </div>
    );
  }
  return (
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 bg-card border-b border-border z-10">
        <tr className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
          <th className="font-medium text-left pl-5 pr-2 py-2">way</th>
          <th className="font-medium text-left px-2 py-2">value</th>
          <th className="font-medium text-left px-2 py-2">status</th>
          <th className="font-medium text-left pl-2 pr-5 py-2">changeset · error</th>
        </tr>
      </thead>
      <tbody>
        {results.map((r) => (
          <tr key={r.way_id} className="border-b border-border/60">
            <td className="pl-5 pr-2 py-2 mono-num">{r.way_id}</td>
            <td className="px-2 py-2">
              <SmoothnessBadge value={r.value} />
            </td>
            <td className="px-2 py-2">
              {r.status === "ok" ? (
                <span className="mono-num text-[11px] text-[color:var(--smooth-excellent)]">ok</span>
              ) : (
                <span className="mono-num text-[11px] text-destructive">error</span>
              )}
            </td>
            <td className="pl-2 pr-5 py-2 max-w-[260px]">
              {r.changeset_url ? (
                <div>
                  <a
                    href={r.changeset_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] mono-num text-[color:var(--accent)] hover:underline"
                  >
                    cs {r.changeset_id}
                  </a>
                  {r.ledger_updated ? (
                    <span className="ml-2 text-[10px] text-muted-foreground">ledger updated</span>
                  ) : null}
                  {r.ledger_error ? (
                    <span className="block text-[10px] text-destructive" title={r.ledger_error}>
                      ledger sync failed
                    </span>
                  ) : null}
                </div>
              ) : (
                <span
                  className="text-[11px] text-destructive truncate block"
                  title={r.error ?? ""}
                >
                  {r.error ?? "-"}
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatPct(x: number): string {
  if (x == null || isNaN(x)) return "-";
  return `${(x * 100).toFixed(0)}%`;
}

interface PushResult {
  way_id: number;
  value: string;
  status: "ok" | "error";
  changeset_id?: string;
  changeset_url?: string;
  ledger_updated?: boolean;
  ledger_error?: string;
  error?: string;
}

function approvedPayload(approved: Proposal[], rideId: string) {
  return approved.map((p) => ({
    way_id: p.way_id,
    key: "smoothness",
    value: p.proposed_value,
    coverage_pct: p.coverage_pct,
    agree_pct: p.agree_pct,
    bad_run_m: p.bad_run_m,
    existing: p.existing_smoothness || null,
    comment: `[w4w] smoothness from scooter telemetry (ride ${rideId})`,
  }));
}
