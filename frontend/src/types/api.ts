// Shared API response and error types.

/** Every backend error looks like this (see backend/app/errors/handlers.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  database: 'up' | 'down';
  server_time: string;
}

export type UserRole = 'admin' | 'manager' | 'cashier';

export interface UserOut {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  store_id: number | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserOut;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
}

export interface StoreOut {
  id: number;
  name: string;
  address: string | null;
  phone: string | null;
  gstin: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CounterOut {
  id: number;
  code: string;
  label: string;
  store_id: number;
  is_active: boolean;
  edc_device_id: string | null; // Razorpay POS card machine on this counter; null = none
  created_at: string;
}

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export type BackupStatus = 'running' | 'success' | 'failed' | 'deleted';
export type BackupStorageLocation = 'local' | 's3' | 'sftp';
export type CloudUploadStatus = 'pending' | 'success' | 'failed';
export type RestoreStatus = 'running' | 'success' | 'failed';

export interface CloudUploadAttemptOut {
  id: number;
  backup_run_id: number;
  provider: string;
  bucket: string | null;
  key: string | null;
  status: CloudUploadStatus;
  bytes_uploaded: number | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface RestoreRecordOut {
  id: number;
  backup_run_id: number | null;
  target_db: string;
  status: RestoreStatus;
  triggered_by_id: number | null;
  safety_backup_path: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ReplicationReplicaOut {
  client_addr: string | null;
  state: string;
  sent_lsn: string;
  replay_lsn: string;
  lag_bytes: number | null;
  lag_seconds: number | null;
}

export interface ReplicationStatusOut {
  replicas: ReplicationReplicaOut[];
  replica_count: number;
  is_healthy: boolean;
  error?: string;
}

export interface BackupRunOut {
  id: number;
  filename: string;
  file_size_bytes: number | null;
  checksum_sha256: string | null;
  status: BackupStatus;
  storage_location: BackupStorageLocation;
  cloud_path: string | null;
  verified: boolean;
  verified_at: string | null;
  restore_tested: boolean;
  restore_tested_at: string | null;
  download_count: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_by_id: number | null;
}

export type PaymentTerms = 'immediate' | 'net_7' | 'net_15' | 'net_30';

export interface SupplierOut {
  id: number;
  supplier_code: string;
  company_name: string;
  contact_person: string | null;
  phone: string | null;
  alt_phone: string | null;
  email: string | null;
  gstin: string | null;
  pan: string | null;
  billing_address: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  country: string;
  payment_terms: PaymentTerms;
  opening_balance: string;
  notes: string | null;
  is_active: boolean;
  product_count: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierProductOut {
  id: number;
  supplier_id: number;
  product_id: number;
  product_name: string;
  product_sku: string | null;
  supplier_product_code: string | null;
  purchase_price: string | null;
  last_purchase_price: string | null;
  min_order_qty: string;
  lead_time_days: number | null;
  is_preferred: boolean;
  notes: string | null;
  is_active: boolean;
}

/** Money with one supplier. What is owed comes from invoices' payable amounts (= goods received). */
export interface SupplierSummary {
  supplier_id: number;
  total_po_value: number;
  /** Goods accepted on all GRNs, at PO rates. */
  total_received_value: number;
  /** Received but no supplier invoice entered yet. */
  not_invoiced_value: number;
  /** Invoice totals as the supplier billed them. */
  total_invoiced: number;
  /** What is owed on those invoices: never more than the goods received. */
  total_payable: number;
  total_paid: number;
  /** Opening balance + payable − paid. */
  outstanding_balance: number;
  advance_balance: number;
  overdue_amount: number;
  invoice_count: number;
  /** Invoices whose amount differs from the goods received. */
  disputed_count: number;
  payment_count: number;
}

export interface SupplierLedgerEntry {
  date: string;
  entry_type: string; // invoice / payment / advance …
  reference: string;
  description: string;
  debit: number;
  credit: number;
  balance: number;
}

/** A goods receipt on the supplier page: its value and the invoice that bills it (null = not invoiced). */
export interface SupplierGRNOut {
  id: number;
  receipt_number: string;
  purchase_order_id: number;
  po_number: string;
  received_at: string;
  value: string;
  item_count: number;
  invoice_id: number | null;
  invoice_number: string | null;
}

export interface SupplierDashboard {
  total: number;
  active: number;
  inactive: number;
  products_linked: number;
}

export type PurchaseStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'ordered'
  | 'partially_received'
  | 'received'
  | 'closed'
  | 'cancelled';

export interface PurchaseOrderItemOut {
  id: number;
  product_id: number;
  product_name: string;
  product_sku: string | null;
  ordered_qty: string;
  received_qty: string;
  unit_price: string;
  discount_percent: string;
  tax_rate: string;
  line_discount: string;
  tax_amount: string;
  line_total: string;
}

export interface PurchaseOrderOut {
  id: number;
  po_number: string;
  supplier_id: number;
  supplier_name: string;
  store_id: number | null;
  purchase_date: string;
  expected_delivery_date: string | null;
  reference_number: string | null;
  notes: string | null;
  internal_remarks: string | null;
  shipping_address: string | null;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  shipping_charges: string;
  other_charges: string;
  grand_total: string;
  status: PurchaseStatus;
  ordered_at: string | null;
  approved_at: string | null;
  approved_by_id: number | null;
  cancelled_at: string | null;
  closed_at: string | null;
  created_by_id: number | null;
  created_by_name: string;
  items: PurchaseOrderItemOut[];
  created_at: string;
  updated_at: string;
  payment_status: POPaymentStatus;
  /** Goods accepted on the GRNs, at PO rates. */
  received_value: string;
  /** Received but no supplier invoice yet. */
  not_invoiced_value: string;
  invoiced_amount: string;
  /** What is owed on the invoices (never more than the goods received). */
  payable_amount: string;
  amount_paid: string;
  /** payable − paid */
  outstanding_amount: string;
}

export type POPaymentStatus = 'not_invoiced' | 'unpaid' | 'partially_paid' | 'paid' | 'overdue';

export interface PurchaseDashboard {
  total: number;
  total_value: string;
  pending: number;
  ordered: number;
  partially_received: number;
  received: number;
  cancelled: number;
  total_paid: string;
  total_due: string;
}

export interface POPaymentSummary {
  po_id: number;
  grand_total: string;
  received_value: string;
  not_invoiced_value: string;
  invoiced_amount: string;
  payable_amount: string;
  total_paid: string;
  outstanding: string;
  invoice_count: number;
  payment_status: POPaymentStatus;
  invoice_id: number | null;
  invoice_ids: number[];
}

export interface POPaymentEntry {
  payment_id: number;
  payment_date: string;
  amount: string;
  allocated_amount: string;
  payment_method: string;
  reference_number: string | null;
  notes: string | null;
  is_voided: boolean;
  created_by_name: string;
  running_total_paid: string;
  balance_after: string;
  invoice_number: string;
}

export interface POPaymentHistoryOut {
  po_id: number;
  po_number: string;
  supplier_name: string;
  grand_total: string;
  payable_amount: string;
  total_paid: string;
  outstanding: string;
  payment_status: string;
  invoice_number: string | null;
  invoice_id: number | null;
  entries: POPaymentEntry[];
}

export interface GoodsReceiptItemOut {
  id: number;
  purchase_order_item_id: number;
  product_id: number;
  product_name: string;
  qty_received: string;
  qty_accepted: string | null;
  qty_rejected: string;
  qty_damaged: string;
  expiry_date: string | null;
  batch_number: string | null;
  mfg_date: string | null;
  remarks: string | null;
}

export interface GoodsReceiptOut {
  id: number;
  purchase_order_id: number;
  receipt_number: string;
  received_at: string;
  received_by_id: number | null;
  received_by_name: string;
  notes: string | null;
  receipt_items: GoodsReceiptItemOut[];
  created_at: string;
}

export interface AuditLogOut {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  old_values: unknown;
  new_values: unknown;
  ip_address: string | null;
  created_at: string;
}

// ── Supplier Invoice (AP) ──────────────────────────────────────────────────────

export type SupplierInvoiceStatus = 'unpaid' | 'partially_paid' | 'paid' | 'cancelled';
export type InvoiceVerificationStatus = 'pending' | 'verified' | 'disputed';

export interface SupplierInvoiceOut {
  id: number;
  supplier_id: number;
  supplier_name: string;
  purchase_order_id: number | null;
  po_number: string | null;
  store_id: number | null;
  invoice_number: string;
  invoice_date: string;
  due_date: string | null;
  subtotal: string;
  tax_amount: string;
  other_charges: string;
  grand_total: string;
  /** Goods accepted on the GRNs (null = old invoice without GRNs). */
  received_value: string | null;
  /** Invoice goods amount − received value. */
  difference: string | null;
  difference_reason: string | null;
  /** What is owed: never more than the goods received (+ other charges). */
  payable_amount: string;
  amount_paid: string;
  /** payable − paid */
  outstanding: string;
  payment_status: SupplierInvoiceStatus;
  verification_status: InvoiceVerificationStatus;
  grn_ids: number[];
  grn_numbers: string[];
  /** Made before invoices were tied to GRNs (e.g. the old PO quick payment). */
  is_legacy: boolean;
  /** The uploaded bill. */
  document_id: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// ── Supplier Payment ──────────────────────────────────────────────────────────

export type SupplierPaymentType = 'payment' | 'advance' | 'credit_note' | 'debit_note';
export type SupplierPaymentMethod = 'cash' | 'bank_transfer' | 'upi' | 'cheque' | 'other';

export interface PaymentAllocationOut {
  id: number;
  invoice_id: number;
  invoice_number: string;
  allocated_amount: string;
}

export interface SupplierPaymentOut {
  id: number;
  supplier_id: number;
  supplier_name: string;
  store_id: number | null;
  payment_date: string;
  amount: string;
  payment_type: SupplierPaymentType;
  payment_method: SupplierPaymentMethod;
  reference_number: string | null;
  bank_account: string | null;
  notes: string | null;
  is_voided: boolean;
  voided_at: string | null;
  allocations: PaymentAllocationOut[];
  /** Advance not yet applied to an invoice. */
  unallocated_amount: string;
  created_at: string;
}

// ── Supplier Document ─────────────────────────────────────────────────────────

export type DocumentEntityType =
  | 'supplier'
  | 'purchase_order'
  | 'goods_receipt'
  | 'supplier_invoice'
  | 'supplier_payment';

export interface SupplierDocumentOut {
  id: number;
  entity_type: DocumentEntityType;
  entity_id: number;
  document_label: string | null;
  original_filename: string;
  file_size: number;
  mime_type: string;
  uploaded_by_id: number | null;
  created_at: string;
}
