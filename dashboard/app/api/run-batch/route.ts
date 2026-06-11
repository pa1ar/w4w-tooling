import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import path from "node:path";
import { IS_DEMO_MODE, REPO_ROOT } from "@/lib/paths";

export const maxDuration = 10;

const SELECT = path.join(REPO_ROOT, "scripts", "OSM", "select_rides.py");
const BATCH = path.join(REPO_ROOT, "scripts", "OSM", "run_pipeline_batch.py");

export async function POST(req: Request) {
  if (IS_DEMO_MODE) {
    return NextResponse.json(
      {
        error: "Pipeline runs are disabled in demo mode. Clone the tooling repo to run the pipeline locally.",
      },
      { status: 403 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const topN = Number(body?.topN ?? 10);
  const force = Boolean(body?.force);

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const emit = (line: string) =>
        controller.enqueue(encoder.encode(line.endsWith("\n") ? line : line + "\n"));

      emit(`[runner] selecting top ${topN} rides...`);
      const sel = await runPy([SELECT, "--top-n", String(topN)], emit);
      if (sel !== 0) {
        emit(`[runner] select_rides failed with code ${sel}`);
        controller.close();
        return;
      }
      emit("[runner] running pipeline batch...");
      const args = [BATCH];
      if (force) args.push("--force");
      const bat = await runPy(args, emit);
      emit(`[runner] pipeline finished with code ${bat}`);
      controller.close();
    },
  });

  return new NextResponse(stream, {
    headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function runPy(args: string[], emit: (line: string) => void): Promise<number> {
  return new Promise((resolve) => {
    const proc = spawn("python3", args, { cwd: REPO_ROOT, env: process.env });
    proc.stdout.on("data", (b) => emit(b.toString().trimEnd()));
    proc.stderr.on("data", (b) => emit(b.toString().trimEnd()));
    proc.on("close", (code) => resolve(code ?? 1));
    proc.on("error", (err) => {
      emit(`[runner] spawn error: ${err}`);
      resolve(1);
    });
  });
}
