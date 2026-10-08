// Reads counter.json (counterCode, apiUrl, printer settings) from the user-data folder.
// On first start the file is created with defaults so the installer can edit it.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { app } from 'electron';

export interface CounterConfig {
  counterCode: string;
  apiUrl: string;
  /** Windows printer name for receipts and the cash drawer. '' = the Windows default printer. */
  printerName: string;
  /** Print the receipt automatically after each sale / return. */
  autoPrint: boolean;
  /** Open the cash drawer (through the receipt printer) on cash sales and cash refunds. */
  drawerEnabled: boolean;
}

/** The settings the POS screen may change (the rest is set by the installer). */
export type PrinterSettings = Pick<CounterConfig, 'printerName' | 'autoPrint' | 'drawerEnabled'>;

const DEFAULT_CONFIG: CounterConfig = {
  counterCode: 'C01',
  apiUrl: 'http://localhost:5000/api/v1',
  printerName: '',
  autoPrint: true,
  drawerEnabled: true,
};

export function getConfigPath(): string {
  return join(app.getPath('userData'), 'counter.json');
}

export function loadCounterConfig(): CounterConfig {
  const path = getConfigPath();

  if (!existsSync(path)) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify(DEFAULT_CONFIG, null, 2), 'utf-8');
    return { ...DEFAULT_CONFIG };
  }

  try {
    const saved = JSON.parse(readFileSync(path, 'utf-8')) as Partial<CounterConfig>;
    return { ...DEFAULT_CONFIG, ...saved };
  } catch {
    throw new Error(`counter.json is not valid JSON: ${path}`);
  }
}

/** Saves the printer settings into counter.json, keeping everything else. Returns the new config. */
export function saveCounterConfig(changes: Partial<PrinterSettings>): CounterConfig {
  const next = { ...loadCounterConfig() };
  if (typeof changes.printerName === 'string') next.printerName = changes.printerName.trim().slice(0, 200);
  if (typeof changes.autoPrint === 'boolean') next.autoPrint = changes.autoPrint;
  if (typeof changes.drawerEnabled === 'boolean') next.drawerEnabled = changes.drawerEnabled;
  writeFileSync(getConfigPath(), JSON.stringify(next, null, 2), 'utf-8');
  return next;
}
