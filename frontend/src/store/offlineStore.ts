// Offline billing state on this counter, kept in localStorage so a restart while the server is down loses nothing:
// the cashier's open shift (offline bills belong to it), the bill being made, and how many bills wait to upload.
// The catalogue and saved bills themselves are files (window.posBridge.offline, electron/offline/offlineStore.ts).
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Dec } from '../offline/decimal';
import type { OfflineProduct } from '../offline/types';
import { useAuthStore } from './authStore';
import { useShiftStore } from './shiftStore';

export interface CartLine {
  product: OfflineProduct;
  qty: string;
}

interface OfflineState {
  /** The last open shift seen while online. */
  lastShift: { id: number; store_id: number; user_id: number } | null;
  cart: CartLine[];
  pending: number;
  /** Adds qty of a product; the same product again adds to its line (as the server does). */
  add: (product: OfflineProduct, qty: string) => void;
  setQty: (productId: number, qty: string) => void;
  remove: (productId: number) => void;
  clearCart: () => void;
  setPending: (n: number) => void;
}

export const useOfflineStore = create<OfflineState>()(
  persist(
    (set) => ({
      lastShift: null,
      cart: [],
      pending: 0,
      add: (product, qty) =>
        set((s) => {
          const line = s.cart.find((l) => l.product.id === product.id);
          if (!line) return { cart: [...s.cart, { product, qty }] };
          return { cart: s.cart.map((l) => (l === line ? { ...l, qty: Dec.of(l.qty).add(qty).toString() } : l)) };
        }),
      setQty: (productId, qty) => set((s) => ({ cart: s.cart.map((l) => (l.product.id === productId ? { ...l, qty } : l)) })),
      remove: (productId) => set((s) => ({ cart: s.cart.filter((l) => l.product.id !== productId) })),
      clearCart: () => set({ cart: [] }),
      setPending: (n) => set({ pending: n }),
    }),
    { name: 'pos-offline', partialize: (s) => ({ lastShift: s.lastShift, cart: s.cart }) },
  ),
);

// Remember the open shift whenever the server reports one; forget it when it closes.
useShiftStore.subscribe((state) => {
  const shift = state.shift;
  if (shift && shift.status === 'open') {
    useOfflineStore.setState({ lastShift: { id: shift.id, store_id: shift.store_id, user_id: shift.user_id } });
  } else if (shift && shift.status === 'closed') {
    useOfflineStore.setState({ lastShift: null });
  }
});

// The offline bill in progress belongs to whoever is logged in.
useAuthStore.subscribe((state, prev) => {
  if (state.user?.id !== prev.user?.id) useOfflineStore.setState({ cart: [] });
});
