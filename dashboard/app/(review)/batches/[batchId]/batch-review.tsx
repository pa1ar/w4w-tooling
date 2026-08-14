"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { SmoothnessBadge } from "@/components/smoothness-badge";
import type { BroadBatchItem, BroadBatchManifest } from "@/lib/broad-batches";
import { cn } from "@/lib/utils";

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

export function BatchReview({ manifest }: { manifest: BroadBatchManifest }) {
  const [selected, setSelected] = useState<number[]>([]);
  const [pushing, setPushing] = useState(false);
  const [pushTotal, setPushTotal] = useState(0);
  const [pushCompleted, setPushCompleted] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [results, setResults] = useState<PushResult[]>([]);
  const [tab, setTab] = useState<"review" | "results">("review");
  const storageKey = `w4w-batch-${manifest.batch}-${manifest.generated_at}-selection`;
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const available = useMemo(
    () => manifest.items.filter((item) => item.status !== "pushed"),
    [manifest.items],
  );
  const approved = available.filter((item) => selectedSet.has(item.way_id));

  useEffect(() => {
    const saved = window.localStorage.getItem(storageKey);
    if (!saved) return;
    const availableIds = new Set(available.map((item) => item.way_id));
    const frame = window.requestAnimationFrame(() => {
      try {
        const ids = (JSON.parse(saved) as unknown[])
          .filter((id): id is number => typeof id === "number" && availableIds.has(id));
        setSelected(ids);
      } catch {
        window.localStorage.removeItem(storageKey);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [available, storageKey]);

  function saveSelection(ids: number[]) {
    window.localStorage.setItem(storageKey, JSON.stringify(ids));
    return ids;
  }

  function toggle(wayId: number, checked: boolean) {
    setSelected((current) => checked
      ? saveSelection([...current, wayId])
      : saveSelection(current.filter((id) => id !== wayId)));
  }

  async function executeSelected() {
    if (approved.length === 0) {
      setConfirming(false);
      return;
    }
    const queue = [...approved];
    setConfirming(false);
    setPushing(true);
    setPushTotal(queue.length);
    setPushCompleted(0);
    setResults([]);
    setTab("results");
    let completed = 0;
    for (const item of queue) {
      let response: Response;
      try {
        response = await fetch(`/api/rides/batch-${manifest.batch}/push`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rows: [payload(item, manifest.batch)] }),
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Network request failed.";
        setResults((current) => [...current, {
          way_id: item.way_id,
          value: item.proposed_value,
          status: "error",
          error: message,
        }]);
        toast.error(`Stopped after ${completed} pushes`, { description: message });
        break;
      }
      if (!response.ok) {
        const error = await response.text();
        setResults((current) => [...current, {
          way_id: item.way_id,
          value: item.proposed_value,
          status: "error",
          error,
        }]);
        toast.error(`Stopped after ${completed} pushes`, { description: error });
        break;
      }
      const body = (await response.json()) as { results: PushResult[] };
      const result = body.results[0];
      setResults((current) => [...current, result]);
      if (result.status !== "ok" || result.ledger_error || !result.ledger_updated) {
        toast.error(`Stopped after ${completed} pushes`, {
          description: result.ledger_error || result.error || "Ledger did not update.",
        });
        break;
      }
      completed += 1;
      setPushCompleted(completed);
      setSelected((current) => saveSelection(current.filter((id) => id !== item.way_id)));
    }
    setPushing(false);
    if (completed === queue.length) {
      toast.success(`Pushed and logged ${completed} path${completed === 1 ? "" : "s"}.`);
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_600px]">
      <section className="flex min-h-0 min-w-0 flex-col gap-4 overflow-hidden border-r border-border bg-muted/30 p-5">
        <div className="flex shrink-0 items-center justify-between">
          <div className="micro-label">batch paths · tallinn</div>
          <div className="text-[11px] text-muted-foreground">click a line for OSM and iD links</div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-card">
          <iframe
            title={`batch-${manifest.batch}-map`}
            src={`/api/batches/${manifest.batch}/map`}
            className="h-full w-full bg-card"
          />
        </div>
        <div className="flex shrink-0 items-center justify-between rounded-md border border-border bg-card px-4 py-3 text-[11.5px]">
          <span className="text-muted-foreground">
            <span className="mono-num text-foreground">{selected.length}</span> selected
          </span>
          <span className="text-muted-foreground">
            OSM tags rechecked before every write
          </span>
        </div>
      </section>

      <section className="flex min-h-0 flex-col bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-4">
            <Tab active={tab === "review"} onClick={() => setTab("review")}>review {available.length}</Tab>
            <Tab active={tab === "results"} onClick={() => setTab("results")}>push results {results.length}</Tab>
          </div>
          {tab === "review" ? (
            <button
              type="button"
              onClick={() => setSelected(saveSelection([]))}
              className="text-[10.5px] uppercase tracking-[0.05em] text-muted-foreground hover:text-foreground"
            >
              clear selection
            </button>
          ) : null}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {tab === "review" ? (
            <ReviewTable items={manifest.items} selected={selectedSet} toggle={toggle} />
          ) : (
            <ResultsTable results={results} pushing={pushing} total={pushTotal} />
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-card px-5 py-3">
          <div className="text-[11.5px] text-muted-foreground">
            <span className="mono-num text-foreground">{approved.length}</span> manually selected
          </div>
          <Button onClick={() => setConfirming(true)} disabled={pushing || approved.length === 0}>
            {pushing ? `pushing ${Math.min(pushCompleted + 1, pushTotal)}/${pushTotal}…` : `push ${approved.length || ""} to osm`.trim()}
          </Button>
        </footer>
      </section>

      {confirming ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-6" role="presentation">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="batch-push-title"
            className="w-full max-w-md rounded-md border border-border bg-card p-5 shadow-2xl"
          >
            <div className="micro-label">final osm confirmation</div>
            <h2 id="batch-push-title" className="mt-2 text-lg font-medium text-foreground">
              Push {approved.length} reviewed path{approved.length === 1 ? "" : "s"}?
            </h2>
            <p className="mt-3 text-[12px] leading-5 text-muted-foreground">
              Each path gets its own transparent [w4w] changeset. The run stops on the first conflict, upload error, or ledger error.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirming(false)}>cancel</Button>
              <Button onClick={executeSelected}>confirm push {approved.length}</Button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function ReviewTable({
  items,
  selected,
  toggle,
}: {
  items: BroadBatchItem[];
  selected: Set<number>;
  toggle: (wayId: number, checked: boolean) => void;
}) {
  return (
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 z-10 border-b border-border bg-card">
        <tr className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
          <th className="w-8 py-2 pl-5 pr-2 text-left font-medium" />
          <th className="px-2 py-2 text-left font-medium">path</th>
          <th className="px-2 py-2 text-left font-medium">proposal</th>
          <th className="px-2 py-2 text-right font-medium">evidence</th>
          <th className="py-2 pl-2 pr-5 text-right font-medium">inspect</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const pushed = item.status === "pushed";
          const surface = item.observed_tags?.surface;
          return (
            <tr
              key={item.way_id}
              className={cn(
                "border-b border-border/60 transition-colors hover:bg-muted/50",
                selected.has(item.way_id) && "bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]",
                pushed && "opacity-55",
              )}
            >
              <td className="py-2.5 pl-5 pr-2 align-middle">
                <Checkbox
                  checked={selected.has(item.way_id)}
                  disabled={pushed}
                  aria-label={`Select way ${item.way_id}`}
                  onCheckedChange={(value) => toggle(item.way_id, !!value)}
                />
              </td>
              <td className="px-2 py-2.5 align-middle">
                <div className="flex items-baseline gap-2">
                  <span className="mono-num text-[10px] text-muted-foreground">#{item.rank}</span>
                  <span className="mono-num text-foreground">{item.way_id}</span>
                </div>
                <div className="mt-0.5 text-[10.5px] text-muted-foreground">
                  {item.highway}{surface ? ` · ${surface}` : ""}
                </div>
              </td>
              <td className="px-2 py-2.5 align-middle">
                <SmoothnessBadge value={item.proposed_value} />
                {pushed ? <div className="mt-1 text-[10px] text-[color:var(--accent)]">pushed</div> : null}
              </td>
              <td className="px-2 py-2.5 text-right align-middle">
                <div className="mono-num text-foreground">{item.coverage_pct.toFixed(0)}%</div>
                <div className="mt-0.5 text-[10px] text-muted-foreground">
                  {item.rides} rides · {item.mean_match_distance_m.toFixed(1)}m match
                </div>
              </td>
              <td className="py-2.5 pl-2 pr-5 text-right align-middle whitespace-nowrap">
                <a href={`https://www.openstreetmap.org/way/${item.way_id}`} target="_blank" rel="noreferrer" className="mr-3 text-[10.5px] text-muted-foreground hover:text-foreground">osm</a>
                <a href={`https://www.openstreetmap.org/edit?way=${item.way_id}`} target="_blank" rel="noreferrer" className="text-[10.5px] text-[color:var(--accent)] hover:underline">iD</a>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ResultsTable({ results, pushing, total }: { results: PushResult[]; pushing: boolean; total: number }) {
  if (results.length === 0) {
    return <div className="p-8 text-center text-[12px] text-muted-foreground">{pushing ? `starting 1/${total}…` : "no pushes this session."}</div>;
  }
  return (
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 z-10 border-b border-border bg-card">
        <tr className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
          <th className="py-2 pl-5 pr-2 text-left font-medium">way</th>
          <th className="px-2 py-2 text-left font-medium">status</th>
          <th className="py-2 pl-2 pr-5 text-left font-medium">changeset · error</th>
        </tr>
      </thead>
      <tbody>
        {results.map((result) => (
          <tr key={result.way_id} className="border-b border-border/60">
            <td className="py-2.5 pl-5 pr-2 mono-num">{result.way_id}</td>
            <td className={cn("px-2 py-2.5 mono-num text-[11px]", result.status === "ok" ? "text-[color:var(--accent)]" : "text-destructive")}>{result.status}</td>
            <td className="py-2.5 pl-2 pr-5">
              {result.changeset_url ? <a href={result.changeset_url} target="_blank" rel="noreferrer" className="mono-num text-[color:var(--accent)] hover:underline">cs {result.changeset_id}</a> : <span className="text-destructive" title={result.error}>{result.error || "failed"}</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Tab({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={cn("text-[12px] uppercase tracking-[0.06em]", active ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>{children}</button>;
}

function payload(item: BroadBatchItem, batch: number) {
  return {
    way_id: item.way_id,
    key: "smoothness",
    value: item.proposed_value,
    manual_reviewed: true,
    comment: `[w4w] smoothness from scooter telemetry (reviewed batch ${String(batch).padStart(2, "0")})`,
  };
}
