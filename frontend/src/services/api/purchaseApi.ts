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
    product_id: number; qty: number; unit_price: number; discount_percent: number; tax_rate: number;
    mrp: number | null; hsn_code: string | null; batch_number: string | null; expiry_date: string | null;
    to_shop: boolean;
    bill_description?: string | null; // the line as printed on the bill (read from it): remembered for the supplier
  }[];
}

/** A saved direct purchase, back in the form to correct it. */
export interface DirectPurchaseEdit {
  po_id: number;
  po_number: string;
  supplier_id: number;
  store_id: number;
  invoice_number: string;
  invoice_date: string;
  due_date: string | null;
  other_charges: number;
  grand_total: number;
  difference_reason: string | null;
  bill_file_name: string | null;
  items: {
    product: BillProduct; qty: number; unit_price: number; discount_percent: number; tax_rate: number;
    mrp: number | null; hsn_code: string | null; batch_number: string | null; expiry_date: string | null;
  }[];
}

/** A product suggested for a line read from the bill (same fields as the product search list). */
export interface BillProduct {
  id: number;
  name: string;
  sku: string | null;
  price: number | null; // last purchase cost
  selling: number | null;
  tax_rate: number;
  score: number | null; // how close the name is, 0-100
}

export type BillLineStatus = 'matched' | 'check' | 'not_found';
/** Texts: purchases.direct.problem.<code> */
export type BillProblem =
  | 'rate_from_amount' | 'qty_from_amount' | 'math_mismatch' | 'amount_missing' | 'bad_gst' | 'hard_to_read'
  | 'mrp_below_rate' | 'discounts_combined';
/** Texts: purchases.direct.warning.<code> */
export type BillWarning = 'no_lines' | 'lines_total_mismatch' | 'bill_totals_mismatch' | 'pages_skipped' | 'used_template'
  | 'gst_from_bill';

/** One item line read from the supplier's bill. */
export interface BillLine {
  description: string;
  hsn_code: string | null;
  qty: number | null; // free units included
  free_qty: number | null;
  unit_price: number | null; // goes in "Rate on bill": before GST (and before discount_percent)
  bill_rate: number | null;
  discount: number | null; // as printed: a % or a ₹ amount
  discount_percent: number; // what goes in "Disc %" (0 = none, or already taken off unit_price)
  tax_rate: number | null;
  mrp: number | null;
  batch_number: string | null;
  expiry_date: string | null;
  amount: number | null;
  status: BillLineStatus;
  product: BillProduct | null;
  match_source: string | null;
  candidates: BillProduct[];
  problems: BillProblem[];
  confidence: number;
}

/** What "Read from bill" found. Nothing is saved until the bill is saved as usual. */
export interface BillExtract {
  source: 'pdf_text' | 'ocr';
  supplier_id: number | null;
  supplier_name: string | null;
  gstin: string | null;
  supplier_check: 'matched' | 'different' | 'not_found' | 'unverified'; // who sent the bill, from its GSTIN
  invoice_number: string | null;
  invoice_date: string | null;
  taxable_total: number | null;
  cgst: number | null;
  sgst: number | null;
  igst: number | null;
  round_off: number | null;
  grand_total: number | null;
  lines_total: number | null;
  lines: BillLine[];
  warnings: BillWarning[];
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

  createDirect(data: DirectPurchasePayload, files: File[]) {
    const form = new FormData();
    form.append('data', JSON.stringify(data));
    files.forEach((f) => form.append('file', f));
    return httpClient.post<{ purchase_order: PurchaseOrderOut }>('/purchases/direct', form, { timeout: 60_000 });
  },

  /** A saved direct purchase, to correct it in the same form. */
  getDirect(id: number) {
    return httpClient.get<DirectPurchaseEdit>(`/purchases/${id}/direct`);
  },

  /** Corrects a saved direct purchase. No files = the bill already saved is kept. */
  updateDirect(id: number, data: DirectPurchasePayload, files: File[]) {
    const form = new FormData();
    form.append('data', JSON.stringify(data));
    files.forEach((f) => form.append('file', f));
    return httpClient.put<{ purchase_order: PurchaseOrderOut }>(`/purchases/${id}/direct`, form, { timeout: 60_000 });
  },

  /** Reads the supplier's bill (one PDF, or photos top to bottom) on the Main PC and returns a draft. Saves nothing. */
  extractBill(files: File[], storeId: number, supplierId?: number) {
    const form = new FormData();
    files.forEach((f) => form.append('file', f));
    form.append('store_id', String(storeId));
    if (supplierId) form.append('supplier_id', String(supplierId));
    // The server stops reading at OCR_TIMEOUT_SECONDS (150 s) and answers with what it read.
    return httpClient.post<BillExtract>('/purchases/direct/extract', form, { timeout: 200_000 });
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
