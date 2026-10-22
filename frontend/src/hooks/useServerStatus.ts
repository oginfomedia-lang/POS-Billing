// Polls GET /health so the cashier can see if the server or database is down.
// The status bar runs the poll; any screen can read the result with useServerStatusStore (e.g. to offer
// offline billing, or to upload offline bills once the server is back).
import { useEffect } from 'react';
import { create } from 'zustand';
import { getHealth } from '../services/api/healthApi';

export type ServerStatus = 'checking' | 'online' | 'database-down' | 'offline';

const POLL_INTERVAL_MS = 10_000;

export const useServerStatusStore = create<{ status: ServerStatus }>(() => ({ status: 'checking' }));

export function useServerStatus(enabled: boolean): ServerStatus {
  const status = useServerStatusStore((s) => s.status);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const set = (next: ServerStatus) => { if (!cancelled) useServerStatusStore.setState({ status: next }); };

    const check = async () => {
      try {
        const health = await getHealth();
        set(health.database === 'up' ? 'online' : 'database-down');
      } catch {
        set('offline');
      }
    };

    check();
    const timer = setInterval(check, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled]);

  return status;
}
