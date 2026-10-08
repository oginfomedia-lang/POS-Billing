// Report, discount and settings types (match backend report_schemas / discount_schemas / settings_schemas).
// Money and quantities are decimal strings.
import type { PaymentMethod } from './sale';

export interface SalesSummary {
  bills: number;
  voided: number;
  subtotal: string;
  discount: string;
  tax: string;
  total: string;
  average_bill: string;
}

export interface MethodRow {
  method: PaymentMethod;
  bills: number;
  amount: string;
}

export interface DailyRow {
  day: string;
  bills: number;
  total: string;
}

export interface GstRow {
  tax_rate: string;
  taxable: string;
  tax: string;
  cgst: string;
  sgst: string;
}

export interface TopProductRow {
  product_id: number;
  product_name: string;
  qty: number;
  amount: string;
}

export interface OfferRow {
  kind: 'item' | 'bill' | 'manual';
  name: string;
  bills: number;
  amount: string;
}

export interface SalesReportOut {
  store_id: number | null;
  date_from: string;
  date_to: string;
  summary: SalesSummary;
  by_method: MethodRow[];
  daily: DailyRow[];
  gst: GstRow[];
  top_products: TopProductRow[];
  offers: OfferRow[];
}

export interface ShiftRow {
  id: number;
  cashier_name: string;
  counter_code: string | null;
  status: 'open' | 'closed';
  opened_at: string;
  closed_at: string | null;
  opening_float: string;
  bills: number;
  cash_sales: string;
  expected_cash: string | null;
  actual_cash: string | null;
  difference: string | null;
}

export interface RecentSale {
  id: number;
  bill_number: string;
  cashier_name: string;
  total: string;
  completed_at: string;
}

export interface DashboardOut {
  store_id: number | null;
  date: string;
  summary: SalesSummary;
  by_method: MethodRow[];
  open_shifts: number;
  low_stock: number;
  recent_sales: RecentSale[];
}

export type DiscountType = 'percentage' | 'fixed' | 'buy_x_get_y' | 'qty_price';
export type DiscountScope = 'bill' | 'product' | 'category';

export interface DiscountOut {
  id: number;
  name: string;
  discount_type: DiscountType;
  value: string;
  scope: DiscountScope;
  product_id: number | null;
  category_id: number | null;
  store_id: number | null;
  min_bill_amount: string | null;
  max_discount_amount: string | null;
  buy_qty: number | null;
  get_qty: number | null;
  starts_at: string | null;
  ends_at: string | null;
  is_active: boolean;
  /** Filled by the server for display (never sent back). */
  product_name: string | null;
  category_name: string | null;
}

export type DiscountIn = Omit<DiscountOut, 'id' | 'product_name' | 'category_name'>;

export interface SettingsData {
  receipt_header: string;
  receipt_footer: string;
  low_stock_threshold: string;
}
