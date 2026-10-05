// Polls GET /health so the cashier can see if the server or database is down.
import { useEffect, useState } from 'react';
import { getHealth } from '../services/api/healthApi';

export type ServerStatus = 'checking' | 'online' | 'database-down' | 'offline';

const POLL_INTERVAL_MS = 10_000;

export function useServerStatus(enabled: boolean): ServerStatus {
  const [status, setStatus] = useState<ServerStatus>('checking');

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const check = async () => {
      try {
        const health = await getHealth();
        if (!cancelled) setStatus(health.database === 'up' ? 'online' : 'database-down');
      } catch {
        if (!cancelled) setStatus('offline');
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
