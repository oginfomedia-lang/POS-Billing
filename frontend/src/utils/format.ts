// Date and text formatting helpers.

const DATE_TIME = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Kolkata',
});

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
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
