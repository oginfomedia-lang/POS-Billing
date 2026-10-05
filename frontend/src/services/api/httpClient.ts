// Axios instance: base URL, JWT header, error handling.
import axios from 'axios';
import type { ApiErrorBody } from '../../types/api';

export const httpClient = axios.create({ timeout: 10_000 });

/** Called once at startup with the apiUrl from counter.json. */
export function setApiBaseUrl(url: string): void {
  httpClient.defaults.baseURL = url.replace(/\/+$/, '');
}

/** Turns any request failure into a message a cashier can read. */
export function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError<ApiErrorBody>(err)) {
    if (!err.response) return 'Cannot reach the server. Check the network cable.';
    return err.response.data?.error?.message ?? `Server error (${err.response.status}).`;
  }
  return err instanceof Error ? err.message : 'Unexpected error.';
}
