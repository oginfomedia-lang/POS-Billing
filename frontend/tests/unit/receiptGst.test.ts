// Run: npm test   (Node's built-in test runner; no extra packages)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { addGstPaise, receiptWithGst } from '../../src/components/pos/receiptGst.ts';
import type { ReceiptOut } from '../../src/types/sale.ts';

const item = (o: Record<string, string>) => ({
  offer_discount: '0', manual_discount: '0', reward_discount: '0', discount_amount: '0', ...o,
});

test('GST added and rounded half up to the paisa', () => {
  assert.equal(addGstPaise(15000, '5.00'), 15750);
  assert.equal(addGstPaise(2458, '18.00'), 2900); // 29.0044
  assert.equal(addGstPaise(7374, 18), 8701); // 87.0132
  assert.equal(addGstPaise(50, '1.00'), 51); // 50.5 -> 51
  assert.equal(addGstPaise(1000, '0'), 1000);
  assert.equal(addGstPaise(0, '18'), 0);
});

test('lines, savings and total add up with GST', () => {
  // Oil 2 × 150 (5 %) with a ₹10 offer; soap 3 × 24.58 (18 %) with a ₹2 manual discount.
  // Taxable 290 + 71.74; GST 14.50 + 12.91; total 389.15.
  const receipt = {
    total: '389.15',
    items: [
      item({ unit_price: '150.00', line_total: '300.00', tax_rate: '5.00', offer_discount: '10.00', discount_amount: '10.00' }),
      item({ unit_price: '24.58', line_total: '73.74', tax_rate: '18.00', manual_discount: '2.00', discount_amount: '2.00' }),
    ],
  } as unknown as ReceiptOut;
  const g = receiptWithGst(receipt);
  assert.deepEqual(g.lines.map((l) => [l.rate, l.amount, l.offer, l.manual]), [
    [15750, 31500, 1050, 0],
    [2900, 8701, 0, 236],
  ]);
  assert.equal(g.subtotal, 40201);
  assert.equal(g.subtotal - g.itemSavings - g.billOffer - g.reward, 38915); // = the total, to the paisa
});
