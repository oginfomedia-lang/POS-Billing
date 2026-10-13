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

export const useCounterStore = create<CounterState>((set) => ({
  config: null,
  error: null,
  load: async () => {
    try {
      // window.posBridge is only present in the Electron app.
      // In a plain browser (dev / admin web UI) fall back to localhost defaults.
      const bridge = typeof window !== 'undefined' ? window.posBridge : undefined;
      const config = bridge
        ? await bridge.getCounterConfig()
        : { counterCode: 'C01', apiUrl: 'http://localhost:5000/api/v1', printerName: '', autoPrint: true, drawerEnabled: true };
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
