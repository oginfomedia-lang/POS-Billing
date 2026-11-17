import type { UOMType } from './product';

export interface StockLevelOut {
  product_id: number;
  product_name: string;
  barcode: string | null;
  qty_on_hand: string; // the whole stock: shop + godown
  shop_qty: string; // on the shop shelf
  godown_qty: string; // in the godown
  shelf_min_qty: string | null; // refill the shelf at this level; null = no shelf alert
  needs_refill: boolean; // shelf at / below shelf_min_qty and the godown has some
  uom: UOMType;
  low_stock_threshold: string | null; // this product's own level; null = Settings default
  effective_threshold: string;
  is_low: boolean; // the WHOLE stock is low: order from the supplier
  base_price: string; // head-office price
  store_price: string | null; // this branch's own price; null = sells at base_price
  price: string; // what this branch charges (before GST)
}

/** A shelf running low while the godown still has some (GET /inventory/refill). */
export interface RefillOut {
  product_id: number;
  product_name: string;
  uom: UOMType;
  shop_qty: string;
  godown_qty: string;
  shelf_min_qty: string;
}

export type TransferDirection = 'to_shop' | 'to_godown';

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
  batch_source: BatchSource | null; // 'grn' = came from a supplier: can be sent back
}

export type BatchSource = 'grn' | 'stock_in' | 'opening' | 'return' | 'adjustment' | 'migration';

/** Stocked goods sent back to the supplier; amount = what the supplier owes back (incl. GST). */
export interface SupplierReturnOut {
  id: number;
  return_number: string;
  supplier_id: number;
  supplier_name: string;
  product_id: number;
  product_name: string;
  batch_id: number;
  goods_receipt_id: number;
  receipt_number: string;
  qty: string;
  amount: string;
  reason: string;
  applied_to_invoice: string; // taken off the GRN's bill; the rest is credit with the supplier
  created_at: string;
}

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
