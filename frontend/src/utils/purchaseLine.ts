/**
 * Money on one purchase line, worked out exactly like the server (backend purchase_service._calc_line):
 *
 *   gross    = qty × rate                     rounded to the paisa
 *   discount = gross × discount% / 100        rounded to the paisa
 *   taxable  = gross − discount
 *   gst      = taxable × GST% / 100           rounded to the paisa
 *   total    = taxable + gst
 *
 * The server rounds with Python's Decimal.quantize (half to even), so this does too, in whole paise (BigInt).
 * With JavaScript floats and Math.round (half up) a line could come out 1 paisa different from the server's.
 */
export interface LineAmounts {
  gross: number;
  discount: number;
  taxable: number;
  gst: number;
  total: number;
}

/** "12.5" with 2 decimals → 1250n. Empty, invalid or negative → 0n. */
function scaled(value: string | number, decimals: number): bigint {
  const n = typeof value === 'number' ? value : parseFloat(value);
  return Number.isFinite(n) && n > 0 ? BigInt(Math.round(n * 10 ** decimals)) : 0n;
}

/** n ÷ d to a whole number, a half going to the even neighbour (n ≥ 0, d > 0). */
function divHalfEven(n: bigint, d: bigint): bigint {
  const q = n / d;
  const twice = (n % d) * 2n;
  return twice > d || (twice === d && q % 2n === 1n) ? q + 1n : q;
}

export function lineAmounts(
  qty: string | number, rate: string | number, discountPercent: string | number, gstPercent: string | number,
): LineAmounts {
  const gross = divHalfEven(scaled(qty, 3) * scaled(rate, 2), 1000n); // paise
  const discount = divHalfEven(gross * scaled(discountPercent, 2), 10000n);
  const taxable = gross - discount;
  const gst = divHalfEven(taxable * scaled(gstPercent, 2), 10000n);
  const rupees = (paise: bigint) => Number(paise) / 100;
  return {
    gross: rupees(gross), discount: rupees(discount), taxable: rupees(taxable), gst: rupees(gst),
    total: rupees(taxable + gst),
  };
}
