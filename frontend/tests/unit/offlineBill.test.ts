// Offline billing without a server: scans (barcodes, SKUs, weighing-scale stickers), the priced bill and its receipt.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { changeDue, priceCart, toReceipt } from '../../src/offline/bill.ts';
import { scan, search } from '../../src/offline/lookup.ts';
import type { OfflineBill, OfflineCatalog, OfflineProduct } from '../../src/offline/types.ts';

function product(p: Partial<OfflineProduct> & { id: number; name: string }): OfflineProduct {
  return {
    sku: `SKU-${p.id}`, barcode: null, plu_code: null, category_id: null, price: '10.00', tax_rate: '5.00',
    mrp: null, hsn_code: null, uom: 'pcs', is_variable_weight: false, ...p,
  };
}

const catalog: OfflineCatalog = {
  generated_at: '2026-10-21T08:00:00Z',
  store: { id: 1, name: 'Shree Stores', address: 'Main Rd', phone: null, gstin: '27AAAAA0000A1Z5' },
  settings: {
    scale_prefix: '20', scale_plu_digits: 5, scale_value: 'weight', receipt_header: '', receipt_footer: 'Thank you!',
    receipt_footer_mr: '', fssai_number: '',
  },
  products: [
    product({ id: 1, name: 'Parle-G 100g', barcode: '8901719101038', price: '9.50', mrp: '10.00' }),
    product({ id: 2, name: 'Sugar (loose)', plu_code: '123', price: '42.00', tax_rate: '0.00', uom: 'kg', is_variable_weight: true }),
    product({ id: 3, name: 'Tata Salt 1kg', sku: 'SALT-1', price: '26.00' }),
  ],
  offers: [{
    id: 9, name: 'Biscuit ₹1 off', discount_type: 'fixed', value: '1.00', scope: 'product', product_id: 1,
    category_id: null, min_bill_amount: null, max_discount_amount: null, buy_qty: null, get_qty: null,
    starts_at: null, ends_at: null,
  }],
  categories: {},
};

test('scan finds barcodes and SKUs', () => {
  const byBarcode = scan(catalog, ' 8901719101038 ');
  assert.ok(byBarcode.ok && byBarcode.hit.product.id === 1 && byBarcode.hit.qty === '1');
  const bySku = scan(catalog, 'SALT-1');
  assert.ok(bySku.ok && bySku.hit.product.id === 3);
  assert.deepEqual(scan(catalog, '0000'), { ok: false, reason: 'not-found' });
});

test('scale sticker gives the weight in kg', () => {
  const sticker = scan(catalog, '2000123012505'); // PLU 123, 1250 g
  assert.ok(sticker.ok && sticker.hit.product.id === 2 && sticker.hit.qty === '1.250');
  assert.deepEqual(scan(catalog, '2099999012505'), { ok: false, reason: 'not-found', plu: '99999' });
  assert.deepEqual(scan(catalog, '2000123000005'), { ok: false, reason: 'zero-weight' });
});

test('price sticker is turned into a weight with GST, like the server', () => {
  const priced: OfflineCatalog = { ...catalog, settings: { ...catalog.settings, scale_value: 'price' } };
  const sticker = scan(priced, '2000123105005'); // value 10500 paise = ₹105.00 of sugar at ₹42/kg, 0% GST -> 2.5 kg
  assert.ok(sticker.ok && sticker.hit.qty === '2.500');
});

test('search by name', () => {
  assert.deepEqual(search(catalog, 'salt').map((p) => p.id), [3]);
  assert.deepEqual(search(catalog, ' '), []);
});

test('priced cart and its receipt', () => {
  const { bill, items } = priceCart(
    [{ product: catalog.products[0], qty: '3' }, { product: catalog.products[1], qty: '1.250' }],
    catalog, new Date('2026-10-21T10:00:00Z'),
  );
  // Biscuits 3 × 9.50 = 28.50, ₹3 off, GST 5% of 25.50 = 1.28. Sugar 1.25 × 42 = 52.50, no GST.
  assert.equal(bill.total, '79.28');
  assert.equal(items[0].offer_name, 'Biscuit ₹1 off');
  assert.equal(changeDue(bill.total, '100'), '20.72');

  const saved: OfflineBill = {
    offline_id: '5d7c1f0e-0000-4000-8000-000000000001', bill_number: 'C02-OFF-261021-0001', shift_id: 4,
    billed_at: '2026-10-21T10:00:00Z', items, ...bill, cash_tendered: '100.00', change_due: '20.72',
    cashier_id: 7, cashier_name: 'Neha', counter_code: 'C02', store: catalog.store, settings: catalog.settings,
  };
  const receipt = toReceipt(saved);
  assert.equal(receipt.bill_number, 'C02-OFF-261021-0001');
  assert.equal(receipt.total_qty, '4'); // 3 biscuits + 1.25 kg loose sugar (counts as 1)
  assert.equal(receipt.items[0].saving, '3.22'); // MRP 30.00 − paid 26.78
  assert.equal(receipt.total_saving, '3.22');
  assert.equal(receipt.payments[0].change_due, '20.72');
});
