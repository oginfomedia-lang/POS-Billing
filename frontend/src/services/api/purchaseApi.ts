import type {
  GoodsReceiptOut,
  PagedResponse,
  POPaymentHistoryOut,
  POPaymentSummary,
  PurchaseDashboard,
  PurchaseOrderOut,
  PurchaseStatus,
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
};
