// Date and text formatting helpers.
import { intlLocale } from '../i18n';

/** Date + time in the current UI language (Marathi month names, 0–9 digits). */
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(intlLocale(), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata',
  }).format(new Date(iso));
}

/** Date only, in the current UI language. */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeZone: 'Asia/Kolkata' }).format(new Date(iso));
}

const ISO_DATE_IST = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' });

/** YYYY-MM-DD for today (or `daysAgo` days back) in India, matching the backend's business date. */
export function isoDateIst(daysAgo = 0): string {
  return ISO_DATE_IST.format(new Date(Date.now() - daysAgo * 86_400_000));
}

/** First day of the current month in India, YYYY-MM-DD. */
export function monthStartIst(): string {
  return `${isoDateIst().slice(0, 8)}01`;
}

/** YYYY-MM-DDTHH:mm for right now in India timezone, suitable for datetime-local inputs. */
export function isoDateTimeLocalIst(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

/** Indian Rupee formatted amount (e.g. ₹1,23,456.78). */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(amount);
}

