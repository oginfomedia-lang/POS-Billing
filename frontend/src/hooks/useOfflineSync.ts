// Runs once in the POS layout: while the server is up, keeps the offline catalogue fresh and uploads bills made
// offline; keeps the "waiting to upload" count for the status bar.
import { useEffect } from 'react';
import { hasOfflineSupport, queuedBills, refreshCatalog, uploadQueued } from '../offline/sync';
import { useAuthStore } from '../store/authStore';
import { useOfflineStore } from '../store/offlineStore';
import { useShiftStore } from '../store/shiftStore';
import { useServerStatusStore } from './useServerStatus';

const CATALOG_EVERY_MS = 5 * 60 * 1000;
const UPLOAD_EVERY_MS = 60 * 1000;

export function useOfflineSync(): void {
  const online = useServerStatusStore((s) => s.status === 'online');
  const userId = useAuthStore((s) => (s.token ? s.user?.id : undefined));
  const userStore = useAuthStore((s) => s.user?.store_id ?? null);
  const shiftStore = useShiftStore((s) => (s.shift?.status === 'open' ? s.shift.store_id : null));
  const lastShiftStore = useOfflineStore((s) => s.lastShift?.store_id ?? null);
  const storeId = shiftStore ?? lastShiftStore ?? userStore;

  // Catalogue: now and every few minutes while online.
  useEffect(() => {
    if (!hasOfflineSupport() || !online || !userId || storeId === null) return;
    const refresh = () => refreshCatalog(storeId).catch((err) => console.warn('Offline catalogue not refreshed:', err));
    refresh();
    const timer = setInterval(refresh, CATALOG_EVERY_MS);
    return () => clearInterval(timer);
  }, [online, userId, storeId]);

  // Uploads: as soon as the server is back, then every minute.
  useEffect(() => {
    if (!hasOfflineSupport()) return;
    const setPending = useOfflineStore.getState().setPending;
    if (!online || !userId) {
      queuedBills().then((b) => setPending(b.length)).catch(() => undefined);
      return;
    }
    const upload = () => uploadQueued(userId).then(setPending).catch(() => undefined);
    upload();
    const timer = setInterval(upload, UPLOAD_EVERY_MS);
    return () => clearInterval(timer);
  }, [online, userId]);
}
