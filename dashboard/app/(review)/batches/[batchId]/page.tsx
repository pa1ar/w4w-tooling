import { notFound } from "next/navigation";
import { readBroadBatchManifest } from "@/lib/broad-batches";
import { BatchReview } from "./batch-review";

export const dynamic = "force-dynamic";

export default async function BatchPage({
  params,
}: {
  params: Promise<{ batchId: string }>;
}) {
  const { batchId } = await params;
  const manifest = await readBroadBatchManifest(Number(batchId));
  if (!manifest) notFound();

  const pushed = manifest.items.filter((item) => item.status === "pushed").length;
  return (
    <>
      <header className="flex h-[52px] shrink-0 items-center justify-between border-b border-border px-6">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex items-baseline gap-2">
            <span className="micro-label">review batch</span>
            <span className="mono-num text-[15px] tracking-tight">
              {String(manifest.batch).padStart(2, "0")}
            </span>
          </div>
          <span className="h-4 w-px bg-border" />
          <div className="flex items-center gap-3 text-[11.5px] text-muted-foreground">
            <span><span className="mono-num text-foreground">{manifest.items.length}</span> paths</span>
            <span className="opacity-40">·</span>
            <span><span className="mono-num text-foreground">{pushed}</span> pushed</span>
            <span className="opacity-40">·</span>
            <span>review date <span className="mono-num text-foreground">{manifest.planned_review_date}</span></span>
          </div>
        </div>
        <div className="text-[11px] text-muted-foreground">
          select only paths you checked
        </div>
      </header>
      <BatchReview manifest={manifest} />
    </>
  );
}
