// Shop licence API calls. The licence lives on the Main PC's server, so every counter shares it.
import axios from 'axios';
import type { ApiErrorBody } from '../../types/api';
import { httpClient } from './httpClient';

export interface LicenseStatus {
  valid: boolean;
  /** The Main PC's machine ID: the key must be issued for this. */
  machine_id: string;
  reason: 'not_activated' | 'invalid_key' | 'wrong_machine' | 'expired' | null;
  expires_at: string | null;
  days_left: number | null;
  customer_name: string | null;
  /** False on a development server: no licence screen. Only sent by GET /license. */
  required?: boolean;
  /** starter | business | enterprise (keys from before plans: enterprise). */
  plan?: string | null;
  /** Features the plan switches on (ALL_FEATURES in the server's license_service.py). */
  features?: string[];
  /** Plan caps; a missing one is unlimited. */
  limits?: Partial<Record<'counters' | 'stores' | 'users', number>>;
  /** Updates and support until this date. */
  amc_until?: string | null;
  key_version?: number | null;
}

export async function getLicense(): Promise<LicenseStatus> {
  try {
    const resp = await httpClient.get<LicenseStatus>('/license');
    return resp.data;
  } catch (err) {
    // The server answered but has no /license: a server from before shop licensing (e.g. the web portal's
    // backend not updated yet). It doesn't check licences, so neither does the screen. Real enforcement is
    // the shop server's own check on every API call.
    if (axios.isAxiosError(err) && err.response?.status === 404) {
      return { valid: false, required: false, machine_id: '', reason: null, expires_at: null, days_left: null, customer_name: null };
    }
    throw err;
  }
}

/** Activates the shop. Resolves with the new status; a rejected key resolves with valid=false and its reason. */
export async function activateLicense(key: string): Promise<LicenseStatus> {
  try {
    const resp = await httpClient.post<LicenseStatus>('/license/activate', { key });
    return resp.data;
  } catch (err) {
    const details = axios.isAxiosError<ApiErrorBody>(err) ? err.response?.data?.error?.details : undefined;
    if (details && typeof details === 'object' && 'valid' in details) return details as LicenseStatus;
    throw err;
  }
}
