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

export interface ExpiringBatchOut {
  product_id: number;
  product_name: string;
  barcode: string | null;
  qty_on_hand: string;
  uom: UOMType;
  nearest_expiry: string; // 'YYYY-MM-DD'
  days_to_expiry: number;
}
