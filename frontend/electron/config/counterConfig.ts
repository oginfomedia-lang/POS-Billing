// Reads counter.json (counterCode, apiUrl, printerName) from the user-data folder.
// On first start the file is created with defaults so the installer can edit it.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { app } from 'electron';

export interface CounterConfig {
  counterCode: string;
  apiUrl: string;
  printerName: string;
}

const DEFAULT_CONFIG: CounterConfig = {
  counterCode: 'C01',
  apiUrl: 'http://localhost:5000/api/v1',
  printerName: '',
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
