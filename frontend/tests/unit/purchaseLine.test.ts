// Run: npm test
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { lineAmounts } from '../../src/utils/purchaseLine.ts';

test('taxable = qty × rate − discount, total = taxable + GST', () => {
  assert.deepEqual(lineAmounts('10', '100', '2', '5'), { gross: 1000, discount: 20, taxable: 980, gst: 49, total: 1029 });
  assert.deepEqual(lineAmounts('10', '24.50', '', '0'), { gross: 245, discount: 0, taxable: 245, gst: 0, total: 245 });
});

test('each step is rounded to the paisa, a half going to even (like the server)', () => {
  // 0.125 kg × 0.20 = 0.025 → 0.02 (2 is even), and 0.375 kg × 0.20 = 0.075 → 0.08 (8 is even)
  assert.equal(lineAmounts('0.125', '0.20', '0', '0').gross, 0.02);
  assert.equal(lineAmounts('0.375', '0.20', '0', '0').gross, 0.08);
  // GST 18 % of 10.25 = 1.845 → 1.84 (4 is even), not 1.85
  assert.equal(lineAmounts('1', '10.25', '0', '18').gst, 1.84);
  // 2.5 % of 100.10 = 2.5025 → 2.50
  assert.equal(lineAmounts('1', '100.10', '2.5', '0').discount, 2.5);
  // a weighed quantity: 1.255 kg × 80.00 = 100.40
  assert.equal(lineAmounts('1.255', '80', '0', '5').total, 105.42);
});

test('empty or invalid fields count as 0', () => {
  assert.deepEqual(lineAmounts('', 'abc', '', ''), { gross: 0, discount: 0, taxable: 0, gst: 0, total: 0 });
});
