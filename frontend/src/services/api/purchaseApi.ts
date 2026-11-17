import type {
  GoodsReceiptOut,
  PagedResponse,
  POPaymentHistoryOut,
  POPaymentSummary,
  POSentVia,
  PurchaseDashboard,
  PurchaseOrderOut,
  PurchaseStatus,
  SupplierMessageOut,
} from '../../types/api';
import { httpClient } from './httpClient';

export interface PurchaseOrderItemPayload {
  product_id: number;
  ordered_qty: number;
  unit_price: number;
  discount_percent?: number;
  tax_rate?: number;
}

export interface PurchaseOrderCreatePayload {
  supplier_id: number;
  store_id?: number | null;
  purchase_date: string;
  expected_delivery_date?: string | null;
  reference_number?: string | null;
  notes?: string | null;
  internal_remarks?: string | null;
  shipping_address?: string | null;
  shipping_charges?: number;
  other_charges?: number;
  items: PurchaseOrderItemPayload[];
}

export type PurchaseOrderUpdatePayload = Partial<Omit<PurchaseOrderCreatePayload, 'items'>> & {
  items?: PurchaseOrderItemPayload[];
};

export interface GoodsReceiptItemPayload {
  purchase_order_item_id: number;
  qty_received: number;
  qty_accepted?: number | null;
  qty_rejected?: number;
  qty_damaged?: number;
  expiry_date?: string | null;
  batch_number?: string | null;
  mfg_date?: string | null;
  remarks?: string | null;
  /** With the godown on: true = straight to the shop shelf instead of the godown. */
  to_shop?: boolean;
  /** From the supplier's bill, only when different: corrects the PO line (before any of it came in). */
  bill_unit_price?: number; // before discount and GST
  bill_tax_rate?: number;
  /** Goes on the product. */
  mrp?: number;
  hsn_code?: string;
}

export interface DirectPurchasePayload {
  supplier_id: number;
  store_id: number;
  invoice_number: string;
  invoice_date: string;
  due_date: string | null;
  other_charges: number;
  grand_total: number;
  difference_reason: string | null;
  items: {
    product_id: number; qty: number; unit_price: number; tax_rate: number;
    mrp: number | null; hsn_code: string | null; batch_number: string | null; expiry_date: string | null;
    to_shop: boolean;
  }[];
}


export interface GoodsReceiptCreatePayload {
  received_at?: string | null;
  notes?: string | null;
  items: GoodsReceiptItemPayload[];
}

export interface PurchaseListParams {
  page?: number;
  per_page?: number;
  status?: PurchaseStatus | '';
  supplier_id?: number | null;
  q?: string;
  date_from?: string;
  date_to?: string;
  payment_filter?: 'has_outstanding' | 'has_payments';
}

export const purchaseApi = {
  dashboard() {
    return httpClient.get<PurchaseDashboard>('/purchases/dashboard');
  },
  list(params?: PurchaseListParams) {
    return httpClient.get<PagedResponse<PurchaseOrderOut>>('/purchases', { params });
  },
  get(id: number) {
    return httpClient.get<PurchaseOrderOut>(`/purchases/${id}`);
  },
  create(data: PurchaseOrderCreatePayload) {
    return httpClient.post<PurchaseOrderOut>('/purchases', data);
  },
  update(id: number, data: PurchaseOrderUpdatePayload) {
    return httpClient.put<PurchaseOrderOut>(`/purchases/${id}`, data);
  },
  placeOrder(id: number) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/place`, {});
  },
  submitForApproval(id: number) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/submit`, {});
  },
  approveOrder(id: number) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/approve`, {});
  },
  closeOrder(id: number) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/close`, {});
  },
  cancelOrder(id: number) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/cancel`, {});
  },
  receiveGoods(id: number, data: GoodsReceiptCreatePayload) {
    return httpClient.post<GoodsReceiptOut>(`/purchases/${id}/receipts`, data);
  },
  listReceipts(id: number) {
    return httpClient.get<GoodsReceiptOut[]>(`/purchases/${id}/receipts`);
  },
  getPaymentSummary(id: number) {
    return httpClient.get<POPaymentSummary>(`/purchases/${id}/payment-summary`);
  },
  getPaymentHistory(id: number) {
    return httpClient.get<POPaymentHistoryOut>(`/purchases/${id}/payment-history`);
  },
  getSupplierMessage(id: number) {
    return httpClient.get<SupplierMessageOut>(`/purchases/${id}/supplier-message`);
  },
  /** Emails the PO now (the screen waits up to ~20 s); the result is in email_status / email_error. */
  emailPo(id: number) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/email`, {}, { timeout: 60_000 });
  },
  markSent(id: number, via: POSentVia) {
    return httpClient.post<PurchaseOrderOut>(`/purchases/${id}/mark-sent`, { via });
  },
  /** Saves the PO as a PDF (PO-number.pdf) to the user's computer. */
  async downloadPdf(id: number, poNumber: string): Promise<void> {
    const resp = await httpClient.get<Blob>(`/purchases/${id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(resp.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${poNumber}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },

  createDirect(data: DirectPurchasePayload, file: File) {
    const form = new FormData();
    form.append('data', JSON.stringify(data));
    form.append('file', file);
    return httpClient.post<{ purchase_order: PurchaseOrderOut }>('/purchases/direct', form, {timeout: 60_000});
  },
};

/** Opens WhatsApp with the message: through the Electron app, or a new tab in a plain browser. */
export async function openWhatsApp(url: string): Promise<void> {
  if (typeof window !== 'undefined' && window.posBridge?.openWhatsApp) {
    await window.posBridge.openWhatsApp(url);
  } else {
    window.open(url, '_blank', 'noopener');
  }
}
