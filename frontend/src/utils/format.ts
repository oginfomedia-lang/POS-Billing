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
