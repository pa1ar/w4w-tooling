import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

export interface LedgerUploadEvent {
  ts: string;
  ride_id: string;
  way_id: number;
  key: string;
  value: string;
  status: "ok" | "error";
  changeset_id?: string;
  changeset_url?: string;
  before_version?: number;
  before_changeset_id?: string;
  before_tag_present?: boolean;
  before_tag_value?: string | null;
  after_version?: number;
}

export interface LedgerPropagationResult {
  matched: boolean;
  updated: boolean;
  ledgerPath?: string;
  error?: string;
}

interface LedgerItem {
  rank: number;
  way_id: number;
  confidence_tier: string;
  highway: string;
  proposed_value: string;
  rides: number;
  coverage_pct: number;
  observed_version: number;
  status: string;
  upload_allowed: boolean;
  [key: string]: unknown;
}

interface LedgerManifest {
  batch: number;
  planned_review_date: string;
  items: LedgerItem[];
  [key: string]: unknown;
}

export async function propagateUploadToLedger(
  entry: LedgerUploadEvent,
  ledgerDir: string,
): Promise<LedgerPropagationResult> {
  if (entry.status !== "ok") return { matched: false, updated: false };

  const changesetId = entry.changeset_id ?? changesetIdFromUrl(entry.changeset_url);
  const changesetUrl = entry.changeset_url ?? (
    changesetId ? `https://www.openstreetmap.org/changeset/${changesetId}` : undefined
  );
  if (!changesetId || !changesetUrl) {
    throw new Error(`successful upload for way ${entry.way_id} has no changeset link`);
  }

  const manifestNames = (await fs.readdir(ledgerDir))
    .filter((name) => /^batch-\d+-.+\.json$/.test(name))
    .sort();
  const manifests: Array<{ filePath: string; manifest: LedgerManifest }> = [];
  const matches: Array<{ manifest: LedgerManifest; item: LedgerItem; filePath: string }> = [];

  for (const name of manifestNames) {
    const filePath = path.join(ledgerDir, name);
    const manifest = JSON.parse(await fs.readFile(filePath, "utf8")) as LedgerManifest;
    manifests.push({ filePath, manifest });
    for (const item of manifest.items) {
      if (item.way_id === entry.way_id) matches.push({ manifest, item, filePath });
    }
  }

  if (matches.length === 0) return { matched: false, updated: false };
  if (matches.length > 1) {
    throw new Error(`way ${entry.way_id} appears in multiple broad ledger manifests`);
  }

  const match = matches[0];
  Object.assign(match.item, {
    status: "pushed",
    upload_allowed: false,
    uploaded_at: entry.ts,
    ride_id: entry.ride_id,
    applied_key: entry.key,
    applied_value: entry.value,
    changeset_id: changesetId,
    changeset_url: changesetUrl,
  });
  const auditFields = {
    before_version: entry.before_version,
    before_changeset_id: entry.before_changeset_id,
    before_tag_present: entry.before_tag_present,
    before_tag_value: entry.before_tag_value,
    after_version: entry.after_version,
  };
  for (const [key, value] of Object.entries(auditFields)) {
    if (value !== undefined) match.item[key] = value;
  }
  match.manifest.pushed_count = match.manifest.items.filter(
    (item) => item.status === "pushed",
  ).length;
  match.manifest.remaining_count = match.manifest.items.length - Number(match.manifest.pushed_count);
  match.manifest.last_propagated_at = entry.ts;
  await writeJsonAtomic(match.filePath, match.manifest);

  const allItems = manifests
    .flatMap(({ manifest }) => manifest.items.map((item) => ({ manifest, item })))
    .sort((a, b) => a.item.rank - b.item.rank);
  const pushedCount = allItems.filter(({ item }) => item.status === "pushed").length;

  const summaryPath = path.join(ledgerDir, "summary.json");
  try {
    const summary = JSON.parse(await fs.readFile(summaryPath, "utf8")) as Record<string, unknown>;
    summary.pushed_candidates = pushedCount;
    summary.remaining_candidates = allItems.length - pushedCount;
    summary.last_propagated_at = entry.ts;
    summary.last_changeset_url = changesetUrl;
    await writeJsonAtomic(summaryPath, summary);
  } catch (error) {
    if (!isMissingFile(error)) throw error;
  }

  const ledgerPath = path.join(ledgerDir, "upload_ledger.md");
  await writeTextAtomic(ledgerPath, renderLedger(allItems));
  return { matched: true, updated: true, ledgerPath };
}

function renderLedger(
  rows: Array<{ manifest: LedgerManifest; item: LedgerItem }>,
): string {
  const lines = [
    "# W4W broad OSM upload ledger",
    "",
    "Rows marked `pushed` include their OSM changeset. Unpushed rows remain blocked until every external gate passes.",
    "",
    "| Batch | Review date | Rank | Tier | OSM way | Highway | Proposal | Rides | Coverage | Version | Status | Changeset |",
    "|---:|:---|---:|:---|:---|:---|:---|---:|---:|---:|:---|:---|",
  ];
  for (const { manifest, item } of rows) {
    const changesetId = stringValue(item.changeset_id);
    const changesetUrl = stringValue(item.changeset_url);
    const changeset = changesetId && changesetUrl
      ? `[${changesetId}](${changesetUrl})`
      : "-";
    const afterVersion = Number(item.after_version);
    const version = Number.isFinite(afterVersion)
      ? `${item.observed_version} -> ${afterVersion}`
      : String(item.observed_version);
    lines.push(
      `| ${manifest.batch} | ${manifest.planned_review_date} | ${item.rank} | ` +
      `${item.confidence_tier} | [${item.way_id}](https://www.openstreetmap.org/way/${item.way_id}) | ` +
      `${item.highway} | \`${item.proposed_value}\` | ${item.rides} | ` +
      `${Number(item.coverage_pct).toFixed(1)}% | ${version} | ${item.status} | ${changeset} |`,
    );
  }
  return `${lines.join("\n")}\n`;
}

function changesetIdFromUrl(url?: string): string | undefined {
  return url?.match(/\/changeset\/(\d+)/)?.[1];
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function isMissingFile(error: unknown): boolean {
  return error instanceof Error && "code" in error && error.code === "ENOENT";
}

async function writeJsonAtomic(filePath: string, value: unknown): Promise<void> {
  await writeTextAtomic(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function writeTextAtomic(filePath: string, content: string): Promise<void> {
  const temporaryPath = `${filePath}.${randomUUID()}.tmp`;
  await fs.writeFile(temporaryPath, content, "utf8");
  await fs.rename(temporaryPath, filePath);
}
