// Keeps offline billing ready and catches up afterwards:
// - while the server is up, refreshes this counter's catalogue (products, prices, offers) every few minutes;
// - when the server is back, uploads the bills made meanwhile (POST /sales/offline; uploading twice is harmless).
import axios from 'axios';
import { httpClient, getErrorMessage } from '../services/api/httpClient';
import type { OfflineBill, OfflineCatalog } from './types';

function bridge() {
  return typeof window !== 'undefined' ? window.posBridge?.offline : undefined;
}

export function hasOfflineSupport(): boolean {
  return Boolean(bridge());
}

export async function refreshCatalog(storeId: number): Promise<void> {
  const files = bridge();
  if (!files) return;
  const resp = await httpClient.get<OfflineCatalog>('/pos/offline-catalog', { params: { store_id: storeId } });
  await files.saveCatalog(storeId, resp.data);
}

export async function loadCatalog(storeId: number): Promise<OfflineCatalog | null> {
  return ((await bridge()?.loadCatalog(storeId)) as OfflineCatalog | null) ?? null;
}

export async function queuedBills(): Promise<OfflineBill[]> {
  return ((await bridge()?.listQueue()) as OfflineBill[] | undefined) ?? [];
}

/** The upload body: OfflineSaleIn (backend app/schemas/offline_schemas.py). */
function uploadBody(bill: OfflineBill) {
  return {
    offline_id: bill.offline_id,
    bill_number: bill.bill_number,
    shift_id: bill.shift_id,
    billed_at: bill.billed_at,
    items: bill.items.map((i) => ({
      product_id: i.product_id, product_name: i.product_name, qty: i.qty, unit_price: i.unit_price,
      tax_rate: i.tax_rate, mrp: i.mrp, hsn_code: i.hsn_code, discount_amount: i.discount_amount,
      offer_id: i.offer_id, offer_name: i.offer_name, offer_discount: i.offer_discount,
    })),
    bill_offer_id: bill.bill_offer_id,
    bill_offer_name: bill.bill_offer_name,
    bill_offer_discount: bill.bill_offer_discount,
    total: bill.total,
    cash_tendered: bill.cash_tendered,
  };
}

let uploading = false;

/** Uploads the logged-in cashier's waiting bills, oldest first. Returns how many are still waiting (anyone's).
 * Stops at the first network error; a bill the server refuses keeps its reason and is skipped. */
export async function uploadQueued(cashierId: number): Promise<number> {
  const files = bridge();
  if (!files || uploading) return (await queuedBills()).length;
  uploading = true;
  try {
    for (const bill of await queuedBills()) {
      // A bill can only be uploaded by its own cashier (the server checks the shift is theirs).
      if (bill.cashier_id !== cashierId || bill.sync_error) continue;
      try {
        const resp = await httpClient.post<{ id: number }>('/sales/offline', uploadBody(bill));
        await files.markSynced(bill.offline_id, resp.data.id);
      } catch (err) {
        if (axios.isAxiosError(err) && err.response && err.response.status >= 400 && err.response.status < 500
            && err.response.status !== 401) {
          await files.markFailed(bill.offline_id, getErrorMessage(err));
          continue;
        }
        break; // server gone again, or the login expired: try later
      }
    }
  } finally {
    uploading = false;
  }
  return (await queuedBills()).length;
}
