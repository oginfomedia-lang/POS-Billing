// Inventory types (match backend/app/schemas/inventory_schemas.py). Quantities are decimal strings.

export interface StockLevelOut {
  product_id: number;
  product_name: string;
  barcode: string | null;
  qty_on_hand: string;
  low_stock_threshold: string | null;
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
  created_at: string;
}
