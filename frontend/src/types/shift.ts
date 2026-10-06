// Shift types (match backend/app/schemas/shift_schemas.py).

export interface ShiftOut {
  id: number;
  store_id: number;
  counter_id: number;
  cashier_id: number;
  status: 'open' | 'closed';
  opening_cash: string;
  opened_at: string;
  closed_at: string | null;
}
