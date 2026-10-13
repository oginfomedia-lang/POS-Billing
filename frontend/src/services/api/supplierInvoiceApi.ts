import type { PagedResponse, SupplierInvoiceOut, SupplierInvoiceStatus } from '../../types/api';
import { httpClient } from './httpClient';

export interface SupplierInvoiceCreatePayload {
  supplier_id: number;
  store_id?: number | null;
  /** The goods receipts (all from one PO) this bill is for. */
  grn_ids: number[];
  invoice_number: string;
  invoice_date: string;
  /** Leave out: due date comes from the supplier's payment terms. */
  due_date?: string | null;
  subtotal: number;
  tax_amount?: number;
  other_charges?: number;
  grand_total: number;
  notes?: string | null;
  /** Required when the bill differs from the goods received by more than ₹1. */
  difference_reason?: string | null;
}

/** What the chosen GRNs are worth (for the add-invoice form). */
export interface GRNPreview {
  purchase_order_id: number;
  po_number: string;
  received_value: string;
  grn_numbers: string[];
}

export interface SupplierInvoiceUpdatePayload {
  invoice_number?: string;
  invoice_date?: string;
  subtotal?: number;
  tax_amount?: number;
  due_date?: string | null;
  notes?: string | null;
  verification_status?: 'pending' | 'verified' | 'disputed';
  grand_total?: number;
  other_charges?: number;
  difference_reason?: string | null;
}

export interface SupplierInvoiceListParams {
  page?: number;
  per_page?: number;
  supplier_id?: number | null;
  /** 'outstanding' = unpaid or partly paid. */
  payment_status?: SupplierInvoiceStatus | 'outstanding' | '';
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
  /** The supplier's bill: its details plus the scanned bill / PDF (required). */
  create(data: SupplierInvoiceCreatePayload, file: File) {
    const form = new FormData();
    form.append('data', JSON.stringify(data));
    form.append('file', file);
    return httpClient.post<SupplierInvoiceOut>('/supplier-invoices', form, { timeout: 60_000 });
  },
  previewGrns(supplierId: number, grnIds: number[]) {
    return httpClient.get<GRNPreview>('/supplier-invoices/preview-grns', {
      params: { supplier_id: supplierId, grn_ids: grnIds.join(',') },
    });
  },
  /** Wrong / duplicate bill (nothing paid on it): its GRNs can be billed again. */
  cancel(id: number, reason: string) {
    return httpClient.post<SupplierInvoiceOut>(`/supplier-invoices/${id}/cancel`, { reason });
  },
  update(id: number, data: SupplierInvoiceUpdatePayload) {
    return httpClient.put<SupplierInvoiceOut>(`/supplier-invoices/${id}`, data);
  },
};
