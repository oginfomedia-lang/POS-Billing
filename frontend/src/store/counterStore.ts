// Zustand store: counter config.
import { create } from 'zustand';
import type { CounterConfig } from '../../electron/config/counterConfig';
import { setApiBaseUrl } from '../services/api/httpClient';

interface CounterState {
  config: CounterConfig | null;
  error: string | null;
  load: () => Promise<void>;
}

export const useCounterStore = create<CounterState>((set) => ({
  config: null,
  error: null,
  load: async () => {
    try {
      const config = await window.posBridge.getCounterConfig();
      setApiBaseUrl(config.apiUrl);
      set({ config, error: null });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Could not read counter configuration.' });
    }
  },
}));
