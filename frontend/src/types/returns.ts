// Return (credit note) types — match backend/app/schemas/return_schemas.py.
// Money fields are decimal strings.
import type { GstSummaryRow, PaymentMethod } from './sale';

export interface ReturnableLine {
  sale_item_id: number;
  product_id: number;
  product_name: string;
  hsn_code: string | null;
  unit_price: string;
  tax_rate: string;
  /** Weighed items can be returned in fractions (kg). */
  is_variable_weight: boolean;
  qty_sold: number;
  qty_returned: number;
  qty_returnable: number;
  line_total: string;
  discount_amount: string;
  tax_amount: string;
  /** What's left of the line after earlier returns (for the refund preview). */
  remaining_line_total: string;
  remaining_discount: string;
  remaining_tax: string;
}

export interface ReturnableBill {
  sale_id: number;
  bill_number: string;
  completed_at: string;
  cashier_name: string;
  total: string;
  payment_methods: PaymentMethod[];
  days_left: number;
  can_return: boolean;
  blocked_reason: string | null;
  lines: ReturnableLine[];
}

/** One of a customer's paid bills, found by mobile number. */
export interface BillForMobile {
  bill_number: string;
  completed_at: string;
  total: string;
  items_count: number;
}

export interface ReturnLineIn {
  sale_item_id: number;
  qty: string;
  restock: boolean;
}

export interface CreateReturnInput {
  bill_number: string;
  lines: ReturnLineIn[];
  reason: string;
  approver_username: string;
  approver_pin: string;
}

export interface ReturnItemOut {
  product_name: string;
  hsn_code: string | null;
  tax_rate: string;
  qty: number;
  line_total: string;
  discount_amount: string;
  tax_amount: string;
  refund_amount: string;
  restocked: boolean;
}

export interface ReturnOut {
  id: number;
  return_number: string;
  created_at: string;
  sale_id: number;
  bill_number: string;
  bill_date: string;
  store_name: string;
  store_address: string | null;
  store_phone: string | null;
  store_gstin: string | null;
  counter_code: string | null;
  cashier_name: string;
  customer_mobile: string | null; // full number, printed on the slip
  approved_by_name: string;
  reason: string;
  refund_method: PaymentMethod;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  refund_amount: string;
  items: ReturnItemOut[];
  gst_summary: GstSummaryRow[];
  receipt_footer: string;
  receipt_footer_mr: string;
}
