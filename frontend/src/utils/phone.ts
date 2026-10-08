// Indian mobile numbers, same rules as backend/app/utils/phone.py (the server has the final say).

/** '+91 98765-43210' -> '9876543210'; '' -> ''; not a valid mobile -> null. */
export function normalizeMobile(raw: string): string | null {
  let digits = raw.replace(/[\s\-()]/g, '');
  if (!digits) return '';
  if (digits.startsWith('+91')) digits = digits.slice(3);
  else if (digits.length === 12 && digits.startsWith('91')) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
  return /^[6-9]\d{9}$/.test(digits) ? digits : null;
}

export function isMobile(raw: string): boolean {
  const n = normalizeMobile(raw);
  return n !== null && n !== '';
}
