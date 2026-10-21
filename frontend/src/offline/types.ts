// Offline billing data: the catalogue from GET /pos/offline-catalog (backend app/schemas/offline_schemas.py) and the
// bills saved on this counter until they are uploaded to POST /sales/offline.
import type { UOMType } from '../types/product';
import type { OfflineOffer } from './pricing';

export interface OfflineProduct {
  id: number;
  name: string;
  sku: string;
  barcode: string | null;
  plu_code: string | null;
  category_id: number | null;
  price: string; // this store's selling price, before GST
  tax_rate: string;
  mrp: string | null;
  hsn_code: string | null;
  uom: UOMType;
  is_variable_weight: boolean;
}

export interface OfflineCatalog {
  generated_at: string;
  store: { id: number; name: string; address: string | null; phone: string | null; gstin: string | null };
  settings: {
    scale_prefix: string;
    scale_plu_digits: number;
    scale_value: 'weight' | 'price';
    receipt_header: string;
    receipt_footer: string;
    receipt_footer_mr: string;
    fssai_number: string;
  };
  products: OfflineProduct[];
  offers: OfflineOffer[];
  categories: Record<string, number | null>;
}

/** One line as uploaded (amounts are what the customer paid) plus what the receipt shows. */
export interface OfflineBillItem {
  product_id: number;
  product_name: string;
  qty: string;
  unit_price: string;
  tax_rate: string;
  mrp: string | null;
  hsn_code: string | null;
  discount_amount: string;
  offer_id: number | null;
  offer_name: string | null;
  offer_discount: string;
  line_total: string;
  tax_amount: string;
  uom: UOMType;
  is_variable_weight: boolean;
}

/** A bill saved on this counter. The upload fields match OfflineSaleIn; the rest is for the receipt and the queue. */
export interface OfflineBill {
  offline_id: string;
  bill_number: string;
  shift_id: number;
  billed_at: string;
  items: OfflineBillItem[];
  bill_offer_id: number | null;
  bill_offer_name: string | null;
  bill_offer_discount: string;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  cash_tendered: string;
  change_due: string;
  // Not uploaded:
  cashier_id: number;
  cashier_name: string;
  counter_code: string;
  store: OfflineCatalog['store'];
  settings: OfflineCatalog['settings'];
  sync_error?: string | null;
  synced_sale_id?: number;
}
