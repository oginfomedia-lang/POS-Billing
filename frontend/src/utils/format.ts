// Date and text formatting helpers.

const DATE_TIME = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Kolkata',
});

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}
