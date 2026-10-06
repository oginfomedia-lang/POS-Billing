import { create } from 'zustand';
import { closeShift, getActiveShift, openShift } from '../services/api/shiftApi';
import type { ShiftOut } from '../types/shift';

interface ShiftState {
  shift: ShiftOut | null;
  busy: boolean;
  loadActive: () => Promise<void>;
  open: (storeId: number, openingFloat: number, counterId?: number | null) => Promise<void>;
  close: (actualCash: number) => Promise<void>;
  clear: () => void;
}

export const useShiftStore = create<ShiftState>()((set, get) => ({
  shift: null,
  busy: false,

  loadActive: async () => {
    try {
      const shift = await getActiveShift();
      set({ shift });
    } catch {
      set({ shift: null });
    }
  },

  open: async (storeId, openingFloat, counterId = null) => {
    set({ busy: true });
    try {
      const shift = await openShift({ store_id: storeId, opening_float: openingFloat, counter_id: counterId });
      set({ shift });
    } finally {
      set({ busy: false });
    }
  },

  close: async (actualCash) => {
    const { shift } = get();
    if (!shift) throw new Error('No active shift.');
    set({ busy: true });
    try {
      const closed = await closeShift(shift.id, { actual_cash: actualCash });
      set({ shift: closed });
    } finally {
      set({ busy: false });
    }
  },

  clear: () => set({ shift: null }),
}));
