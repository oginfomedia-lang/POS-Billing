// Sale draft, items, hold, resume, complete API calls.
import type { DigitalMethod, PaymentIntentOut, ReceiptOut, RewardInfo, SaleOut, TenderMethod } from '../../types/sale';
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

/** Optional customer mobile on the open bill (null / '' clears it). Doesn't touch a live QR / card payment. */
export async function setCustomerMobile(saleId: number, mobile: string | null): Promise<SaleOut> {
  const resp = await httpClient.put<SaleOut>(`/sales/${saleId}/customer-mobile`, { mobile: mobile || null });
  return resp.data;
}

/** Customer's points balance for the payment screen (doesn't register anyone). */
export async function getRewards(mobile: string): Promise<RewardInfo> {
  const resp = await httpClient.get<RewardInfo>(`/customers/${mobile}/rewards`);
  return resp.data;
}

/** Use blocks × block_points of the customer's points on the open bill (0 removes). Re-prices the bill. */
export async function redeemPoints(saleId: number, blocks: number): Promise<SaleOut> {
  const resp = await httpClient.post<SaleOut>(`/sales/${saleId}/redeem-points`, { blocks });
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

/** Card: pushes the bill total to this counter's card machine. UPI: creates a Razorpay QR for exactly the total. */
export async function startPayment(saleId: number, method: DigitalMethod): Promise<PaymentIntentOut> {
  const resp = await httpClient.post<PaymentIntentOut>(`/sales/${saleId}/payment-intents`, { method });
  return resp.data;
}

/** Asks the backend (which asks Razorpay) whether the customer has paid. When paid, `sale` is the completed bill. */
export async function checkPayment(intentId: number): Promise<PaymentIntentOut> {
  const resp = await httpClient.get<PaymentIntentOut>(`/payment-intents/${intentId}`);
  return resp.data;
}

/** Closes the QR / clears the card machine. Safe to call if it was already paid or cancelled. */
export async function cancelPayment(intentId: number): Promise<void> {
  await httpClient.post(`/payment-intents/${intentId}/cancel`);
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
