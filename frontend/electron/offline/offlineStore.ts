// Files for billing while the server is unreachable, in this Windows user's app-data folder (always writable):
//   offline\catalog-<storeId>.json   products, prices, offers and receipt details (refreshed while online)
//   offline\queue\<offlineId>.json   bills not uploaded yet
//   offline\synced\<offlineId>.json  uploaded bills, kept 30 days (reprints)
//   offline\sequence.json            last offline bill number per day
// Writes go to a temporary file first and are then renamed, so a power cut never leaves half a bill.
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { app } from 'electron';

const KEEP_SYNCED_DAYS = 30;

function dir(...parts: string[]): string {
  const path = join(app.getPath('userData'), 'offline', ...parts);
  mkdirSync(path, { recursive: true });
  return path;
}

function writeAtomic(path: string, data: unknown): void {
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, JSON.stringify(data), 'utf-8');
  renameSync(tmp, path);
}

function readJson<T>(path: string): T | null {
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T;
  } catch {
    return null;
  }
}

/** Only ids the renderer made (uuid-like): never a path. */
function safeId(id: string): string {
  if (!/^[A-Za-z0-9-]{8,36}$/.test(id)) throw new Error(`Bad offline bill id: ${id}`);
  return id;
}

export function saveCatalog(storeId: number, catalog: unknown): void {
  writeAtomic(join(dir(), `catalog-${Number(storeId)}.json`), catalog);
}

export function loadCatalog(storeId: number): unknown | null {
  return readJson(join(dir(), `catalog-${Number(storeId)}.json`));
}

/** Next offline bill number for this counter: C02-OFF-261021-0001 (numbering starts again each day). */
export function nextBillNumber(counterCode: string): string {
  const code = counterCode.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 10) || 'C00';
  const now = new Date();
  const day = `${String(now.getFullYear()).slice(2)}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const path = join(dir(), 'sequence.json');
  const seq = readJson<{ day: string; n: number }>(path);
  const n = seq && seq.day === day ? seq.n + 1 : 1;
  writeAtomic(path, { day, n });
  return `${code}-OFF-${day}-${String(n).padStart(4, '0')}`;
}

export function queueBill(bill: { offline_id: string }): void {
  writeAtomic(join(dir('queue'), `${safeId(bill.offline_id)}.json`), bill);
}

/** Bills waiting to be uploaded, oldest first. */
export function listQueue(): unknown[] {
  const folder = dir('queue');
  return readdirSync(folder)
    .filter((f) => f.endsWith('.json'))
    .map((f) => readJson<{ billed_at?: string }>(join(folder, f)))
    .filter((b): b is { billed_at?: string } => b !== null)
    .sort((a, b) => String(a.billed_at).localeCompare(String(b.billed_at)));
}

/** A bill, waiting or uploaded. */
export function getBill(offlineId: string): unknown | null {
  const name = `${safeId(offlineId)}.json`;
  return readJson(join(dir('queue'), name)) ?? readJson(join(dir('synced'), name));
}

/** The server recorded the bill: keep it a while for reprints, out of the queue. */
export function markSynced(offlineId: string, saleId: number): void {
  const name = `${safeId(offlineId)}.json`;
  const bill = readJson<Record<string, unknown>>(join(dir('queue'), name));
  if (!bill) return;
  writeAtomic(join(dir('synced'), name), { ...bill, synced_sale_id: saleId, sync_error: null });
  unlinkSync(join(dir('queue'), name));
}

/** The server refused the bill (e.g. its totals don't add up): it stays queued with the reason, for a manager. */
export function markFailed(offlineId: string, error: string): void {
  const path = join(dir('queue'), `${safeId(offlineId)}.json`);
  const bill = readJson<Record<string, unknown>>(path);
  if (bill) writeAtomic(path, { ...bill, sync_error: error.slice(0, 500) });
}

/** Uploaded bills older than KEEP_SYNCED_DAYS are deleted (called at start-up). */
export function pruneSynced(): void {
  const folder = dir('synced');
  const cutoff = Date.now() - KEEP_SYNCED_DAYS * 24 * 60 * 60 * 1000;
  for (const f of readdirSync(folder)) {
    const path = join(folder, f);
    if (existsSync(path) && statSync(path).mtimeMs < cutoff) unlinkSync(path);
  }
}
