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
  /** Credit notes (returns) in the period, and the cash given back for them. */
  returns: number;
  refunded: string;
  /** total − refunded */
  net_total: string;
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

export interface GstHsnRow {
  hsn_code: string | null; // null = products without an HSN code
  tax_rate: string;
  taxable: string;
  tax: string;
  cgst: string;
  sgst: string;
}

export interface TopProductRow {
  product_id: number;
  product_name: string;
  qty: string; // decimal string: "3" or "2.5" (kg for loose items)
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
  gst_hsn: GstHsnRow[];
  top_products: TopProductRow[];
  offers: OfferRow[];
}

/** Gross profit: sales after returns (before GST) minus the purchase cost of what was sold. Admin only. */
export interface ProfitSummary {
  net_sales: string;
  returns: string;
  /** The part of net_sales whose cost is known (profit and margin are on this). */
  costed_sales: string;
  cogs: string;
  gross_profit: string;
  margin_pct: string | null;
  /** Sales of products with no cost price: left out of profit. */
  uncosted_sales: string;
  uncosted_products: number;
}

export interface ProfitRow {
  product_id: number;
  product_name: string;
  category: string | null;
  qty: string;
  net_sales: string;
  cogs: string;
  gross_profit: string;
  margin_pct: string | null;
}

export interface ProfitCategoryRow {
  category: string | null;
  net_sales: string;
  cogs: string;
  gross_profit: string;
  margin_pct: string | null;
}

export interface UncostedRow {
  product_id: number;
  product_name: string;
  qty: string;
  net_sales: string;
}

export interface ProfitReportOut {
  store_id: number | null;
  date_from: string;
  date_to: string;
  summary: ProfitSummary;
  by_category: ProfitCategoryRow[];
  products: ProfitRow[];
  uncosted: UncostedRow[];
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
  cash_refunds: string;
  expected_cash: string | null;
  actual_cash: string | null;
  difference: string | null;
}

/** What one cashier collected on one counter (GET /reports/collection). */
export interface CollectionRow {
  cashier_id: number;
  cashier_name: string;
  counter_code: string | null;
  bills: number;
  cash: string;
  card: string;
  upi: string;
  total: string;
  refunds: string;
  /** total − refunds */
  net: string;
  /** counted − expected on shifts closed in the period; negative = short. null = no closed shift. */
  cash_difference: string | null;
  shift_open: boolean;
}

export interface CollectionReportOut {
  store_id: number | null;
  date_from: string;
  date_to: string;
  rows: CollectionRow[];
  totals: Pick<CollectionRow, 'bills' | 'cash' | 'card' | 'upi' | 'total' | 'refunds' | 'net'>;
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
  /** Footer when the till prints in Marathi ('' = use receipt_footer). */
  receipt_footer_mr: string;
  fssai_number: string;
  low_stock_threshold: string;
  /** Bills older than this many days can't be returned. */
  return_window_days: number;
  /** Reward points for customers identified by mobile number. */
  rewards_enabled: boolean;
  /** ₹ paid for 1 point. */
  reward_rupees_per_point: string;
  /** Points are redeemed in blocks of this many… */
  reward_block_points: number;
  /** …each worth this many ₹ off (before GST). */
  reward_block_value: string;
  /** Nightly WhatsApp collection summary to the owner. */
  daily_report_enabled: boolean;
  /** IST "HH:MM"; sent at the first check after this time. */
  daily_report_time: string;
  /** Comma-separated 10-digit mobiles. */
  daily_report_mobiles: string;
  /** PDF of every paid bill sent on WhatsApp to the customer's mobile. */
  ebill_enabled: boolean;
  /** Weighing-scale sticker: first 2 digits (20-28). */
  scale_prefix: string;
  /** How many digits the scale's item code has (4-6). */
  scale_plu_digits: number;
  /** What the rest of the sticker holds: weight in grams or price in paise. */
  scale_value: 'weight' | 'price';
  /** Card/UPI: confirmed by Razorpay, or taken on the shop's own machine / QR and confirmed by the cashier. */
  card_upi_mode: 'razorpay' | 'manual';
}

export type NotificationStatus = 'pending' | 'sent' | 'failed';

export interface DailyReportSendResult {
  store_name: string;
  recipient: string;
  status: NotificationStatus;
  error: string | null;
}

export interface DailyReportLog {
  id: number;
  /** daily_collection = nightly automatic send; daily_collection_manual = "Send now". */
  kind: 'daily_collection' | 'daily_collection_manual';
  report_date: string;
  store_name: string;
  recipient: string;
  status: NotificationStatus;
  attempts: number;
  error: string | null;
  body: string | null;
  sent_at: string | null;
  updated_at: string;
}
