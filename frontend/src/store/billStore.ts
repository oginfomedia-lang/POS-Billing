// Zustand store: current sale as returned by the backend.
// No persistence: the backend reuses the cashier's open bill, so createDraft() restores it after a reload.
// Actions throw on failure so the calling screen can show the error.
import { create } from 'zustand';
import * as billingApi from '../services/api/billingApi';
import { useAuthStore } from './authStore';
import type { SaleOut, TenderMethod } from '../types/sale';

interface BillState {
  sale: SaleOut | null;
  busy: boolean;
  createDraft: () => Promise<void>;
  addItem: (productId: number, qty?: number) => Promise<void>;
  updateItem: (itemId: number, qty: number) => Promise<void>;
  removeItem: (itemId: number) => Promise<void>;
  setManualDiscount: (itemId: number, data: billingApi.ManualDiscountInput) => Promise<void>;
  hold: (note?: string) => Promise<void>;
  resume: (saleId: number) => Promise<void>;
  /** Returns the paid sale; the store is cleared so the next bill can start. */
  complete: (method: TenderMethod, cashTendered?: string, reference?: string) => Promise<SaleOut>;
  /** Card/UPI: Razorpay confirmed and the backend already completed the bill — just clear it. */
  markPaid: () => void;
  void: () => Promise<void>;
  reset: () => void;
}

export const useBillStore = create<BillState>((set, get) => {
  async function run<T>(fn: () => Promise<T>): Promise<T> {
    set({ busy: true });
    try {
      return await fn();
    } finally {
      set({ busy: false });
    }
  }

  function currentSale(): SaleOut {
    const sale = get().sale;
    if (!sale) throw new Error('No bill is open.');
    return sale;
  }

  return {
    sale: null,
    busy: false,

    createDraft: async () => {
      // Guard against double calls (e.g. React StrictMode effects) creating two drafts.
      if (get().busy || get().sale) return;
      await run(async () => set({ sale: await billingApi.createSale() }));
    },

    addItem: (productId, qty = 1) =>
      run(async () => set({ sale: await billingApi.addItem(currentSale().id, productId, qty) })),

    updateItem: (itemId, qty) =>
      run(async () => set({ sale: await billingApi.updateItem(currentSale().id, itemId, qty) })),

    removeItem: (itemId) =>
      run(async () => set({ sale: await billingApi.removeItem(currentSale().id, itemId) })),

    setManualDiscount: (itemId, data) =>
      run(async () => set({ sale: await billingApi.setManualDiscount(currentSale().id, itemId, data) })),

    hold: (note) =>
      run(async () => {
        await billingApi.holdSale(currentSale().id, note);
        set({ sale: null });
      }),

    resume: (saleId) => run(async () => set({ sale: await billingApi.resumeSale(saleId) })),

    complete: (method, cashTendered, reference) =>
      run(async () => {
        const paid = await billingApi.completeSale(currentSale().id, method, cashTendered, reference);
        set({ sale: null });
        return paid;
      }),

    markPaid: () => set({ sale: null }),

    void: () =>
      run(async () => {
        await billingApi.voidSale(currentSale().id);
        set({ sale: null });
      }),

    reset: () => set({ sale: null, busy: false }),
  };
});

// A bill belongs to one cashier: drop it when the logged-in user changes (logout, expired session).
useAuthStore.subscribe((state, prev) => {
  if (state.user?.id !== prev.user?.id) useBillStore.getState().reset();
});
