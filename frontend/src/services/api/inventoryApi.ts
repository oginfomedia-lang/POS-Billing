// Inventory API calls.
import type { ExpiringBatchOut, InventoryTxnOut, StockLevelOut } from '../../types/inventory';
import { httpClient } from './httpClient';

interface QtyResponse {
  product_id: number;
  qty_on_hand: string;
}

export async function getStockLevels(storeId: number): Promise<StockLevelOut[]> {
  const resp = await httpClient.get<StockLevelOut[]>('/inventory', { params: { store_id: storeId } });
  return resp.data;
}

/** Goods received: adds qty to stock. */
export async function stockIn(storeId: number, productId: number, qty: string, notes?: string, expiryDate?: string): Promise<QtyResponse> {
  const resp = await httpClient.post<QtyResponse>('/inventory/stock-in', {
    store_id: storeId,
    product_id: productId,
    qty,
    notes: notes || null,
    expiry_date: expiryDate || null,
  });
  return resp.data;
}

export async function getExpiringProducts(storeId: number, days = 30): Promise<ExpiringBatchOut[]> {
  const resp = await httpClient.get<ExpiringBatchOut[]>('/inventory/expiring', {
    params: { store_id: storeId, days },
  });
  return resp.data;
}

/** Stock-take correction: sets the counted qty. A reason is required. */
export async function adjustStock(storeId: number, productId: number, newQty: string, notes: string): Promise<QtyResponse> {
  const resp = await httpClient.post<QtyResponse>('/inventory/adjust', {
    store_id: storeId,
    product_id: productId,
    new_qty: newQty,
    notes,
  });
  return resp.data;
}

/** Per-product low-stock level; null = use the store-wide default from Settings. */
export async function setThreshold(storeId: number, productId: number, threshold: string | null): Promise<void> {
  await httpClient.post('/inventory/threshold', { store_id: storeId, product_id: productId, threshold });
}

export async function getLedger(storeId: number, productId?: number): Promise<InventoryTxnOut[]> {
  const resp = await httpClient.get<InventoryTxnOut[]>('/inventory/ledger', {
    params: { store_id: storeId, product_id: productId },
  });
  return resp.data;
}
