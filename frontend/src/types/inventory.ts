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
  created_at: string;
}
