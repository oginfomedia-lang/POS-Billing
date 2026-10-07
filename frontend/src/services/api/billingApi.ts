// Sale draft, items, hold, resume, complete API calls.
import type { ReceiptOut, SaleOut, TenderMethod } from '../../types/sale';
import { httpClient } from './httpClient';

/** Returns the cashier's open bill, creating one if needed. 409 = no open shift. */
export async function createSale(): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>('/sales');
  return resp.data;
}

export async function addItem(saleId: number, productId: number, qty = 1): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/items`, { product_id: productId, qty });
  return resp.data;
}

export async function updateItem(saleId: number, itemId: number, qty: number): Promise<SaleOut> {
  const resp = await httpClient.put<SaleOut>(`/sales/${saleId}/items/${itemId}`, { qty });
  return resp.data;
}

export async function removeItem(saleId: number, itemId: number): Promise<SaleOut> {
  const resp = await httpClient.delete<SaleOut>(`/sales/${saleId}/items/${itemId}`);
  return resp.data;
}

export interface ManualDiscountInput {
  amount: string;
  reason: string;
  approver_username: string;
  approver_pin: string;
}

/** Counter discount on one line; a manager/admin approves with their PIN. amount "0" removes it. */
export async function setManualDiscount(saleId: number, itemId: number, data: ManualDiscountInput): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/items/${itemId}/manual-discount`, data);
  return resp.data;
}

export async function holdSale(saleId: number, note?: string): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/hold`, { note: note || null });
  return resp.data;
}

export async function resumeSale(saleId: number): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/resume`);
  return resp.data;
}

export async function completeSale(
  saleId: number,
  method: TenderMethod,
  cashTendered?: string,
  reference?: string,
): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/complete`, {
    method,
    cash_tendered: method === 'cash' ? cashTendered : null,
    reference: reference || null,
  });
  return resp.data;
}

export async function voidSale(saleId: number): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/void`);
  return resp.data;
}

export async function listHeld(): Promise<SaleOut[]> {
  const resp = await httpClient.get<SaleOut[]>('/sales/held');
  return resp.data;
}

export async function getReceipt(saleId: number): Promise<ReceiptOut> {
  const resp = await httpClient.get<ReceiptOut>(`/sales/${saleId}/receipt`);
  return resp.data;
}
