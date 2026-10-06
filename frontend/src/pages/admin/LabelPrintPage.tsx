// Print barcode/price stickers for a product, in any quantity.
// Open with /admin/labels?product=<id>&barcode=<code>&qty=<n> (all optional).
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { BarcodeLabel } from '../../components/admin/BarcodeLabel';
import { getErrorMessage } from '../../services/api/httpClient';
import { getProduct, listProducts } from '../../services/api/productApi';
import type { ProductOut } from '../../types/product';
import { encodeBarcode } from '../../utils/barcode';
import { paiseToString, toPaise } from '../../utils/money';

const MAX_COPIES = 1000;
const PREVIEW_LIMIT = 24;

const SIZES = {
  'roll-50x25': { label: '50 × 25 mm label roll (thermal printer)', page: '50mm 25mm', perPage: 1 },
  'roll-38x25': { label: '38 × 25 mm label roll (thermal printer)', page: '38mm 25mm', perPage: 1 },
  'a4-24': { label: 'A4 sheet, 24 labels (3 × 8, 70 × 37 mm)', page: 'A4', perPage: 24 },
} as const;
type SizeKey = keyof typeof SIZES;

const SIZE_STORAGE_KEY = 'pos-label-size';

function savedSize(): SizeKey {
  try {
    const v = localStorage.getItem(SIZE_STORAGE_KEY);
    if (v && v in SIZES) return v as SizeKey;
  } catch { /* storage unavailable */ }
  return 'roll-50x25';
}

/** Selling price is tax-exclusive; the sticker shows what the customer pays. */
function priceWithTax(p: ProductOut): string {
  return paiseToString(Math.round((toPaise(p.price) * (100 + Number(p.tax_rate))) / 100));
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

export function LabelPrintPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const navigationState = location.state;
  const backTo = navigationState && typeof navigationState === 'object' && 'from' in navigationState
    && (navigationState.from === '/admin/products' || navigationState.from === '/admin/inventory')
    ? navigationState.from
    : '/admin/products';
  const backLabel = backTo === '/admin/inventory' ? 'Back to Inventory' : 'Back to Products';

  const [product, setProduct] = useState<ProductOut | null>(null);
  const [barcode, setBarcode] = useState(params.get('barcode') ?? '');
  const [copies, setCopies] = useState(params.get('qty') ?? '1');
  const [size, setSize] = useState<SizeKey>(savedSize);
  const [showPrice, setShowPrice] = useState(true);

  const [search, setSearch] = useState('');
  const [results, setResults] = useState<ProductOut[]>([]);
  const [error, setError] = useState('');

  // Preselected product from the URL (from Products / Inventory pages).
  useEffect(() => {
    const id = Number(params.get('product'));
    if (!id) return;
    getProduct(id).then(choose).catch((err) => setError(getErrorMessage(err)));
  }, []);

  // Search as you type (debounced).
  useEffect(() => {
    const q = search.trim();
    if (!q) { setResults([]); return; }
    const t = window.setTimeout(() => {
      listProducts({ q, per_page: 10, active_only: true })
        .then((r) => setResults(r.items))
        .catch((err) => setError(getErrorMessage(err)));
    }, 250);
    return () => window.clearTimeout(t);
  }, [search]);

  function choose(p: ProductOut) {
    setProduct(p);
    setSearch('');
    setResults([]);
    setError('');
    setBarcode((cur) => {
      if (p.barcodes.some((b) => b.barcode === cur)) return cur;
      // Prefer the store's own sticker code, then the primary barcode.
      const pick = p.barcodes.find((b) => b.barcode_type === 'IN_HOUSE') ?? p.barcodes.find((b) => b.is_primary) ?? p.barcodes[0];
      return pick?.barcode ?? '';
    });
  }

  function changeSize(s: SizeKey) {
    setSize(s);
    try { localStorage.setItem(SIZE_STORAGE_KEY, s); } catch { /* storage unavailable */ }
  }

  const pattern = useMemo(() => (barcode ? encodeBarcode(barcode) : null), [barcode]);
  const count = Number(copies);
  const countValid = Number.isInteger(count) && count >= 1 && count <= MAX_COPIES;
  const ready = product !== null && pattern !== null && countValid;
  const price = product && showPrice ? priceWithTax(product) : null;
  const labels = ready ? Array.from({ length: count }, (_, i) => i) : [];
  const spec = SIZES[size];

  return (
    <div className="admin-page labels-page">
      {/* @page must match the label stock so each sticker lands on one label. */}
      <style>{`@page { size: ${spec.page}; margin: 0; }`}</style>

      <div className="no-print">
        <AdminNav />
        <div className="admin-header">
          <h2>Print Barcode Labels</h2>
          <div className="admin-actions">
            <button className="btn-secondary page-back-button" onClick={() => navigate(backTo)}>
              <span aria-hidden="true">←</span>
              {backLabel}
            </button>
            <button className="btn-primary" disabled={!ready} onClick={() => window.print()}>
              Print {ready ? `${count} label${count === 1 ? '' : 's'}` : ''}
            </button>
          </div>
        </div>

        {error && <div className="page-error">{error}</div>}

        <div className="labels-form">
          <label className="field-label">
            Product
            <div className="product-picker">
              <input
                className="field-input"
                placeholder={product ? product.name : 'Search name, SKU or scan barcode'}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoFocus={!params.get('product')}
              />
              {results.length > 0 && (
                <ul className="picker-results">
                  {results.map((p) => (
                    <li key={p.id}>
                      <button type="button" onClick={() => choose(p)}>
                        {p.name} <span className="status-muted">{p.sku}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </label>

          <label className="field-label">
            Barcode
            <select className="field-input" value={barcode} onChange={(e) => setBarcode(e.target.value)} disabled={!product}>
              {!product?.barcodes.length && <option value="">— no barcodes —</option>}
              {product?.barcodes.map((b) => (
                <option key={b.barcode} value={b.barcode}>
                  {b.barcode} ({b.barcode_type === 'IN_HOUSE' ? 'in-house' : b.barcode_type.toLowerCase()})
                </option>
              ))}
            </select>
          </label>

          <label className="field-label">
            Copies
            <input
              className="field-input"
              type="number"
              min={1}
              max={MAX_COPIES}
              value={copies}
              onChange={(e) => setCopies(e.target.value)}
              onFocus={(e) => e.target.select()}
            />
          </label>

          <label className="field-label">
            Label size
            <select className="field-input" value={size} onChange={(e) => changeSize(e.target.value as SizeKey)}>
              {Object.entries(SIZES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </label>

          <label className="field-label checkbox-label">
            <input type="checkbox" checked={showPrice} onChange={(e) => setShowPrice(e.target.checked)} />
            Show price
          </label>
        </div>

        {product && product.barcodes.length === 0 && (
          <div className="page-error">
            This product has no barcode. Open it on the Products page and click "Generate In-House Barcode" first.
          </div>
        )}
        {barcode && !pattern && (
          <div className="page-error">
            "{barcode}" isn't a valid EAN-13 or EAN-8 code, so it can't be printed. Use the product's in-house barcode.
          </div>
        )}
        {!countValid && <div className="page-error">Copies must be a whole number from 1 to {MAX_COPIES}.</div>}

        {ready && (
          <>
            <p className="hint-text">
              Preview{count > PREVIEW_LIMIT ? ` (first ${PREVIEW_LIMIT} of ${count}; all will print)` : ''}. In the print
              dialog choose your label printer, set paper size to match, and scale to 100% / "Actual size".
            </p>
            <div className={`label-preview size-${size}`}>
              {labels.slice(0, PREVIEW_LIMIT).map((i) => (
                <BarcodeLabel key={i} name={product.name} price={price} code={barcode} pattern={pattern} />
              ))}
            </div>
          </>
        )}
      </div>

      {ready && (
        <div className={`label-print size-${size}`}>
          {chunk(labels, spec.perPage).map((page, pi) => (
            <div key={pi} className="label-page">
              {page.map((i) => (
                <BarcodeLabel key={i} name={product.name} price={price} code={barcode} pattern={pattern} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
