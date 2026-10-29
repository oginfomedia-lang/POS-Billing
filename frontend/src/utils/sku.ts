// What the SKU box on the product form shows. New products get an automatic SKU (KIR-SAK-0001) made by the
// server when they are saved; until then the box shows a preview, or nothing (with a hint) while the
// category or name is missing. An admin may type an own SKU instead.

export type SkuField =
  | { kind: 'own' }                      // admin typing an own SKU: an editable box
  | { kind: 'saved'; sku: string }       // existing product: its SKU, unchanged by edits
  | { kind: 'preview'; sku: string }     // new product: what it will look like (number confirmed on save)
  | { kind: 'waiting' };                 // new product without a category or name yet

export function skuField(opts: {
  mode: 'create' | 'edit';
  ownSku: boolean;
  savedSku: string;
  categoryId: string;
  name: string;
  preview: string;
}): SkuField {
  if (opts.ownSku) return { kind: 'own' };
  if (opts.mode === 'edit') return { kind: 'saved', sku: opts.savedSku };
  if (!opts.categoryId || !opts.name.trim() || !opts.preview) return { kind: 'waiting' };
  return { kind: 'preview', sku: opts.preview };
}
