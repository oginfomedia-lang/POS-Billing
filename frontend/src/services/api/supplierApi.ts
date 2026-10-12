import type { PagedResponse, SupplierDashboard, SupplierOut } from '../../types/api';
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
  notes?: string;
}

export interface SupplierUpdatePayload extends Partial<SupplierCreatePayload> {
  is_active?: boolean;
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
};
