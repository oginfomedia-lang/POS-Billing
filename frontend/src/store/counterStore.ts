// Zustand store: counter config.
import { create } from 'zustand';
import type { CounterConfig, PrinterSettings } from '../../electron/config/counterConfig';
import { setApiBaseUrl } from '../services/api/httpClient';

interface CounterState {
  config: CounterConfig | null;
  error: string | null;
  load: () => Promise<void>;
  /** Saves this counter's printer settings into counter.json (Electron only). Throws on failure. */
  savePrinterSettings: (changes: Partial<PrinterSettings>) => Promise<void>;
}

/**
 * API address when running in a browser: VITE_API_URL if the build sets it; the local backend while
 * developing; otherwise the server that served this page (its web server forwards /api to the backend).
 * "localhost" would be the visitor's own PC, not the server.
 */
function browserApiUrl(): string {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (import.meta.env.DEV) return 'http://localhost:5000/api/v1';
  return `${window.location.origin}/api/v1`;
}

export const useCounterStore = create<CounterState>((set) => ({
  config: null,
  error: null,
  load: async () => {
    try {
      // window.posBridge is only present in the Electron app.
      // In a plain browser (the web admin portal, or `vite` while developing) there is no counter.json.
      const bridge = typeof window !== 'undefined' ? window.posBridge : undefined;
      const config = bridge
        ? await bridge.getCounterConfig()
        : { counterCode: 'C01', apiUrl: browserApiUrl(), printerName: '', autoPrint: true, drawerEnabled: true };
      setApiBaseUrl(config.apiUrl);
      set({ config, error: null });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Could not read counter configuration.' });
    }
  },
  savePrinterSettings: async (changes) => {
    if (typeof window !== 'undefined' && window.posBridge) {
      const config = await window.posBridge.saveCounterConfig(changes);
      set({ config });
    }
  },
}));
