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

export interface ShiftBillPayment {
  method: 'cash' | 'card' | 'upi' | 'split';
  amount: string;
}

export interface ShiftBill {
  id: number;
  bill_number: string | null;
  status: 'paid' | 'held' | 'voided' | 'open';
  completed_at: string | null;
  created_at: string;
  total: string;
  items_count: number;
  payments: ShiftBillPayment[];
  customer_mobile: string | null; // masked
  return_count: number;
  refunded: string;
}

export interface ShiftReturn {
  id: number;
  return_number: string | null;
  bill_number: string | null;
  created_at: string;
  refund_method: 'cash' | 'card' | 'upi' | 'split';
  refund_amount: string;
}

/** Same numbers the server uses to close the shift: expected cash = float + cash sales − cash refunds. */
export interface ShiftSummary {
  paid_bills: number;
  held_bills: number;
  voided_bills: number;
  sales_total: string;
  cash_sales: string;
  card_sales: string;
  upi_sales: string;
  returns: number;
  cash_refunds: string;
  other_refunds: string;
  opening_float: string;
  expected_cash: string;
}

export interface ShiftBills {
  shift: ShiftOut;
  cashier_name: string;
  counter_code: string | null;
  summary: ShiftSummary;
  bills: ShiftBill[];
  returns: ShiftReturn[];
}
