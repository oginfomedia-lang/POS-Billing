// Customers and their reward-points and Udhari (credit) passbooks.
import type { PagedResponse } from '../../types/api';
import type {
  CreditRepaymentRequest,
  CreditTxnOut,
  CustomerCreditInfo,
  CustomerOut,
  RewardTxnOut,
} from '../../types/customer';
import { httpClient } from './httpClient';

/** Search matches part of the mobile number or the name. withDues filters for customers with outstanding balance. */
export async function listCustomers(search: string, page: number, withDues?: boolean): Promise<PagedResponse<CustomerOut>> {
  const resp = await httpClient.get<PagedResponse<CustomerOut>>('/customers', {
    params: { search: search.trim() || undefined, page, with_dues: withDues || undefined },
  });
  return resp.data;
}

/** Add or correct a customer's name ('' removes it; refused while the customer owes udhari). */
export async function updateCustomerName(customerId: number, name: string): Promise<CustomerOut> {
  const resp = await httpClient.put<CustomerOut>(`/customers/${customerId}/name`, { name: name.trim() || null });
  return resp.data;
}

/** Update customer's maximum allowable credit limit. */
export async function updateCustomerCreditLimit(customerId: number, creditLimit: string | null): Promise<CustomerOut> {
  const resp = await httpClient.put<CustomerOut>(`/customers/${customerId}/credit-limit`, {
    credit_limit: creditLimit ? creditLimit : null,
  });
  return resp.data;
}

export async function getCustomerTransactions(customerId: number): Promise<PagedResponse<RewardTxnOut>> {
  const resp = await httpClient.get<PagedResponse<RewardTxnOut>>(`/customers/${customerId}/transactions`);
  return resp.data;
}

/** Fetch customer's live credit balance and remaining limit for POS checkout. */
export async function getCustomerCredit(mobile: string): Promise<CustomerCreditInfo> {
  const resp = await httpClient.get<CustomerCreditInfo>(`/customers/${mobile}/credit`);
  return resp.data;
}

/** Record a repayment towards customer's dues (Khata settlement). */
export async function repayCustomerCredit(customerId: number, data: CreditRepaymentRequest): Promise<CreditTxnOut> {
  const resp = await httpClient.post<CreditTxnOut>(`/customers/${customerId}/repay`, data);
  return resp.data;
}

/** Fetch customer's Khata passbook statement. */
export async function getCustomerCreditTransactions(customerId: number): Promise<PagedResponse<CreditTxnOut>> {
  const resp = await httpClient.get<PagedResponse<CreditTxnOut>>(`/customers/${customerId}/credit-transactions`);
  return resp.data;
}
