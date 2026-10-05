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
  created_at: string;
}

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
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
