// Offline billing must price bills exactly like the server. The expected results in fixtures/pricing-cases.json are
// written by the server's own code (backend tests/integration/test_offline_pricing_cases.py).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Dec, money } from '../../src/offline/decimal.ts';
import { activeOffers, lineSaving, priceBill, type LineInput, type OfflineOffer, type PricedBill } from '../../src/offline/pricing.ts';

interface Case {
  name: string;
  lines: LineInput[];
  offers: OfflineOffer[];
  categories: Record<string, number | null>;
  expected: PricedBill;
}

const cases = JSON.parse(readFileSync(new URL('../fixtures/pricing-cases.json', import.meta.url), 'utf-8')) as Case[];

for (const c of cases) {
  test(`same price as the server: ${c.name}`, () => {
    assert.deepEqual(priceBill(c.lines, c.offers, c.categories), c.expected);
  });
}

test('money rounds half-up like the server', () => {
  assert.equal(money('2.345').toString(), '2.35');
  assert.equal(money('2.344').toString(), '2.34');
  assert.equal(money('-2.345').toString(), '-2.35');
  assert.equal(Dec.of('1.0050').quantize(2).toString(), '1.01');
  assert.equal(Dec.of('0.0005').quantize(3, 'half-even').toString(), '0.000');
  assert.equal(Dec.of('0.0015').quantize(3, 'half-even').toString(), '0.002');
  assert.equal(Dec.of(10).div(3).quantize(2).toString(), '3.33');
  assert.equal(Dec.of(0.1).add(0.2).toString(), '0.3');
});

test('only offers running now apply', () => {
  const base: OfflineOffer = {
    id: 1, name: 'x', discount_type: 'fixed', value: '1', scope: 'bill', product_id: null, category_id: null,
    min_bill_amount: null, max_discount_amount: null, buy_qty: null, get_qty: null, starts_at: null, ends_at: null,
  };
  const now = new Date('2026-10-21T10:00:00Z');
  const offers = [
    { ...base, id: 3 },
    { ...base, id: 1, starts_at: '2026-10-22T00:00:00Z' },
    { ...base, id: 2, ends_at: '2026-10-21T10:00:00Z' },
    { ...base, id: 4, starts_at: '2026-10-01T00:00:00Z', ends_at: '2026-10-31T00:00:00Z' },
  ];
  assert.deepEqual(activeOffers(offers, now).map((o) => o.id), [3, 4]);
});

test('saving against MRP', () => {
  assert.equal(lineSaving('50.00', '2', '80.00', '0.00', '4.00'), '16.00');
  assert.equal(lineSaving(null, '2', '80.00', '5.00', '3.75'), '5.00');
  assert.equal(lineSaving('40.00', '1', '40.00', '0.00', '2.00'), '0.00');
});
