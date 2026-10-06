// Rupee formatting helpers. Amounts arrive as decimal strings; do maths in paise (integers).

/** "157.5" -> 15750. Returns NaN for blank/invalid input. */
export function toPaise(value: string | number): number {
  const text = String(value).trim();
  if (text === '' || !/^\d*\.?\d*$/.test(text)) return NaN;
  return Math.round(Number(text) * 100);
}

export function paiseToString(paise: number): string {
  return (paise / 100).toFixed(2);
}

const RUPEES = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export function formatRupees(value: string | number): string {
  return RUPEES.format(Number(value));
}
