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
  mrp: string | null; // incl. GST, per unit
  hsn_code: string | null;
  qty: number;
  line_total: string; // unit_price × qty, before discount
  discount_amount: string; // offer + manual + this line's share of the bill offer
  offer_name: string | null;
  offer_discount: string; // item offer only
  manual_discount: string; // counter discount, manager-approved
  manual_discount_reason: string | null;
  /** This line's share of the reward points discount (before GST, inside discount_amount). */
  reward_discount: string;
  tax_amount: string;
  /** MRP × qty − amount paid (or the discount when there's no MRP). */
  saving: string;
}

/** One line of the rate-wise GST table on a receipt / credit note. */
export interface GstSummaryRow {
  tax_rate: string;
  taxable: string;
  cgst: string;
  sgst: string;
  tax: string;
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
  bill_offer_name: string | null;
  bill_offer_discount: string;
  tax_amount: string;
  total: string;
  total_saving: string;
  note: string | null;
  customer_mobile: string | null;
  /** Points reserved on this open bill / used on this paid bill. */
  points_redeemed: number;
  /** ₹ off for those points (before GST, already inside discount_amount). */
  reward_discount: string;
  /** Points this paid bill gave the customer. */
  points_earned: number;
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
  /** Masked for printing, e.g. 98XXXXX210. */
  customer_mobile: string | null;
  completed_at: string;
  items: SaleItemOut[];
  subtotal: string;
  discount_amount: string;
  bill_offer_name: string | null;
  bill_offer_discount: string;
  tax_amount: string;
  total: string;
  total_saving: string;
  points_redeemed: number;
  reward_discount: string;
  points_earned: number;
  /** Customer's points balance now; null = no customer on the bill. */
  points_balance: number | null;
  gst_summary: GstSummaryRow[];
  payments: PaymentOut[];
  receipt_header: string;
  receipt_footer: string;
  /** Latest WhatsApp e-bill for this bill; null = none sent or queued. */
  ebill: EbillStatus | null;
}

/** WhatsApp e-bill (PDF of the bill) — shown on the bill screen, never printed. */
export interface EbillStatus {
  status: 'pending' | 'sent' | 'failed';
  /** Masked, e.g. 98XXXXX210. */
  recipient: string;
  error: string | null;
  sent_at: string | null;
}

/** Methods the complete-sale endpoint accepts. */
export type TenderMethod = Exclude<PaymentMethod, 'split'>;

/** Card/UPI go through Razorpay; cash is completed directly. */
export type DigitalMethod = Exclude<TenderMethod, 'cash'>;

export type PaymentIntentStatus = 'pending' | 'paid' | 'failed' | 'cancelled';

/** One Razorpay attempt: a UPI QR for the exact total, or the total pushed to the card machine. */
export interface PaymentIntentOut {
  id: number;
  sale_id: number;
  method: DigitalMethod;
  amount: string;
  status: PaymentIntentStatus;
  qr_image_url: string | null; // UPI only
  failure_reason: string | null;
  created_at: string;
  sale?: SaleOut | null; // set by the poll endpoint once Razorpay confirms and the bill is completed
}

/** Customer's points for the payment screen (GET /customers/{mobile}/rewards). */
export interface RewardInfo {
  mobile: string;
  /** false = first visit; the customer is created when this bill is paid. */
  registered: boolean;
  enabled: boolean;
  points_balance: number;
  block_points: number;
  block_value: string;
  /** Blocks the balance allows (the bill amount may allow fewer). */
  max_blocks: number;
}
