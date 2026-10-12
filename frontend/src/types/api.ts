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
export type BackupStorageLocation = 'local' | 's3';

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
  notes: string | null;
  is_active: boolean;
  product_count: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierDashboard {
  total: number;
  active: number;
  inactive: number;
  products_linked: number;
}

export type PurchaseStatus = 'draft' | 'ordered' | 'partially_received' | 'received' | 'cancelled';

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
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  grand_total: string;
  status: PurchaseStatus;
  ordered_at: string | null;
  cancelled_at: string | null;
  created_by_id: number | null;
  created_by_name: string;
  items: PurchaseOrderItemOut[];
  created_at: string;
  updated_at: string;
}

export interface PurchaseDashboard {
  total: number;
  total_value: string;
  pending: number;
  ordered: number;
  partially_received: number;
  received: number;
  cancelled: number;
}

export interface GoodsReceiptItemOut {
  id: number;
  purchase_order_item_id: number;
  product_id: number;
  product_name: string;
  qty_received: string;
  expiry_date: string | null;
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
