// Reads/writes license.json in the Electron userData folder.
// Only the main process touches this file — the renderer never accesses it directly.
import { existsSync, writeFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { app } from 'electron';

interface LicenseFile {
  key: string;
}

function getLicensePath(): string {
  return join(app.getPath('userData'), 'license.json');
}

export function readLicenseKey(): string | null {
  const path = getLicensePath();
  if (!existsSync(path)) return null;
  try {
    const data = JSON.parse(readFileSync(path, 'utf-8')) as LicenseFile;
    return data.key?.trim() || null;
  } catch {
    return null;
  }
}

export function writeLicenseKey(key: string): void {
  writeFileSync(getLicensePath(), JSON.stringify({ key }, null, 2), 'utf-8');
}

export function clearLicenseKey(): void {
  writeFileSync(getLicensePath(), JSON.stringify({ key: '' }, null, 2), 'utf-8');
}
