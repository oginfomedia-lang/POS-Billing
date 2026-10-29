// Axios instance: base URL, JWT header, error handling.
import axios from 'axios';
import i18n from '../../i18n';
import type { ApiErrorBody } from '../../types/api';

export const httpClient = axios.create({ timeout: 10_000 });

/** Called once at startup with the apiUrl from counter.json. */
export function setApiBaseUrl(url: string): void {
  httpClient.defaults.baseURL = url.replace(/\/+$/, '');
}

interface StockShortage {
  product_name: string;
  requested: number | string;
  available: number | string;
}

/**
 * Server messages are English. The ones a cashier or manager meets most are recognised here
 * (by error code or exact wording) and shown in the current UI language; anything else is
 * shown as the server sent it.
 */
function translateServerError(code: string | undefined, message: string, details: unknown): string {
  const t = i18n.t;
  if (code === 'INSUFFICIENT_STOCK' && Array.isArray(details)) {
    const items = (details as StockShortage[])
      .map((d) => t('errors.stockItem', { name: d.product_name, need: Number(d.requested), have: Number(d.available) }))
      .join(', ');
    return t('errors.insufficientStock', { items });
  }
  if (code === 'VALIDATION_ERROR' && message === 'Invalid request data.') {
    // Our own field checks explain what to fix ("Enter a valid 10-digit mobile number…"): show that.
    const first = Array.isArray(details) ? (details[0] as { message?: unknown } | undefined) : undefined;
    const own = typeof first?.message === 'string' && /^Value error, /.exec(first.message);
    return own ? (first!.message as string).slice(own[0].length) : t('errors.invalidRequest');
  }
  if (message === 'Invalid username or PIN.') return t('errors.badLogin');
  if (message === 'Approval failed: wrong manager username or PIN.') return t('errors.approvalFailed');
  if (message === 'Only a manager or admin can approve a discount.') return t('errors.approvalRole');
  if (message === "You don't have permission for this action.") return t('errors.permissionDenied');
  if (message === 'You can only access your own store.') return t('errors.ownStoreOnly');
  const notFound = /^No active product found for barcode '(.*)'\.$/.exec(message);
  if (notFound) return t('errors.productNotFound', { code: notFound[1] });
  return message;
}

/** Turns any request failure into a message a cashier can read, in the current UI language. */
export function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError<ApiErrorBody>(err)) {
    if (!err.response) return i18n.t('errors.network');
    const body = err.response.data?.error;
    if (!body?.message) return i18n.t('errors.server', { status: err.response.status });
    return translateServerError(body.code, body.message, body.details);
  }
  return err instanceof Error ? err.message : i18n.t('errors.unexpected');
}

/** getErrorMessage for downloads (responseType 'blob'): the server's JSON error arrives as a Blob. */
export async function getBlobErrorMessage(err: unknown): Promise<string> {
  if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
    try { err.response.data = JSON.parse(await err.response.data.text()); }
    catch { /* not JSON: the status code is shown */ }
  }
  return getErrorMessage(err);
}
