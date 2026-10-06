export type ShiftStatus = 'open' | 'closed';

export interface ShiftOut {
  id: number;
  user_id: number;
  store_id: number;
  counter_id: number | null;
  status: ShiftStatus;
  opening_float: string;
  expected_cash: string | null;
  actual_cash: string | null;
  opened_at: string;
  closed_at: string | null;
}

export interface OpenShiftRequest {
  opening_float: number;
  store_id: number;
  counter_id?: number | null;
}

export interface CloseShiftRequest {
  actual_cash: number;
}
