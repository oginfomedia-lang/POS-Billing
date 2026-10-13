import type {
  PagedResponse,
  SupplierPaymentMethod,
  SupplierPaymentOut,
  SupplierPaymentType,
} from '../../types/api';
import { httpClient } from './httpClient';

export interface PaymentAllocationIn {
  invoice_id: number;
  allocated_amount: number;
}

export interface SupplierPaymentCreatePayload {
  supplier_id: number;
  store_id?: number | null;
  payment_date: string;
  amount: number;
  payment_type?: SupplierPaymentType;
  payment_method?: SupplierPaymentMethod;
  reference_number?: string | null;
  bank_account?: string | null;
  notes?: string | null;
  allocations?: PaymentAllocationIn[];
}

export interface SupplierPaymentListParams {
  page?: number;
  per_page?: number;
  supplier_id?: number | null;
}

export const supplierPaymentApi = {
  list(params?: SupplierPaymentListParams) {
    return httpClient.get<PagedResponse<SupplierPaymentOut>>('/supplier-payments', { params });
  },
  get(id: number) {
    return httpClient.get<SupplierPaymentOut>(`/supplier-payments/${id}`);
  },
  create(data: SupplierPaymentCreatePayload) {
    return httpClient.post<SupplierPaymentOut>('/supplier-payments', data);
  },
  /** Put the unused part of an advance against invoices that have arrived. */
  applyAdvance(id: number, allocations: PaymentAllocationIn[]) {
    return httpClient.post<SupplierPaymentOut>(`/supplier-payments/${id}/apply`, { allocations });
  },
  void(id: number) {
    return httpClient.post<SupplierPaymentOut>(`/supplier-payments/${id}/void`, {});
  },
};
