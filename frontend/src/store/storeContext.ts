// The branch (store) the admin screens are working in — like a SaaS "workspace".
// Every branch-specific screen (stock, sales, reports, offers, staff, prices) follows `selectedId`,
// so switching branch reloads them with that branch's data only.
// Head office (admin) may pick any branch or "All branches"; managers are locked to their own
// branch. The server enforces the same rule, this just keeps the screens in step.
import { useEffect } from 'react';
import { create } from 'zustand';
import { listStores } from '../services/api/storeApi';
import type { StoreOut } from '../types/api';
import { useAuthStore } from './authStore';

export const APP_NAME = 'Supermarket POS';
const SELECTED_KEY = 'pos-selected-store';
const LAST_NAME_KEY = 'pos-last-store-name';

function savedSelection(): number | null {
  try {
    const v = localStorage.getItem(SELECTED_KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

/** The branch a non-admin is locked to, or undefined when the user may switch (admin / logged out). */
function lockedStoreId(): number | null | undefined {
  const user = useAuthStore.getState().user;
  return user && user.role !== 'admin' ? user.store_id : undefined;
}

function initialSelection(): number | null {
  const locked = lockedStoreId();
  return locked !== undefined ? locked : savedSelection();
}

interface StoreContextState {
  stores: StoreOut[];
  selectedId: number | null; // null = "All branches" (admins only)
  loaded: boolean;
  refresh: () => Promise<void>;
  select: (id: number | null) => void;
}

export const useStoreContext = create<StoreContextState>((set, get) => ({
  stores: [],
  selectedId: initialSelection(),
  loaded: false,

  refresh: async () => {
    const stores = await listStores();
    const locked = lockedStoreId();
    if (locked !== undefined) {
      set({ stores, loaded: true, selectedId: locked });
      return;
    }
    const { selectedId } = get();
    // Forget a selection whose store was deleted or deactivated.
    const valid = selectedId === null || stores.some((s) => s.id === selectedId && s.is_active);
    set({ stores, loaded: true, selectedId: valid ? selectedId : null });
  },

  select: (id) => {
    if (lockedStoreId() !== undefined) return; // managers can't switch branch
    set({ selectedId: id });
    try {
      if (id === null) localStorage.removeItem(SELECTED_KEY);
      else localStorage.setItem(SELECTED_KEY, String(id));
    } catch { /* storage unavailable */ }
  },
}));

// A different person logged in (or out): start again from their own branch / saved choice.
useAuthStore.subscribe((state, prev) => {
  if (state.user?.id !== prev.user?.id) {
    useStoreContext.setState({ stores: [], loaded: false, selectedId: initialSelection() });
  }
});

/** Can the logged-in user switch branch? (head office only) */
export function useCanSwitchStore(): boolean {
  return useAuthStore((s) => s.user?.role === 'admin');
}

/** Name to show in headers: the selected store, the only store, or the app name for "All stores". */
export function useStoreDisplayName(): string {
  return useStoreContext((s) => {
    const active = s.stores.filter((x) => x.is_active);
    const chosen = s.stores.find((x) => x.id === s.selectedId);
    const name = chosen?.name ?? (active.length === 1 ? active[0].name : APP_NAME);
    try { localStorage.setItem(LAST_NAME_KEY, name); } catch { /* ignore */ }
    return name;
  });
}

let loading: Promise<void> | null = null;

/** The store list, loaded once and shared (several screens mounting together make one request). */
export function useStores(): StoreOut[] {
  const { stores, loaded } = useStoreContext();
  useEffect(() => {
    if (loaded || loading) return;
    loading = useStoreContext.getState().refresh().catch(() => {}).finally(() => { loading = null; });
  }, [loaded]);
  return stores;
}

/** For the login screen, which can't call the API yet: the name from the last session. */
export function lastStoreName(): string {
  try { return localStorage.getItem(LAST_NAME_KEY) ?? APP_NAME; } catch { return APP_NAME; }
}
