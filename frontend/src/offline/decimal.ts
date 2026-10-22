// Exact decimal numbers for offline billing maths (never floats for money), behaving like the backend's Python
// Decimal: quantize() rounds half-up for money (app/utils/money.py) or half-even (Python's default, used for the
// weight worked out from a price sticker). Values are a BigInt scaled by 10^scale.

const DIV_PLACES = 30; // digits kept by div(); the backend keeps 28 significant digits before rounding

export class Dec {
  readonly units: bigint;
  readonly scale: number;

  // Plain fields, not constructor parameter properties: the unit tests run this file with Node's type stripping.
  private constructor(units: bigint, scale: number) {
    this.units = units;
    this.scale = scale;
  }

  static of(value: string | number | Dec): Dec {
    if (value instanceof Dec) return value;
    const text = typeof value === 'number' ? numberText(value) : value.trim();
    const m = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(text);
    if (!m || (m[2] === '' && (m[3] ?? '') === '')) throw new Error(`Not a number: ${value}`);
    const frac = m[3] ?? '';
    const units = BigInt(`${m[2] || '0'}${frac}`) * (m[1] === '-' ? -1n : 1n);
    return new Dec(units, frac.length);
  }

  static readonly ZERO = new Dec(0n, 0);

  private aligned(other: Dec): [bigint, bigint, number] {
    const scale = Math.max(this.scale, other.scale);
    return [this.units * 10n ** BigInt(scale - this.scale), other.units * 10n ** BigInt(scale - other.scale), scale];
  }

  add(other: Dec | string | number): Dec {
    const [a, b, scale] = this.aligned(Dec.of(other));
    return new Dec(a + b, scale);
  }

  sub(other: Dec | string | number): Dec {
    const [a, b, scale] = this.aligned(Dec.of(other));
    return new Dec(a - b, scale);
  }

  mul(other: Dec | string | number): Dec {
    const o = Dec.of(other);
    return new Dec(this.units * o.units, this.scale + o.scale);
  }

  /** Division kept to DIV_PLACES digits (truncated); round the result with quantize(). */
  div(other: Dec | string | number): Dec {
    const o = Dec.of(other);
    if (o.units === 0n) throw new Error('Division by zero');
    // (a / 10^sa) / (b / 10^sb) = a * 10^(sb + P - sa) / b, scaled by 10^P
    const shift = o.scale + DIV_PLACES - this.scale;
    const num = shift >= 0 ? this.units * 10n ** BigInt(shift) : this.units / 10n ** BigInt(-shift);
    return new Dec(num / o.units, DIV_PLACES);
  }

  /** Whole part, rounded toward minus infinity (Python's // for the positive numbers used here). */
  floor(): bigint {
    const d = 10n ** BigInt(this.scale);
    const q = this.units / d;
    return this.units < 0n && q * d !== this.units ? q - 1n : q;
  }

  quantize(places: number, mode: 'half-up' | 'half-even' = 'half-up'): Dec {
    if (places >= this.scale) return new Dec(this.units * 10n ** BigInt(places - this.scale), places);
    const d = 10n ** BigInt(this.scale - places);
    const neg = this.units < 0n;
    const abs = neg ? -this.units : this.units;
    let q = abs / d;
    const rem = abs - q * d;
    const twice = rem * 2n;
    if (twice > d || (twice === d && (mode === 'half-up' || q % 2n === 1n))) q += 1n;
    return new Dec(neg ? -q : q, places);
  }

  cmp(other: Dec | string | number): number {
    const [a, b] = this.aligned(Dec.of(other));
    return a < b ? -1 : a > b ? 1 : 0;
  }

  eq(other: Dec | string | number): boolean { return this.cmp(other) === 0; }
  lt(other: Dec | string | number): boolean { return this.cmp(other) < 0; }
  gt(other: Dec | string | number): boolean { return this.cmp(other) > 0; }
  isZero(): boolean { return this.units === 0n; }

  static min(a: Dec, b: Dec): Dec { return a.cmp(b) <= 0 ? a : b; }
  static max(a: Dec, b: Dec): Dec { return a.cmp(b) >= 0 ? a : b; }
  static sum(values: Dec[]): Dec { return values.reduce((acc, v) => acc.add(v), Dec.ZERO); }

  /** Plain decimal text with the stored number of places, e.g. "157.50", "-0.05", "3". */
  toString(): string {
    const neg = this.units < 0n;
    const digits = (neg ? -this.units : this.units).toString().padStart(this.scale + 1, '0');
    const text = this.scale ? `${digits.slice(0, -this.scale)}.${digits.slice(-this.scale)}` : digits;
    return neg ? `-${text}` : text;
  }

  toNumber(): number { return Number(this.toString()); }
}

function numberText(n: number): string {
  if (!Number.isFinite(n)) throw new Error(`Not a number: ${n}`);
  // Up to 6 places covers money (2) and weights (3) without float noise such as 0.30000000000000004.
  return Number.isInteger(n) ? String(n) : n.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
}

/** round_money(): two places, half-up. */
export function money(value: Dec | string | number): Dec {
  return Dec.of(value).quantize(2);
}
