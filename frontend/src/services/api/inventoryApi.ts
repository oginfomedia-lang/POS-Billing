// Inventory API calls.
import type {
  BatchOut,
  ExpiringBatchOut,
  InventoryTxnOut,
  RefillOut,
  StockLevelOut,
  SupplierReturnOut,
  TransferDirection,
} from '../../types/inventory';
import { httpClient } from './httpClient';

interface QtyResponse {
  product_id: number;
  qty_on_hand: string;
}

/** q: name, SKU, barcode, or how the name sounds ("sakhar" finds "साखर"). */
export async function getStockLevels(storeId: number, q?: string): Promise<StockLevelOut[]> {
  const resp = await httpClient.get<StockLevelOut[]>('/inventory', { params: { store_id: storeId, q: q || undefined } });
  return resp.data;
}

/** Goods received: adds qty to stock. */
export async function stockIn(
  storeId: number,
  productId: number,
  qty: string,
  notes?: string,
  expiryDate?: string,
  batchNumber?: string,
  toGodown = false,
): Promise<QtyResponse> {
  const resp = await httpClient.post<QtyResponse>('/inventory/stock-in', {
    store_id: storeId,
    product_id: productId,
    qty,
    notes: notes || null,
    expiry_date: expiryDate || null,
    batch_number: batchNumber || null,
    to_godown: toGodown,
  });
  return resp.data;
}

/** The product's batches with stock, in the order sales take them (earliest expiry first). */
export async function getBatches(storeId: number, productId: number): Promise<BatchOut[]> {
  const resp = await httpClient.get<BatchOut[]>('/inventory/batches', {
    params: { store_id: storeId, product_id: productId },
  });
  return resp.data;
}

/** Takes expired / damaged goods of one batch out of stock. qty null = all that is left. */
export async function writeOffBatch(batchId: number, qty: string | null, reason: string, fromGodown = false): Promise<void> {
  await httpClient.post(`/inventory/batches/${batchId}/write-off`, { qty, reason, from_godown: fromGodown });
}

/** Sends goods of a GRN batch back to its supplier: out of stock, and a debit note for their value
 *  (taken off the supplier's bill, or kept as credit with them). qty null = all that is left. */
export async function returnBatchToSupplier(
  batchId: number, qty: string | null, reason: string, fromGodown = false,
): Promise<SupplierReturnOut> {
  const resp = await httpClient.post<SupplierReturnOut>(`/inventory/batches/${batchId}/return-to-supplier`, {
    qty, reason, from_godown: fromGodown,
  });
  return resp.data;
}

/** Stock-take correction: sets the counted qty. A reason is required.
 *  location: what was counted; null = everything (shop + godown). */
export async function adjustStock(
  storeId: number,
  productId: number,
  newQty: string,
  notes: string,
  location: 'shop' | 'godown' | null = null,
): Promise<QtyResponse> {
  const resp = await httpClient.post<QtyResponse>('/inventory/adjust', {
    store_id: storeId,
    product_id: productId,
    new_qty: newQty,
    notes,
    location,
  });
  return resp.data;
}

/** This branch's own selling price (before GST); null = go back to the head-office price. */
export async function setStorePrice(storeId: number, productId: number, price: string | null): Promise<void> {
  await httpClient.post('/inventory/price', { store_id: storeId, product_id: productId, price });
}

/** Per-product low-stock level; null = use the store-wide default from Settings. */
export async function setThreshold(storeId: number, productId: number, threshold: string | null): Promise<void> {
  await httpClient.post('/inventory/threshold', { store_id: storeId, product_id: productId, threshold });
}

export async function getExpiringProducts(storeId: number, days = 30): Promise<ExpiringBatchOut[]> {
  const resp = await httpClient.get<ExpiringBatchOut[]>('/inventory/expiring', {
    params: { store_id: storeId, days },
  });
  return resp.data;
}

/** Move goods between the godown and the shop shelf. */
export async function transferStock(
  storeId: number,
  productId: number,
  qty: string,
  direction: TransferDirection,
  notes?: string,
): Promise<void> {
  await httpClient.post('/inventory/transfer', {
    store_id: storeId, product_id: productId, qty, direction, notes: notes || null,
  });
}

/** Refill alert level for the shop shelf; null = no alert. */
export async function setShelfMin(storeId: number, productId: number, level: string | null): Promise<void> {
  await httpClient.post('/inventory/shelf-min', { store_id: storeId, product_id: productId, shelf_min_qty: level });
}

/** Shelves at / below their refill level with stock waiting in the godown. */
export async function getRefillList(storeId: number): Promise<RefillOut[]> {
  const resp = await httpClient.get<RefillOut[]>('/inventory/refill', { params: { store_id: storeId } });
  return resp.data;
}

export async function getLedger(storeId: number, productId?: number): Promise<InventoryTxnOut[]> {
  const resp = await httpClient.get<InventoryTxnOut[]>('/inventory/ledger', {
    params: { store_id: storeId, product_id: productId },
  });
  return resp.data;
}
