// Sale, sale item and payment types (match backend/app/schemas/sale_schemas.py).
// Money fields are decimal strings (e.g. "157.50") — never parse them into floats for maths.

export type SaleStatus = 'open' | 'paid' | 'voided' | 'held';
export type PaymentMethod = 'cash' | 'card' | 'upi' | 'split';

export interface PaymentOut {
  id: number;
  method: PaymentMethod;
  amount: string;
  reference: string | null;
  tendered: string | null;
  change_due: string | null;
  created_at: string;
}

export interface SaleItemOut {
  id: number;
  product_id: number;
  product_name: string;
  unit_price: string;
  tax_rate: string;
  qty: number;
  line_total: string; // unit_price × qty, before discount
  discount_amount: string;
  tax_amount: string;
}

export interface SaleOut {
  id: number;
  bill_number: string | null;
  store_id: number;
  counter_id: number | null;
  shift_id: number;
  cashier_id: number;
  status: SaleStatus;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  note: string | null;
  items: SaleItemOut[];
  payments: PaymentOut[];
  created_at: string;
  completed_at: string | null;
}

export interface ReceiptOut {
  sale_id: number;
  bill_number: string;
  store_name: string;
  store_address: string | null;
  store_phone: string | null;
  store_gstin: string | null;
  counter_code: string | null;
  cashier_name: string;
  completed_at: string;
  items: SaleItemOut[];
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  payments: PaymentOut[];
  receipt_header: string;
  receipt_footer: string;
}

/** Methods the complete-sale endpoint accepts. */
export type TenderMethod = Exclude<PaymentMethod, 'split'>;
