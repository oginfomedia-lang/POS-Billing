// Return API calls: look up a bill, create a return (cash refund, manager PIN), fetch a credit note.
import type { BillForMobile, CreateReturnInput, ReturnableBill, ReturnOut } from '../../types/returns';
import { httpClient } from './httpClient';

/** The paid bill with what can still be returned on each line. 404 = no such paid bill. */
export async function getReturnableBill(billNumber: string): Promise<ReturnableBill> {
  const resp = await httpClient.get<ReturnableBill>(`/returns/bill/${encodeURIComponent(billNumber.trim())}`);
  return resp.data;
}

/** A customer's recent paid bills (newest first), for returns without the receipt. */
export async function getBillsForMobile(mobile: string): Promise<BillForMobile[]> {
  const resp = await httpClient.get<BillForMobile[]>('/returns/bills', { params: { mobile } });
  return resp.data;
}

export async function createReturn(data: CreateReturnInput): Promise<ReturnOut> {
  const resp = await httpClient.post<ReturnOut>('/returns', data);
  return resp.data;
}

export async function getReturn(returnId: number): Promise<ReturnOut> {
  const resp = await httpClient.get<ReturnOut>(`/returns/${returnId}`);
  return resp.data;
}
