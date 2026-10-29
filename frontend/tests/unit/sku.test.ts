// What the SKU box on the product form shows (src/utils/sku.ts).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { skuField } from '../../src/utils/sku.ts';

const base = { mode: 'create' as const, ownSku: false, savedSku: '', categoryId: '3', name: 'साखर', preview: 'KIR-SAK-0007' };

test('new product with category and name: the preview', () => {
  assert.deepEqual(skuField(base), { kind: 'preview', sku: 'KIR-SAK-0007' });
});

test('new product without a category or a name, or before the preview arrives: waiting (placeholder)', () => {
  assert.deepEqual(skuField({ ...base, categoryId: '' }), { kind: 'waiting' });
  assert.deepEqual(skuField({ ...base, name: '   ' }), { kind: 'waiting' });
  assert.deepEqual(skuField({ ...base, preview: '' }), { kind: 'waiting' });
});

test('existing product: its saved SKU, whatever the name or category become', () => {
  assert.deepEqual(
    skuField({ ...base, mode: 'edit', savedSku: 'GRO-SUG-0002', name: 'नवीन नाव', categoryId: '9' }),
    { kind: 'saved', sku: 'GRO-SUG-0002' },
  );
});

test('admin typing an own SKU: an editable box, in both modes', () => {
  assert.deepEqual(skuField({ ...base, ownSku: true }), { kind: 'own' });
  assert.deepEqual(skuField({ ...base, mode: 'edit', ownSku: true }), { kind: 'own' });
});
