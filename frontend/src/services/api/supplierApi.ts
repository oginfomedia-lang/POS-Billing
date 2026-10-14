import type {
  PagedResponse,
  SupplierDashboard,
  SupplierGRNOut,
  SupplierLedgerEntry,
  SupplierOut,
  SupplierProductOut,
  SupplierSummary,
} from '../../types/api';
import { httpClient } from './httpClient';

export interface SupplierCreatePayload {
  supplier_code?: string;
  company_name: string;
  contact_person?: string;
  phone?: string;
  alt_phone?: string;
  email?: string;
  gstin?: string;
  pan?: string;
  billing_address?: string;
  city?: string;
  state?: string;
  pincode?: string;
  country?: string;
  payment_terms?: string;
  opening_balance?: number;
  notes?: string;
}

export interface SupplierUpdatePayload extends Partial<SupplierCreatePayload> {
  is_active?: boolean;
}

export interface SupplierProductPayload {
  product_id: number;
  supplier_product_code?: string | null;
  purchase_price?: number | null;
  min_order_qty?: number;
  lead_time_days?: number | null;
  is_preferred?: boolean;
  notes?: string | null;
}

export interface PoProductRow {
  id: number;
  name: string;
  sku: string | null;
  purchase_price: number;
  tax_rate: number;
  supplier_product_code: string | null;
  min_order_qty: number;
  is_preferred: boolean;
}

export const supplierApi = {
  dashboard() {
    return httpClient.get<SupplierDashboard>('/suppliers/dashboard');
  },
  list(params?: { page?: number; per_page?: number; status?: 'active' | 'inactive'; q?: string }) {
    return httpClient.get<PagedResponse<SupplierOut>>('/suppliers', { params });
  },
  get(id: number) {
    return httpClient.get<SupplierOut>(`/suppliers/${id}`);
  },
  create(data: SupplierCreatePayload) {
    return httpClient.post<SupplierOut>('/suppliers', data);
  },
  update(id: number, data: SupplierUpdatePayload) {
    return httpClient.put<SupplierOut>(`/suppliers/${id}`, data);
  },
  toggleStatus(id: number) {
    return httpClient.patch<SupplierOut>(`/suppliers/${id}/status`);
  },
  getSummary(id: number) {
    return httpClient.get<SupplierSummary>(`/suppliers/${id}/summary`);
  },
  getLedger(id: number, params?: { date_from?: string; date_to?: string }) {
    return httpClient.get<SupplierLedgerEntry[]>(`/suppliers/${id}/ledger`, { params });
  },
  /** Goods received from the supplier, with value and invoice; uninvoiced = not billed yet. */
  listGrns(id: number, uninvoiced = false) {
    return httpClient.get<SupplierGRNOut[]>(`/suppliers/${id}/grns`, { params: uninvoiced ? { uninvoiced: 1 } : {} });
  },
  listProducts(id: number) {
    return httpClient.get<SupplierProductOut[]>(`/suppliers/${id}/products`);
  },
  getPoProducts(id: number) {
    return httpClient.get<PoProductRow[]>(`/suppliers/${id}/po-products`);
  },
  addProduct(id: number, data: SupplierProductPayload) {
    return httpClient.post<SupplierProductOut>(`/suppliers/${id}/products`, data);
  },
  updateProduct(id: number, spId: number, data: Partial<SupplierProductPayload>) {
    return httpClient.put<SupplierProductOut>(`/suppliers/${id}/products/${spId}`, data);
  },
  removeProduct(id: number, spId: number) {
    return httpClient.delete<{ message: string }>(`/suppliers/${id}/products/${spId}`);
  },
};
