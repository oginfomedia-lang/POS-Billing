// Customers and their reward-points passbook (admin / manager screens).
import type { PagedResponse } from '../../types/api';
import type { CustomerOut, RewardTxnOut } from '../../types/customer';
import { httpClient } from './httpClient';

/** search matches part of the mobile number or the name. */
export async function listCustomers(search: string, page: number): Promise<PagedResponse<CustomerOut>> {
  const resp = await httpClient.get<PagedResponse<CustomerOut>>('/customers', {
    params: { search: search.trim() || undefined, page },
  });
  return resp.data;
}

export async function getCustomerTransactions(customerId: number): Promise<PagedResponse<RewardTxnOut>> {
  const resp = await httpClient.get<PagedResponse<RewardTxnOut>>(`/customers/${customerId}/transactions`);
  return resp.data;
}
