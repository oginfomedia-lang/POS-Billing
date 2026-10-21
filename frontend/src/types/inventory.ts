import type { UOMType } from './product';

export interface StockLevelOut {
  product_id: number;
  product_name: string;
  barcode: string | null;
  qty_on_hand: string;
  uom: UOMType;
  low_stock_threshold: string | null; // this product's own level; null = Settings default
  effective_threshold: string;
  is_low: boolean;
  base_price: string; // head-office price
  store_price: string | null; // this branch's own price; null = sells at base_price
  price: string; // what this branch charges (before GST)
}

export type InventoryTxnType = 'purchase' | 'sale' | 'return' | 'adjustment';

export interface InventoryTxnOut {
  id: number;
  product_id: number;
  txn_type: InventoryTxnType;
  qty: string;
  reference_id: number | null;
  notes: string | null;
  expiry_date: string | null;
  created_at: string;
}

/** One batch expiring soon, or already expired (days_to_expiry < 0). */
export interface ExpiringBatchOut {
  product_id: number;
  product_name: string;
  barcode: string | null;
  qty_on_hand: string; // the product's whole stock
  uom: UOMType;
  nearest_expiry: string; // this batch's expiry, 'YYYY-MM-DD'
  days_to_expiry: number;
  batch_id: number | null;
  batch_number: string | null;
  batch_qty: string | null; // left in this batch
}

export type BatchSource = 'grn' | 'stock_in' | 'opening' | 'return' | 'adjustment' | 'migration';

export interface BatchOut {
  id: number;
  batch_number: string | null;
  mfg_date: string | null;
  expiry_date: string | null;
  qty_received: string;
  qty_remaining: string;
  source: BatchSource;
  received_at: string;
  days_to_expiry: number | null;
}
