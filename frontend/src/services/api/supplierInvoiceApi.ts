import type { PagedResponse, SupplierInvoiceOut, SupplierInvoiceStatus } from '../../types/api';
import { httpClient } from './httpClient';

export interface SupplierInvoiceCreatePayload {
  supplier_id: number;
  store_id?: number | null;
  purchase_order_id?: number | null;
  grn_ids?: number[];
  invoice_number: string;
  invoice_date: string;
  due_date?: string | null;
  subtotal: number;
  tax_amount?: number;
  other_charges?: number;
  grand_total: number;
  notes?: string | null;
}

export interface SupplierInvoiceUpdatePayload {
  due_date?: string | null;
  notes?: string | null;
  verification_status?: 'pending' | 'verified' | 'disputed';
}

export interface SupplierInvoiceListParams {
  page?: number;
  per_page?: number;
  supplier_id?: number | null;
  payment_status?: SupplierInvoiceStatus | '';
  date_from?: string;
  date_to?: string;
}

export const supplierInvoiceApi = {
  list(params?: SupplierInvoiceListParams) {
    return httpClient.get<PagedResponse<SupplierInvoiceOut>>('/supplier-invoices', { params });
  },
  get(id: number) {
    return httpClient.get<SupplierInvoiceOut>(`/supplier-invoices/${id}`);
  },
  create(data: SupplierInvoiceCreatePayload) {
    return httpClient.post<SupplierInvoiceOut>('/supplier-invoices', data);
  },
  update(id: number, data: SupplierInvoiceUpdatePayload) {
    return httpClient.put<SupplierInvoiceOut>(`/supplier-invoices/${id}`, data);
  },
};
