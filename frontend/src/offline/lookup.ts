// Finding products in the offline catalogue: what a scan or a typed name means, as the server's
// product_service.scan_barcode does online (weighing-scale stickers first, then barcode, then SKU).
import { Dec } from './decimal.ts';
import type { OfflineCatalog, OfflineProduct } from './types.ts';

export interface ScanHit {
  product: OfflineProduct;
  qty: string; // 1 for packets; kg from a scale sticker
}

export type ScanResult = { ok: true; hit: ScanHit } | { ok: false; reason: 'not-found' | 'zero-weight' | 'no-price'; plu?: string };

export function scan(catalog: OfflineCatalog, raw: string): ScanResult {
  const code = raw.trim();
  const sticker = scaleSticker(catalog, code);
  if (sticker) return sticker;
  const product = catalog.products.find((p) => p.barcode === code) ?? catalog.products.find((p) => p.sku === code);
  return product ? { ok: true, hit: { product, qty: '1' } } : { ok: false, reason: 'not-found' };
}

/** null = not a scale sticker (or no loose item has its code and it is a normal barcode): try it as a barcode. */
function scaleSticker(catalog: OfflineCatalog, code: string): ScanResult | null {
  const { scale_prefix: prefix, scale_plu_digits: digits, scale_value: valueMode } = catalog.settings;
  if (code.length !== 13 || !/^\d+$/.test(code) || !code.startsWith(prefix)) return null;
  const pluRaw = code.slice(2, 2 + digits);
  const valueRaw = code.slice(2 + digits, 12);
  if (!pluRaw || !valueRaw) return null;
  const plu = String(Number(pluRaw));
  let product = catalog.products.find((p) => p.plu_code === plu);
  if (!product) {
    // Older setup: the scale code was the product's SKU.
    const bySku = catalog.products.find((p) => p.sku === pluRaw);
    product = bySku?.is_variable_weight ? bySku : undefined;
  }
  if (!product) {
    const normal = catalog.products.some((p) => p.barcode === code || p.sku === code);
    return normal ? null : { ok: false, reason: 'not-found', plu };
  }
  const value = Dec.of(String(Number(valueRaw)));
  if (!value.gt(0)) return { ok: false, reason: 'zero-weight' };
  let kg: Dec;
  if (valueMode === 'price') {
    const withGst = Dec.of(product.price).mul(Dec.of(1).add(Dec.of(product.tax_rate).div(100)));
    if (!withGst.gt(0)) return { ok: false, reason: 'no-price' };
    kg = value.div(100).div(withGst).quantize(3, 'half-even');
    if (!kg.gt(0)) return { ok: false, reason: 'zero-weight' };
  } else {
    kg = value.div(1000).quantize(3, 'half-even');
  }
  return { ok: true, hit: { product, qty: kg.toString() } };
}

/** Name, SKU or barcode contains the text (case-insensitive), at most `limit` products. */
export function search(catalog: OfflineCatalog, text: string, limit = 20): OfflineProduct[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return [];
  return catalog.products
    .filter((p) => p.name.toLowerCase().includes(needle) || p.sku.toLowerCase().includes(needle) || (p.barcode ?? '').includes(needle))
    .slice(0, limit);
}
