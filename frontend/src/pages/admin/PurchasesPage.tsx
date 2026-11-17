// Purchase Orders management page — admin and manager.
import { type CSSProperties, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import {
  IconCheck,
  IconClipboardList,
  IconEdit,
  IconHistory,
  IconPlus,
  IconTrash,
  IconX,
} from '../../components/common/Icons';
import { getBlobErrorMessage, getErrorMessage } from '../../services/api/httpClient';
import { openWhatsApp, purchaseApi } from '../../services/api/purchaseApi';
import type {
  GoodsReceiptItemPayload,
  PurchaseOrderCreatePayload,
  PurchaseOrderItemPayload,
  PurchaseOrderUpdatePayload,
} from '../../services/api/purchaseApi';
import { supplierApi } from '../../services/api/supplierApi';
import { listStores } from '../../services/api/storeApi';
import { createPendingProduct, listCategories, listProducts } from '../../services/api/productApi';
import { MarathiInput } from '../../components/common/MarathiInput';
import type { CategoryOut, UOMType } from '../../types/product';
import { getSettings } from '../../services/api/reportApi';
import { getPriceReview } from '../../services/api/priceReviewApi';
import type {
  GoodsReceiptOut,
  POPaymentHistoryOut,
  POPaymentSummary,
  POSentVia,
  PurchaseDashboard,
  PurchaseOrderItemOut,
  PurchaseOrderOut,
  PurchaseStatus,
  SupplierMessageOut,
  SupplierOut,
  StoreOut,
} from '../../types/api';
import { formatDate, formatDateTime, isoDateIst, isoDateTimeLocalIst } from '../../utils/format';

const PER_PAGE = 20;

const STATUS_OPTIONS: PurchaseStatus[] = [
  'draft', 'pending_approval', 'approved', 'ordered', 'partially_received', 'received', 'closed', 'cancelled',
];

// Colour tokens per status — uses CSS vars so dark-mode adapts
const STATUS_ACCENT: Record<PurchaseStatus, string> = {
  draft:              'var(--muted)',
  pending_approval:   '#7c3aed',
  approved:           '#0891b2',
  ordered:            '#0284c7',
  partially_received: '#d97706',
  received:           'var(--ok)',
  closed:             'var(--ok)',
  cancelled:          'var(--danger)',
};

const STATUS_BG: Record<PurchaseStatus, string> = {
  draft:              'var(--surface-3)',
  pending_approval:   '#ede9fe',
  approved:           '#cffafe',
  ordered:            'var(--info-bg)',
  partially_received: 'var(--warn-bg)',
  received:           'var(--ok-bg)',
  closed:             'var(--ok-bg)',
  cancelled:          'var(--danger-bg)',
};

const STATUS_FG: Record<PurchaseStatus, string> = {
  draft:              'var(--muted)',
  pending_approval:   '#5b21b6',
  approved:           '#164e63',
  ordered:            'var(--info-text)',
  partially_received: 'var(--warn-text)',
  received:           'var(--ok-text)',
  closed:             'var(--ok-text)',
  cancelled:          'var(--danger-text)',
};

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: PurchaseStatus }) {
  const { t } = useTranslation();
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '2px 10px',
        borderRadius: 999,
        fontSize: 11.5,
        fontWeight: 700,
        whiteSpace: 'nowrap',
        background: STATUS_BG[status],
        color: STATUS_FG[status],
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: STATUS_ACCENT[status],
          flexShrink: 0,
        }}
      />
      {t(`purchases.statuses.${status}` as const)}
    </span>
  );
}

// ── Stat tile (matches design system .stat-tile) ──────────────────────────────

function StatTile({
  label,
  value,
  sub,
  accent,
  onClick,
  isActive,
}: {
  label: string;
  value: string | number;
  accent: string;
  sub?: string;
  onClick?: () => void;
  isActive?: boolean;
}) {
  return (
    <div
      className="stat-tile"
      style={{
        '--accent': accent,
        cursor: onClick ? 'pointer' : undefined,
        outline: isActive ? `2px solid ${accent}` : undefined,
        outlineOffset: isActive ? 2 : undefined,
        userSelect: onClick ? 'none' : undefined,
      } as React.CSSProperties}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); } : undefined}
    >
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
      <div className="stat-label">{label}</div>
      {isActive && (
        <div style={{ fontSize: 10, fontWeight: 700, color: accent, marginTop: 2, letterSpacing: '0.05em' }}>
          ▲ ACTIVE FILTER
        </div>
      )}
    </div>
  );
}

// ── Payment status badge ──────────────────────────────────────────────────────

function PaymentStatusBadge({ status, cancelled }: { status?: string; cancelled?: boolean }) {
  if (cancelled) return null;
  const cfg: Record<string, { label: string; bg: string; color: string }> = {
    not_invoiced:  { label: 'No invoice yet', bg: 'var(--surface-2)', color: 'var(--muted)' },
    paid:          { label: 'Paid',    bg: 'var(--ok-bg)',      color: 'var(--ok-text)' },
    partially_paid:{ label: 'Partial', bg: 'var(--warn-bg)',    color: 'var(--warn-text)' },
    unpaid:        { label: 'Pending', bg: 'var(--danger-bg)',  color: 'var(--danger-text)' },
    overdue:       { label: 'Overdue', bg: '#fef2f2',           color: '#991b1b' },
  };
  const c = cfg[status ?? 'not_invoiced'] ?? cfg.unpaid;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 700,
        whiteSpace: 'nowrap',
        background: c.bg,
        color: c.color,
      }}
    >
      {status === 'overdue' && <span style={{ fontSize: 9 }}>⚠</span>}
      {c.label}
    </span>
  );
}

// ── Product search dropdown ───────────────────────────────────────────────────

interface ProductRow {
  id: number;
  name: string;
  sku: string | null;
  price: number | null; // purchase rate to start the line at; null = unknown, the user types it
  selling: number | null; // selling price (before GST), only to warn about a rate that isn't below it
  tax_rate: number;
  linked?: boolean; // already in this supplier's product list (bought from them before)
}

/** Matches shown in the picker; type more of the name / SKU / barcode to narrow it down. */
const PICKER_LIMIT = 20;
const SEARCH_DELAY_MS = 300;

const UOMS: UOMType[] = ['pcs', 'kg', 'g', 'ltr', 'ml', 'pack'];

/**
 * + New product: one not in the system yet. Only name, category and unit now; GST, HSN, MRP come from the bill
 * on the goods receipt, and the selling price after that (Selling prices page). Billing refuses it until then.
 * Loose (weighed) items need a scale code, so they are added on the Products page instead.
 */
function NewProductModal({
  supplierId,
  storeId,
  onCreated,
  onClose,
}: {
  supplierId?: number;
  storeId?: number | '';
  onCreated: (p: ProductRow) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [uom, setUom] = useState<UOMType>('pcs');
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => { listCategories(true).then(setCategories).catch(() => {}); }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr('');
    try {
      const p = await createPendingProduct({
        name: name.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        uom,
        supplier_id: supplierId,
        store_id: typeof storeId === 'number' && storeId > 0 ? storeId : undefined,
      });
      // No rate yet: the line's rate box starts empty, so the agreed rate must be typed before saving the PO.
      onCreated({ id: p.id, name: p.name, sku: p.sku, price: null, selling: null, tax_rate: 0, linked: false });
    } catch (e2) {
      setErr(getErrorMessage(e2));
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 460 }}>
        <button type="button" className="modal-close-btn modal-close-corner" onClick={onClose} aria-label={t('common.close')}>
          <IconX size={18} />
        </button>
        <h3>{t('purchases.newProductTitle')}</h3>
        <p className="hint-text">{t('purchases.newProductHint')}</p>
        {err && <div className="form-error">{err}</div>}
        <form onSubmit={save} className="modal-form">
          <label className="field-label">
            {t('common.name')}
            <MarathiInput className="field-input" value={name} maxLength={200} onChange={setName} required autoFocus />
          </label>
          <label className="field-label">
            {t('products.category')}
            <select className="field-input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">—</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field-label">
            {t('products.uom')}
            <select className="field-input" value={uom} onChange={(e) => setUom(e.target.value as UOMType)}>
              {UOMS.map((u) => <option key={u} value={u}>{t(`products.uoms.${u}`)}</option>)}
            </select>
          </label>
          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={busy || !name.trim()}>
              {busy ? t('common.saving') : t('common.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * Product picker for PO lines. Any product can be ordered from any supplier: no need to link it first.
 * - The supplier's own products (bought from them before) come first, marked "linked", at their last rate.
 * - Then every other matching product from the catalogue, at its cost price if known.
 * Receiving the goods links the product to the supplier automatically, so it is "linked" next time.
 * When no supplier is selected: input is locked with a hint to pick a supplier first.
 */
function ProductSearch({
  onSelect,
  storeId,
  supplierId,
}: {
  onSelect: (p: ProductRow) => void;
  storeId?: number | '';
  supplierId?: number;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<ProductRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [supplierProducts, setSupplierProducts] = useState<ProductRow[]>([]);

  // Fetch all products linked to the chosen supplier once (not per-keystroke).
  useEffect(() => {
    if (!supplierId || supplierId === 0) {
      setSupplierProducts([]);
      setResults([]);
      return;
    }
    supplierApi.getPoProducts(supplierId)
      .then((r) => {
        setSupplierProducts(r.data.map((p) => ({
          id: p.id,
          name: p.name,
          sku: p.sku,
          price: p.purchase_price,
          selling: p.selling_price,
          tax_rate: p.tax_rate,
          linked: true,
        })));
      })
      .catch(() => setSupplierProducts([]));
  }, [supplierId]);

  useEffect(() => {
    if (!open) return;

    // The supplier's own products that match, first (filtered locally from the pre-loaded list).
    const lq = q.trim().toLowerCase();
    const linked = supplierProducts
      .filter((p) => !lq || p.name.toLowerCase().includes(lq) || (p.sku ?? '').toLowerCase().includes(lq))
      .slice(0, PICKER_LIMIT);
    setResults(linked);

    // Then the rest of the catalogue (search by name / SKU / barcode on the server).
    let cancelled = false;
    const sid = typeof storeId === 'number' && storeId > 0 ? storeId : undefined;
    const timer = window.setTimeout(() => {
      setLoading(true);
      listProducts({ q: q.trim() || undefined, per_page: PICKER_LIMIT, active_only: true, store_id: sid })
        .then((data) => {
          if (cancelled) return;
          const linkedIds = new Set(supplierProducts.map((p) => p.id));
          const others: ProductRow[] = (data.items || [])
            .filter((p) => !linkedIds.has(p.id))
            .map((p) => ({
              id: p.id,
              name: p.name,
              sku: p.sku,
              // Never the selling price as a purchase rate: the cost if known, else typed in.
              price: p.cost_price != null ? Math.round(parseFloat(p.cost_price) * 100) / 100 : null,
              selling: parseFloat(p.store_price ?? p.price ?? '0'),
              tax_rate: parseFloat(p.tax_rate ?? '0'),
              linked: false,
            }));
          setResults([...linked, ...others]);
        })
        .catch(() => { /* keep the supplier's own products */ })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, q.trim() ? SEARCH_DELAY_MS : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [q, open, storeId, supplierId, supplierProducts]);

  function pick(p: ProductRow) {
    onSelect(p);
    setQ('');
    setOpen(false);
  }

  const noSupplier = !supplierId || supplierId === 0;

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ position: 'relative', maxWidth: 560 }}>
        <label className="field-label" style={{ marginBottom: 4, display: 'block', fontSize: 12 }}>
          {t('purchases.productSearch', 'Search product name or SKU')}
          {!noSupplier && supplierProducts.length > 0 && (
            <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 500, color: '#6366f1', background: '#eef2ff', border: '1px solid #e0e7ff', borderRadius: 10, padding: '1px 8px' }}>
              {t('purchases.linkedCount', { count: supplierProducts.length })}
            </span>
          )}
        </label>
        {noSupplier ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: 8, color: '#94a3b8', fontSize: '0.88em' }}>
            <span style={{ fontSize: 18 }}>🔒</span>
            <span>{t('purchases.pickSupplierFirst')}</span>
          </div>
        ) : (
          <>
            <input
              className="field-input"
              placeholder={t('purchases.productSearchHint', 'Type name, SKU or scan barcode')}
              value={q}
              onFocus={() => setOpen(true)}
              onChange={(e) => {
                setQ(e.target.value);
                setOpen(true);
              }}
              onBlur={() => setTimeout(() => setOpen(false), 200)}
            />
            {open && (
              <div
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 4px)',
                  left: 0,
                  right: 0,
                  background: 'var(--surface)',
                  border: '1px solid var(--border-strong)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: 'var(--shadow-lg)',
                  zIndex: 60,
                  maxHeight: 280,
                  overflowY: 'auto',
                }}
              >
                {loading && results.length === 0 && (
                  <div style={{ padding: '9px 14px', color: 'var(--muted)' }}>
                    {t('purchases.loadingProducts', 'Loading available products...')}
                  </div>
                )}
                {!loading && results.length === 0 && (
                  <div style={{ padding: '9px 14px', color: 'var(--muted)' }}>
                    {t('purchases.noProductMatch')}
                  </div>
                )}
                {results.map((p) => (
                  <div
                    key={p.id}
                    style={{
                      padding: '9px 14px',
                      cursor: 'pointer',
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background 100ms',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--brand-50)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                    onMouseDown={() => pick(p)}
                  >
                    <div>
                      <span style={{ fontWeight: 700 }}>{p.name}</span>
                      {p.sku && (
                        <span
                          style={{
                            marginLeft: 8,
                            fontSize: 12,
                            color: 'var(--muted)',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {p.sku}
                        </span>
                      )}
                      {p.linked && (
                        <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 500, color: '#6366f1', background: '#eef2ff', border: '1px solid #e0e7ff', borderRadius: 10, padding: '1px 8px' }}>
                          {t('purchases.linkedTag')}
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-2)', marginLeft: 12, flexShrink: 0 }}>
                      {p.price != null ? `₹${p.price.toFixed(2)}` : t('purchases.ratePlaceholder') + ' ?'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Financial helpers ─────────────────────────────────────────────────────────

interface LineItem extends PurchaseOrderItemPayload {
  _id: number;
  _name: string;
  _sku: string;
  _selling?: number | null; // selling price, for the warning
  _rateMissing?: boolean; // no rate known or typed yet: the order can't be saved
}

/** Rate after the line discount is not below the selling price: probably a typo (or the selling price). */
function rateNotBelowSelling(l: LineItem): boolean {
  if (l._rateMissing || l._selling == null || l._selling <= 0) return false;
  return l.unit_price * (1 - (l.discount_percent ?? 0) / 100) >= l._selling - 0.005;
}

function calcLine(qty: number, price: number, disc: number, tax: number) {
  const gross = qty * price;
  const d = (gross * disc) / 100;
  const t = ((gross - d) * tax) / 100;
  return { gross, disc: d, tax: t };
}

let _lid = 0;
function newLid() { return ++_lid; }

// ── Create / Edit modal ───────────────────────────────────────────────────────

interface PoFormProps {
  editing: PurchaseOrderOut | null;
  suppliers: SupplierOut[];
  stores: StoreOut[];
  onClose: () => void;
  onSaved: (po: PurchaseOrderOut) => void;
}

function PoFormModal({ editing, suppliers, stores, onClose, onSaved }: PoFormProps) {
  const { t } = useTranslation();
  const today = isoDateIst();

  const [supplierId, setSupplierId] = useState(editing?.supplier_id ?? 0);
  const [newProductOpen, setNewProductOpen] = useState(false);
  const [storeId, setStoreId] = useState<number | ''>(editing?.store_id ?? '');
  const [purchaseDate, setPurchaseDate] = useState(editing?.purchase_date ?? today);
  const [expectedDate, setExpectedDate] = useState(editing?.expected_delivery_date ?? '');
  const [ref, setRef] = useState(editing?.reference_number ?? '');
  const [notes, setNotes] = useState(editing?.notes ?? '');
  const [remarks, setRemarks] = useState(editing?.internal_remarks ?? '');
  const [lines, setLines] = useState<LineItem[]>(() => {
    if (!editing?.items?.length) return [];
    return editing.items.map((i) => ({
      _id: newLid(),
      _name: i.product_name,
      _sku: i.product_sku ?? '',
      product_id: i.product_id,
      ordered_qty: parseFloat(i.ordered_qty),
      unit_price: parseFloat(i.unit_price),
      discount_percent: parseFloat(i.discount_percent),
      tax_rate: parseFloat(i.tax_rate),
    }));
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  function addLine(p: ProductRow) {
    setLines((prev) => [
      ...prev,
      {
        _id: newLid(),
        _name: p.name,
        _sku: p.sku ?? '',
        product_id: p.id,
        ordered_qty: 1,
        unit_price: p.price ?? 0,
        discount_percent: 0,
        tax_rate: p.tax_rate,
        _selling: p.selling,
        _rateMissing: p.price == null,
      },
    ]);
  }

  function updateLine(id: number, field: string, value: number) {
    setLines((prev) =>
      prev.map((l) => l._id !== id ? l : { ...l, [field]: value }),
    );
  }

  /** Blank = no rate yet (not ₹0), so the order can't go out without one. */
  function updateRate(id: number, text: string) {
    setLines((prev) => prev.map((l) => l._id !== id ? l : {
      ...l,
      unit_price: parseFloat(text) || 0,
      _rateMissing: text.trim() === '' || Number.isNaN(parseFloat(text)),
    }));
  }

  function removeLine(id: number) {
    setLines((prev) => prev.filter((l) => l._id !== id));
  }

  // Totals
  let subtotal = 0, discTotal = 0, taxTotal = 0;
  for (const l of lines) {
    const c = calcLine(l.ordered_qty, l.unit_price, l.discount_percent ?? 0, l.tax_rate ?? 0);
    subtotal += c.gross;
    discTotal += c.disc;
    taxTotal += c.tax;
  }
  const grandTotal = subtotal - discTotal + taxTotal;

  async function save() {
    if (purchaseDate > isoDateIst()) { setErr(t('purchases.fieldDate') + ' cannot be in the future'); return; }
    if (!supplierId) { setErr(t('purchases.fieldSupplier') + ' is required'); return; }
    if (lines.length === 0) { setErr(t('purchases.noItems')); return; }
    const missing = lines.filter((l) => l._rateMissing).map((l) => l._name);
    if (missing.length > 0) { setErr(t('purchases.rateMissing', { names: missing.join(', ') })); return; }
    setSaving(true);
    setErr('');
    try {
      const payload = {
        supplier_id: supplierId,
        store_id: storeId || null,
        purchase_date: purchaseDate,
        expected_delivery_date: expectedDate || null,
        reference_number: ref || null,
        notes: notes || null,
        internal_remarks: remarks || null,
        items: lines.map((l) => ({
          product_id: l.product_id,
          ordered_qty: l.ordered_qty,
          unit_price: l.unit_price,
          discount_percent: l.discount_percent ?? 0,
          tax_rate: l.tax_rate ?? 0,
        })),
      };
      const r = editing
        ? await purchaseApi.update(editing.id, payload as PurchaseOrderUpdatePayload)
        : await purchaseApi.create(payload as PurchaseOrderCreatePayload);
      onSaved(r.data);
    } catch (e) {
      setErr(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay">
      <div
        className="modal-box"
        style={{ maxWidth: 900, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="modal-header">
          <div>
            <p className="modal-subtitle">{t('purchases.title')}</p>
            <h3 className="modal-title" style={{ margin: 0 }}>
              {editing
                ? t('purchases.editTitle', { po: editing.po_number })
                : t('purchases.addTitle')}
            </h3>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <IconX size={18} />
          </button>
        </div>

        <div className="modal-form">
          {err && <div className="page-error">{err}</div>}

          {/* Section — Order info */}
          <fieldset className="form-section">
            <legend>{t('purchases.sectionInfo')}</legend>
            <div className="form-row">
              <label className="field-label">
                {t('purchases.fieldSupplier')} *
                <select
                  className="field-input"
                  value={supplierId}
                  onChange={(e) => {
                    const newId = Number(e.target.value);
                    if (newId !== supplierId && lines.length > 0) {
                      if (!window.confirm('Changing the supplier will clear all line items. Continue?')) return;
                      setLines([]);
                    }
                    setSupplierId(newId);
                  }}
                >
                  <option value={0}>{t('purchases.chooseSupplier')}</option>
                  {suppliers.map((s) => (
                    <option key={s.id} value={s.id}>{s.company_name}</option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                {t('purchases.fieldStore')}
                <select
                  className="field-input"
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value ? Number(e.target.value) : '')}
                >
                  <option value="">{t('purchases.chooseStore')}</option>
                  {stores.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                {t('purchases.fieldDate')} *
                <input
                  className="field-input"
                  type="date"
                  value={purchaseDate}
                  max={isoDateIst()}
                  onChange={(e) => setPurchaseDate(e.target.value)}
                />
              </label>
              <label className="field-label">
                {t('purchases.fieldExpected')}
                <input
                  className="field-input"
                  type="date"
                  value={expectedDate}
                  min={purchaseDate || isoDateIst()}
                  onChange={(e) => setExpectedDate(e.target.value)}
                />
              </label>
              <label className="field-label">
                {t('purchases.fieldRef')}
                <input
                  className="field-input"
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                />
              </label>
              <label className="field-label">
                {t('purchases.fieldNotes')}
                <input
                  className="field-input"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
              <label className="field-label" style={{ gridColumn: '1 / -1' }}>
                {t('purchases.fieldRemarks')}
                <textarea
                  className="field-input"
                  rows={2}
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                />
              </label>
            </div>
          </fieldset>

          {/* Section — Line items */}
          <fieldset className="form-section">
            <legend>{t('purchases.sectionItems')}</legend>
            <ProductSearch onSelect={addLine} storeId={storeId} supplierId={supplierId || undefined} />
            {supplierId ? (
              <button type="button" className="btn-sm" style={{ marginTop: -8, marginBottom: 12 }} onClick={() => setNewProductOpen(true)}>
                + {t('purchases.newProduct')}
              </button>
            ) : null}
            {newProductOpen && (
              <NewProductModal
                supplierId={supplierId || undefined}
                storeId={storeId}
                onClose={() => setNewProductOpen(false)}
                onCreated={(p) => { addLine(p); setNewProductOpen(false); }}
              />
            )}

            {lines.length > 0 && (
              <div className="table-card" style={{ marginTop: 12 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t('purchases.colProduct')}</th>
                      <th style={{ width: 80 }}>{t('purchases.colQty')}</th>
                      <th style={{ width: 110 }}>{t('purchases.colPrice')} (₹)</th>
                      <th style={{ width: 80 }}>{t('purchases.colDisc')} %</th>
                      <th style={{ width: 80 }}>{t('purchases.colTax')} %</th>
                      <th className="num" style={{ width: 100 }}>{t('purchases.colLineTotal')}</th>
                      <th style={{ width: 40 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l) => {
                      const { gross } = calcLine(
                        l.ordered_qty,
                        l.unit_price,
                        l.discount_percent ?? 0,
                        l.tax_rate ?? 0,
                      );
                      return (
                        <tr key={l._id}>
                          <td>
                            <div style={{ fontWeight: 700 }}>{l._name}</div>
                            {l._sku && (
                              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>
                                {l._sku}
                              </div>
                            )}
                          </td>
                          <td>
                            <input
                              className="field-input"
                              type="number"
                              min="0.001"
                              step="0.001"
                              value={l.ordered_qty}
                              onChange={(e) => updateLine(l._id, 'ordered_qty', parseFloat(e.target.value) || 0)}
                              style={{ padding: '5px 8px', minHeight: 32 }}
                            />
                          </td>
                          <td>
                            <input
                              className="field-input"
                              type="number"
                              min="0"
                              step="0.01"
                              value={l._rateMissing ? '' : l.unit_price}
                              placeholder={t('purchases.ratePlaceholder')}
                              aria-invalid={l._rateMissing || rateNotBelowSelling(l)}
                              onChange={(e) => updateRate(l._id, e.target.value)}
                              style={{
                                padding: '5px 8px',
                                minHeight: 32,
                                ...(l._rateMissing || rateNotBelowSelling(l) ? { borderColor: 'var(--danger-border)' } : {}),
                              }}
                            />
                            {l._selling != null && (
                              <div className={`hint-text${rateNotBelowSelling(l) ? ' text-danger' : ''}`} style={{ fontSize: 11, marginTop: 2 }}>
                                {rateNotBelowSelling(l)
                                  ? t('purchases.rateNotBelowSelling', { price: l._selling.toFixed(2) })
                                  : t('purchases.sellsAt', { price: l._selling.toFixed(2) })}
                              </div>
                            )}
                          </td>
                          <td>
                            <input
                              className="field-input"
                              type="number"
                              min="0"
                              max="100"
                              step="0.01"
                              value={l.discount_percent ?? 0}
                              onChange={(e) => updateLine(l._id, 'discount_percent', parseFloat(e.target.value) || 0)}
                              style={{ padding: '5px 8px', minHeight: 32 }}
                            />
                          </td>
                          <td>
                            <input
                              className="field-input"
                              type="number"
                              min="0"
                              step="0.01"
                              value={l.tax_rate ?? 0}
                              onChange={(e) => updateLine(l._id, 'tax_rate', parseFloat(e.target.value) || 0)}
                              style={{ padding: '5px 8px', minHeight: 32 }}
                            />
                          </td>
                          <td className="num" style={{ fontWeight: 700, fontSize: 14 }}>
                            ₹{gross.toFixed(2)}
                          </td>
                          <td>
                            <button
                              className="btn-sm"
                              style={{ color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
                              onClick={() => removeLine(l._id)}
                              title="Remove"
                            >
                              <IconTrash size={14} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr className="total-row">
                      <td colSpan={5} className="num" style={{ fontSize: 13, fontWeight: 600 }}>
                        {t('purchases.subtotal')} &nbsp; ₹{subtotal.toFixed(2)} &nbsp;—&nbsp;
                        {t('purchases.discountAmount')} &nbsp; ₹{discTotal.toFixed(2)} &nbsp;+&nbsp;
                        {t('purchases.taxAmount')} &nbsp; ₹{taxTotal.toFixed(2)}
                      </td>
                      <td className="num" style={{ fontSize: 17, fontWeight: 800, letterSpacing: '-0.02em' }}>
                        ₹{grandTotal.toFixed(2)}
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </fieldset>
        </div>

        <div className="modal-buttons">
          <button className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Detail modal ──────────────────────────────────────────────────────────────

function DetailModal({
  po,
  stores,
  onClose,
  onPlace,
  onCancel,
  onReceive,
  onEdit,
  onSend,
  onOpenInvoices,
}: {
  po: PurchaseOrderOut;
  stores: StoreOut[];
  onClose: () => void;
  onPlace: () => void;
  onCancel: () => void;
  onReceive: () => void;
  onEdit: () => void;
  /** Opens "Send to supplier" (email / WhatsApp / PDF / mark as sent). */
  onSend: () => void;
  /** Payments are made on the supplier's invoices: go to the supplier's Invoices tab. */
  onOpenInvoices: () => void;
}) {
  const { t } = useTranslation();
  const [receipts, setReceipts] = useState<GoodsReceiptOut[] | null>(null);
  const [showReceipts, setShowReceipts] = useState(false);
  const [paymentSummary, setPaymentSummary] = useState<POPaymentSummary | null>(null);

  const canPlace = po.status === 'draft';
  const canCancel = po.status === 'draft' || po.status === 'ordered';
  const canReceive = po.status === 'ordered' || po.status === 'partially_received';
  const canEdit = po.status === 'draft';
  const canPay = po.status !== 'draft' && po.status !== 'cancelled';
  const canSend = SENDABLE.includes(po.status) && !po.is_direct; // a direct purchase: the goods already came

  useEffect(() => {
    if (!canPay) return;
    purchaseApi.getPaymentSummary(po.id)
      .then((r) => setPaymentSummary(r.data))
      .catch(() => {});
  }, [po.id, canPay]);

  const storeName = stores.find((s) => s.id === po.store_id)?.name ?? (po.store_id ? `Store #${po.store_id}` : '—');

  async function loadReceipts() {
    try {
      const r = await purchaseApi.listReceipts(po.id);
      setReceipts(r.data);
    } catch {
      setReceipts([]);
    }
    setShowReceipts(true);
  }

  return (
    <div className="modal-overlay">
      <div
        className="modal-box"
        style={{ maxWidth: 820, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="modal-header">
          <div>
            <p className="modal-subtitle">{t('purchases.title')}</p>
            <div className="title-with-icon">
              <h3 className="modal-title" style={{ margin: 0 }}>
                {t('purchases.detailTitle', { po: po.po_number })}
              </h3>
              <StatusBadge status={po.status} />
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose}><IconX size={18} /></button>
        </div>

        {/* Meta row */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: '8px 20px',
            padding: '12px 16px',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            marginBottom: 18,
            fontSize: 13,
          }}
        >
          <div>
            <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
              {t('purchases.fieldSupplier')}
            </div>
            <div style={{ fontWeight: 700 }}>{po.supplier_name}</div>
          </div>
          <div>
            <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
              {t('purchases.fieldDate')}
            </div>
            <div style={{ fontWeight: 600 }}>{formatDate(po.purchase_date)}</div>
          </div>
          {po.expected_delivery_date && (
            <div>
              <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                {t('purchases.fieldExpected')}
              </div>
              <div style={{ fontWeight: 600 }}>{formatDate(po.expected_delivery_date)}</div>
            </div>
          )}
          <div>
            <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
              {t('purchases.fieldStore')}
            </div>
            <div style={{ fontWeight: 600 }}>{storeName}</div>
          </div>
          {po.reference_number && (
            <div>
              <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                {t('purchases.fieldRef')}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{po.reference_number}</div>
            </div>
          )}
          {po.ordered_at && (
            <div>
              <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                Ordered
              </div>
              <div style={{ fontWeight: 600 }}>{formatDate(po.ordered_at)}</div>
            </div>
          )}
          {canSend && (
            <div>
              <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                {t('purchases.send.fieldSent')}
              </div>
              <div style={{ fontWeight: 600, color: po.sent_at ? 'var(--ok-text)' : 'var(--warn-text)' }}>
                {po.sent_at && po.sent_via
                  ? t('purchases.send.sentLine', {
                    via: t(`purchases.send.via.${po.sent_via}` as const),
                    date: formatDate(po.sent_at),
                  })
                  : t('purchases.send.notSent')}
              </div>
            </div>
          )}
          {po.notes && (
            <div style={{ gridColumn: '1 / -1' }}>
              <div style={{ color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                {t('purchases.fieldNotes')}
              </div>
              <div>{po.notes}</div>
            </div>
          )}
        </div>

        {/* Items table */}
        <div className="table-card" style={{ marginBottom: 16 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('purchases.colProduct')}</th>
                <th className="num">{t('purchases.colQty')}</th>
                <th className="num">{t('purchases.colReceived')}</th>
                <th className="num">{t('purchases.colPrice')}</th>
                <th className="num">{t('purchases.colDisc')} %</th>
                <th className="num">{t('purchases.colTax')} %</th>
                <th className="num">{t('purchases.colLineTotal')}</th>
              </tr>
            </thead>
            <tbody>
              {po.items.map((item: PurchaseOrderItemOut) => {
                const isDone = parseFloat(item.received_qty) >= parseFloat(item.ordered_qty);
                return (
                  <tr key={item.id}>
                    <td>
                      <div style={{ fontWeight: 700 }}>{item.product_name}</div>
                      {item.product_sku && (
                        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>
                          {item.product_sku}
                        </div>
                      )}
                    </td>
                    <td className="num">{item.ordered_qty}</td>
                    <td
                      className="num"
                      style={{ color: isDone ? 'var(--ok)' : 'var(--text)', fontWeight: isDone ? 700 : undefined }}
                    >
                      {item.received_qty}
                    </td>
                    <td className="num">₹{parseFloat(item.unit_price).toFixed(2)}</td>
                    <td className="num">{item.discount_percent}</td>
                    <td className="num">{item.tax_rate}</td>
                    <td className="num" style={{ fontWeight: 700 }}>
                      ₹{parseFloat(item.line_total).toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="total-row">
                <td colSpan={6} className="num" style={{ fontSize: 13 }}>
                  {t('purchases.subtotal')} ₹{parseFloat(po.subtotal).toFixed(2)} &nbsp;—&nbsp;
                  {t('purchases.discountAmount')} ₹{parseFloat(po.discount_amount).toFixed(2)} &nbsp;+&nbsp;
                  {t('purchases.taxAmount')} ₹{parseFloat(po.tax_amount).toFixed(2)} &nbsp;=
                </td>
                <td className="num" style={{ fontSize: 17, fontWeight: 800 }}>
                  ₹{parseFloat(po.grand_total).toFixed(2)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* Money: payments are made against the supplier's invoices, never more than the goods received */}
        {paymentSummary && (
          <div style={{ marginBottom: 16 }}>
            <div
              style={{
                display: 'flex',
                gap: 0,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                overflow: 'hidden',
              }}
            >
              {[
                { label: 'Received (GRN)', val: paymentSummary.received_value, color: 'var(--text)' },
                { label: 'Invoiced', val: paymentSummary.invoiced_amount, color: 'var(--text)' },
                { label: 'Payable', val: paymentSummary.payable_amount, color: 'var(--text)' },
                { label: 'Paid', val: paymentSummary.total_paid, color: 'var(--ok)' },
                { label: 'Balance', val: paymentSummary.outstanding, color: parseFloat(paymentSummary.outstanding) > 0 ? '#d97706' : 'var(--ok)' },
              ].map((col, i) => (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    textAlign: 'center',
                    padding: '10px 8px',
                    borderRight: '1px solid var(--border)',
                    background: 'var(--surface-2)',
                  }}
                >
                  <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{col.label}</div>
                  <div style={{ fontWeight: 800, fontSize: 15, color: col.color }}>
                    ₹{parseFloat(col.val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
              ))}
              <div style={{ flex: 1, textAlign: 'center', padding: '10px 8px', background: 'var(--surface-2)' }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Status</div>
                <PaymentStatusBadge status={paymentSummary.payment_status} />
              </div>
            </div>
            {parseFloat(paymentSummary.not_invoiced_value) > 0.005 && (
              <p className="hint-text" style={{ margin: '6px 0 0' }}>
                ₹{parseFloat(paymentSummary.not_invoiced_value).toFixed(2)} of goods received has no supplier invoice yet.
                Add the supplier's bill from the supplier page, then pay against it.
              </p>
            )}
          </div>
        )}

        {/* Receipts section */}
        {showReceipts && receipts !== null && (
          <div>
            <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 700, color: 'var(--text-2)' }}>
              {t('purchases.receiptsTitle', { po: po.po_number })}
            </h4>
            {receipts.length === 0 ? (
              <p style={{ color: 'var(--muted)', fontSize: 13 }}>{t('purchases.noReceipts')}</p>
            ) : (
              receipts.map((r) => (
                <div
                  key={r.id}
                  style={{
                    padding: '10px 14px',
                    marginBottom: 8,
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--brand)' }}>
                      {r.receipt_number}
                    </span>
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                      {formatDate(r.received_at)} &nbsp;·&nbsp; {r.received_by_name || '—'}
                    </span>
                  </div>
                  {r.notes && <p style={{ margin: '4px 0 6px', fontSize: 12, color: 'var(--text-2)' }}>{r.notes}</p>}
                  <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-2)' }}>
                    {r.receipt_items.map((ri) => (
                      <span
                        key={ri.id}
                        style={{
                          display: 'inline-block',
                          marginRight: 12,
                          padding: '1px 8px',
                          background: 'var(--ok-bg)',
                          color: 'var(--ok-text)',
                          borderRadius: 999,
                          fontSize: 11.5,
                          fontWeight: 600,
                        }}
                      >
                        {ri.product_name}: {ri.qty_accepted ?? ri.qty_received}
                        {parseFloat(ri.qty_rejected) > 0 ? ` (+${ri.qty_rejected} rejected)` : ''}
                        {parseFloat(ri.qty_damaged) > 0 ? ` (+${ri.qty_damaged} damaged)` : ''}
                        {ri.remarks ? ` · ${ri.remarks}` : ''}
                        {ri.expiry_date ? ` · exp ${ri.expiry_date}` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Footer actions */}
        <div className="modal-buttons" style={{ flexWrap: 'wrap', gap: 8 }}>
          <button className="btn-secondary" onClick={onClose}>{t('common.close')}</button>
          {!showReceipts && (
            <button className="btn-secondary" onClick={loadReceipts}>
              {t('purchases.viewReceipts')}
            </button>
          )}
          {canEdit && (
            <button className="btn-secondary" onClick={onEdit}>
              <IconEdit size={14} /> {t('common.edit')}
            </button>
          )}
          <button className="btn-secondary" onClick={() => void downloadPoPdf(po)}>
            {t('purchases.send.downloadPdf')}
          </button>
          {canSend && (
            <button className="btn-primary" onClick={onSend}>
              {t('purchases.send.button')}
            </button>
          )}
          {canPay && (
            <button className="btn-secondary" onClick={onOpenInvoices}>
              Supplier invoices &amp; payments →
            </button>
          )}
          {canReceive && (
            <button className="btn-primary" onClick={onReceive}>
              <IconCheck size={14} /> {t('purchases.receiveGoods')}
            </button>
          )}
          {canPlace && (
            <button
              className="btn-primary"
              style={{ background: 'linear-gradient(180deg,#22c55e,#16a34a)', borderColor: '#15803d' }}
              onClick={onPlace}
            >
              {t('purchases.placeOrder')}
            </button>
          )}
          {canCancel && (
            <button
              className="btn-primary btn-warning-bg"
              onClick={onCancel}
            >
              {t('purchases.cancelOrder')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Receive Goods modal ───────────────────────────────────────────────────────

function ReceiveModal({
  po,
  onClose,
  onSaved,
}: {
  po: PurchaseOrderOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const today = isoDateTimeLocalIst();
  const [receivedAt, setReceivedAt] = useState(today);
  const [notes, setNotes] = useState('');
  // With the godown on, goods go to the godown unless a line is ticked "straight to shelf" (milk, bread).
  const [godownOn, setGodownOn] = useState(false);
  useEffect(() => { getSettings().then((s) => setGodownOn(s.godown_enabled)).catch(() => {}); }, []);
  const [lines, setLines] = useState<{
    item: PurchaseOrderItemOut; qty: string; rejected: string; damaged: string; expiry: string; batch: string; remarks: string; toShop: boolean;
    // From the supplier's bill; they start at the PO / product figures, so a matching bill needs no typing.
    rate: string; gst: string; mrp: string; hsn: string;
  }[]>(
    () =>
      po.items
        .filter((i) => parseFloat(i.received_qty) < parseFloat(i.ordered_qty))
        .map((i) => ({
          item: i,
          qty: (parseFloat(i.ordered_qty) - parseFloat(i.received_qty)).toFixed(3),
          rejected: '',
          damaged: '',
          expiry: '',
          batch: '',
          remarks: '',
          toShop: false,
          rate: String(Number(i.unit_price)),
          gst: String(Number(i.tax_rate)),
          mrp: i.product_mrp ? String(Number(i.product_mrp)) : '',
          hsn: i.product_hsn_code ?? '',
        })),
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [toReview, setToReview] = useState<number[] | null>(null); // goods saved; these prices need a look
  const navigate = useNavigate();

  type Line = (typeof lines)[number];
  function setLine(idx: number, patch: Partial<Line>) {
    setLines((prev) => prev.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  }
  const bad = (l: Line) => (parseFloat(l.rejected) || 0) + (parseFloat(l.damaged) || 0);
  const todayDate = today.slice(0, 10); // YYYY-MM-DD, India time
  // Days from today to the expiry date (negative = already expired); null when no date is entered.
  function daysLeft(expiry: string): number | null {
    if (!expiry) return null;
    return Math.round((new Date(expiry).getTime() - new Date(todayDate).getTime()) / 86_400_000);
  }

  async function submit() {
    const wrong = lines.find((l) => bad(l) > (parseFloat(l.qty) || 0));
    if (wrong) { setErr(`${wrong.item.product_name}: rejected + damaged can't be more than what arrived.`); return; }
    const noReason = lines.find((l) => bad(l) > 0 && !l.remarks.trim());
    if (noReason) { setErr(`${noReason.item.product_name}: write the reason for the rejected / damaged goods.`); return; }
    const expired = lines.find((l) => {
      const d = daysLeft(l.expiry);
      return d !== null && d < 0 && (parseFloat(l.qty) || 0) - bad(l) > 0;
    });
    if (expired) { setErr(`${expired.item.product_name}: already expired. Mark these goods as rejected.`); return; }
    const items: GoodsReceiptItemPayload[] = lines
      .filter((l) => parseFloat(l.qty) > 0)
      .map((l) => ({
        purchase_order_item_id: l.item.id,
        qty_received: parseFloat(l.qty),
        // Rejected / damaged goods: not stocked, not paid for, still owed by the supplier.
        qty_rejected: parseFloat(l.rejected) || 0,
        qty_damaged: parseFloat(l.damaged) || 0,
        remarks: l.remarks.trim() || null,
        expiry_date: l.expiry || null,
        batch_number: l.batch || null,
        to_shop: godownOn && l.toShop,
        // Bill details: only what differs, so a line that matches the PO stays exactly as it was. A new product
        // always sends its GST: it becomes the product's selling GST.
        ...(l.rate !== '' && Number(l.rate) !== Number(l.item.unit_price) ? { bill_unit_price: Number(l.rate) } : {}),
        ...(l.gst !== '' && (l.item.product_details_pending || Number(l.gst) !== Number(l.item.tax_rate))
          ? { bill_tax_rate: Number(l.gst) } : {}),
        ...(l.mrp !== '' && Number(l.mrp) !== Number(l.item.product_mrp ?? 0) ? { mrp: Number(l.mrp) } : {}),
        ...(l.hsn.trim() && l.hsn.trim() !== (l.item.product_hsn_code ?? '') ? { hsn_code: l.hsn.trim() } : {}),
      }));
    if (items.length === 0) { setErr('No items to receive.'); return; }
    if (receivedAt && receivedAt > isoDateTimeLocalIst()) {
      setErr(t('purchases.receiveDate') + ' cannot be in the future.');
      return;
    }
    setSaving(true);
    setErr('');
    try {
      await purchaseApi.receiveGoods(po.id, {
        received_at: receivedAt || null,
        notes: notes || null,
        items,
      });
      // The cost may have changed: ask about selling prices that no longer give the profit wanted.
      const productIds = lines.filter((l) => parseFloat(l.qty) > 0).map((l) => l.item.product_id);
      const review = await getPriceReview(productIds).catch(() => null);
      if (review && review.items.length > 0) {
        setToReview(review.items.map((r) => r.product_id));
        return;
      }
      onSaved();
    } catch (e) {
      setErr(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  if (toReview) {
    // Goods are saved. Some selling prices no longer give the profit wanted: offer to fix them now.
    return (
      <div className="modal-overlay">
        <div className="modal-box" style={{ maxWidth: 480 }}>
          <h3>{t('purchases.receivedTitle')}</h3>
          <p>{t('purchases.pricesToReview', { count: toReview.length })}</p>
          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onSaved}>{t('purchases.reviewLater')}</button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => navigate(`/admin/price-review?products=${toReview.join(',')}`)}
            >
              {t('purchases.reviewNow')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay">
      <div
        className="modal-box"
        style={{ maxWidth: 940, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
      >
        <div className="modal-header">
          <div>
            <p className="modal-subtitle">
              {po.po_number}
              {po.status === 'partially_received' && (
                <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 700, padding: '1px 8px', borderRadius: 999, background: 'var(--warn-bg)', color: 'var(--warn-text)' }}>
                  Completing Partial Receipt
                </span>
              )}
            </p>
            <h3 className="modal-title" style={{ margin: 0 }}>{t('purchases.receiveTitle', { po: po.po_number })}</h3>
          </div>
          <button className="modal-close-btn" onClick={onClose}><IconX size={18} /></button>
        </div>

        <div className="modal-form">
          {err && <div className="page-error">{err}</div>}

          <div className="form-row">
            <label className="field-label">
              {t('purchases.receiveDate')}
              <input
                className="field-input"
                type="datetime-local"
                value={receivedAt}
                max={isoDateTimeLocalIst()}
                onChange={(e) => setReceivedAt(e.target.value)}
              />
            </label>
            <label className="field-label">
              {t('purchases.receiveNotes')}
              <input
                className="field-input"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
          </div>

          <div className="table-card" style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('purchases.colProduct')}</th>
                  <th className="num">{t('purchases.receiveQty')}</th>
                  <th className="num" title="Sent back: expired, wrong item, bad quality. Not stocked, not paid for; the supplier still owes them">Rejected</th>
                  <th className="num" title="Arrived broken or leaking. Not stocked, not paid for; the supplier still owes them">Damaged</th>
                  <th title="Required when goods are rejected or damaged">Reason</th>
                  <th>Batch No.</th>
                  <th>{t('purchases.expiryDate')}</th>
                  {godownOn && <th title={t('purchases.toShopHint')}>{t('purchases.toShop')}</th>}
                  <th className="num" title={t('purchases.billRateHint')}>{t('purchases.billRate')}</th>
                  <th className="num">{t('purchases.billGst')}</th>
                  <th className="num">MRP</th>
                  <th>HSN</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l, idx) => {
                  const outstanding = parseFloat(l.item.ordered_qty) - parseFloat(l.item.received_qty);
                  const d = daysLeft(l.expiry);
                  return (
                    <tr key={l.item.id}>
                      <td>
                        <div style={{ fontWeight: 700 }}>{l.item.product_name}</div>
                        <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                          {t('purchases.outstanding', { qty: outstanding.toFixed(3) })}
                        </div>
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="number"
                          min="0"
                          max={outstanding}
                          step="0.001"
                          value={l.qty}
                          onChange={(e) => setLine(idx, { qty: e.target.value })}
                          style={{ padding: '5px 8px', minHeight: 34, width: 100 }}
                        />
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="number"
                          min="0"
                          step="0.001"
                          value={l.rejected}
                          placeholder="0"
                          onChange={(e) => setLine(idx, { rejected: e.target.value })}
                          style={{ padding: '5px 8px', minHeight: 34, width: 80 }}
                        />
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="number"
                          min="0"
                          step="0.001"
                          value={l.damaged}
                          placeholder="0"
                          onChange={(e) => setLine(idx, { damaged: e.target.value })}
                          style={{ padding: '5px 8px', minHeight: 34, width: 80 }}
                        />
                        {bad(l) > 0 && (
                          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                            To stock: {Math.max((parseFloat(l.qty) || 0) - bad(l), 0).toFixed(3)}
                          </div>
                        )}
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="text"
                          list="grn-reasons"
                          value={l.remarks}
                          placeholder={bad(l) > 0 ? 'Required' : 'Optional'}
                          onChange={(e) => setLine(idx, { remarks: e.target.value })}
                          style={{
                            minHeight: 34,
                            width: 140,
                            borderColor: bad(l) > 0 && !l.remarks.trim() ? 'var(--danger)' : undefined,
                          }}
                        />
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="text"
                          value={l.batch}
                          placeholder="Optional"
                          onChange={(e) => setLine(idx, { batch: e.target.value })}
                          style={{ minHeight: 34, width: 110 }}
                        />
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="date"
                          value={l.expiry}
                          onChange={(e) => setLine(idx, { expiry: e.target.value })}
                          style={{ minHeight: 34 }}
                        />
                        {d !== null && d < 0 && (
                          <div style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 600 }}>
                            Expired {-d} day(s) ago.{' '}
                            <button
                              type="button"
                              onClick={() => setLine(idx, { rejected: l.qty, damaged: '', remarks: 'Expired' })}
                              style={{ background: 'none', border: 0, padding: 0, color: 'inherit', textDecoration: 'underline', cursor: 'pointer', font: 'inherit' }}
                            >
                              Reject all as expired
                            </button>
                          </div>
                        )}
                        {d !== null && d >= 0 && d <= 30 && (
                          <div style={{ fontSize: 11, color: 'var(--warn-text)' }}>Expires in {d} day(s)</div>
                        )}
                      </td>
                      {godownOn && (
                        <td style={{ textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={l.toShop}
                            onChange={(e) => setLine(idx, { toShop: e.target.checked })}
                          />
                        </td>
                      )}
                      {(() => {
                        // Part of this line already came in at the PO rate: its rate / GST can't change now.
                        const locked = parseFloat(l.item.received_qty) > 0;
                        const box = { padding: '5px 8px', minHeight: 34, width: 90 } as const;
                        return (
                          <>
                            <td>
                              <input
                                className="field-input" type="number" min="0" step="0.01" style={box}
                                value={l.rate} disabled={locked} title={locked ? t('purchases.rateLocked') : ''}
                                aria-label={t('purchases.billRate')}
                                onChange={(e) => setLine(idx, { rate: e.target.value })}
                              />
                            </td>
                            <td>
                              <input
                                className="field-input" type="number" min="0" max="100" step="0.01" style={{ ...box, width: 70 }}
                                value={l.gst} disabled={locked} title={locked ? t('purchases.rateLocked') : ''}
                                aria-label={t('purchases.billGst')}
                                onChange={(e) => setLine(idx, { gst: e.target.value })}
                              />
                            </td>
                            <td>
                              <input
                                className="field-input" type="number" min="0" step="0.01" style={box}
                                value={l.mrp} placeholder="—" aria-label="MRP"
                                onChange={(e) => setLine(idx, { mrp: e.target.value })}
                              />
                            </td>
                            <td>
                              <input
                                className="field-input" type="text" inputMode="numeric" maxLength={8} style={box}
                                value={l.hsn} placeholder={l.item.product_details_pending ? t('purchases.fromBill') : '—'}
                                aria-label="HSN"
                                onChange={(e) => setLine(idx, { hsn: e.target.value.replace(/\D/g, '') })}
                              />
                              {l.item.product_details_pending && (
                                <div style={{ fontSize: 11, color: 'var(--warn-text)' }}>{t('purchases.newProductLine')}</div>
                              )}
                            </td>
                          </>
                        );
                      })()}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <datalist id="grn-reasons">
              <option value="Expired" />
              <option value="Near expiry" />
              <option value="Broken / leaking" />
              <option value="Wrong item" />
              <option value="Poor quality" />
              <option value="Extra quantity" />
            </datalist>
          </div>
        </div>

        <div className="modal-buttons">
          <button className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
          <button className="btn-primary" onClick={submit} disabled={saving}>
            {saving ? t('common.saving') : t('purchases.submitReceive')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Send to supplier ──────────────────────────────────────────────────────────

const SENDABLE: PurchaseStatus[] = ['ordered', 'partially_received', 'received'];
// Email isn't a manual choice: the app records an email itself when it goes out.
const MANUAL_VIA: POSentVia[] = ['whatsapp', 'phone', 'in_person', 'other'];

/** "Sent: WhatsApp · 02 Nov 2026" / "Not sent" next to the status of an ordered PO. */
function SentBadge({ po }: { po: PurchaseOrderOut }) {
  const { t } = useTranslation();
  if (!SENDABLE.includes(po.status)) return null;
  const sent = po.sent_at !== null;
  return (
    <div
      style={{ fontSize: 11, marginTop: 3, fontWeight: 600, color: sent ? 'var(--ok-text)' : 'var(--warn-text)' }}
      title={sent && po.sent_via ? t(`purchases.send.via.${po.sent_via}` as const) : undefined}
    >
      {sent ? `✓ ${t('purchases.send.sent')}` : t('purchases.send.notSent')}
    </div>
  );
}

async function downloadPoPdf(po: PurchaseOrderOut) {
  try {
    await purchaseApi.downloadPdf(po.id, po.po_number);
  } catch (e) {
    alert(await getBlobErrorMessage(e));
  }
}

/**
 * Email (automatic when the PO is placed, or the button here), WhatsApp, PDF, copy text and "mark as sent".
 * onChanged gets the PO back whenever its sent / email state changes.
 */
function SendToSupplierModal({
  po,
  onClose,
  onChanged,
}: {
  po: PurchaseOrderOut;
  onClose: () => void;
  onChanged: (po: PurchaseOrderOut) => void;
}) {
  const { t } = useTranslation();
  const [msg, setMsg] = useState<SupplierMessageOut | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'email' | 'mark' | null>(null);
  const [copied, setCopied] = useState(false);
  const [via, setVia] = useState<POSentVia>('whatsapp');

  useEffect(() => {
    purchaseApi.getSupplierMessage(po.id)
      .then((r) => setMsg(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }, [po.id]);

  // The automatic email runs in the background after "Place order": check back until it has finished.
  useEffect(() => {
    if (po.email_status !== 'sending') return;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      try {
        const r = await purchaseApi.get(po.id);
        if (r.data.email_status !== 'sending' || tries >= 15) {
          clearInterval(timer);
          onChanged(r.data);
        }
      } catch {
        if (tries >= 15) clearInterval(timer);
      }
    }, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [po.id, po.email_status]);

  async function sendEmail() {
    setBusy('email');
    setError('');
    try {
      onChanged((await purchaseApi.emailPo(po.id)).data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function markSent() {
    // The app can't see whether a WhatsApp message or call really happened: staff confirm it themselves.
    const sure = window.confirm(
      t('purchases.send.markConfirm', { po: po.po_number, via: t(`purchases.send.via.${via}` as const) }),
    );
    if (!sure) return;
    setBusy('mark');
    setError('');
    try {
      onChanged((await purchaseApi.markSent(po.id, via)).data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function sendWhatsApp() {
    if (!msg?.whatsapp_url) return;
    setError('');
    try {
      await openWhatsApp(msg.whatsapp_url);
      setVia('whatsapp');
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  async function copyText() {
    if (!msg) return;
    try {
      await navigator.clipboard.writeText(msg.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  const to = po.email_to || po.supplier_email || '';
  const canEmail = Boolean(msg?.supplier_email) && Boolean(msg?.email_configured);
  const emailLine =
    po.email_status === 'sending' ? t('purchases.send.emailSending', { to })
    : po.email_status === 'sent' ? t('purchases.send.emailSent', { to })
    : po.email_status === 'failed' ? t('purchases.send.emailFailed', { to, error: po.email_error ?? '' })
    : t('purchases.send.emailNotYet');
  const emailButton =
    po.email_status === 'failed' ? t('purchases.send.retry')
    : po.email_status === 'sent' ? t('purchases.send.sendAgain')
    : t('purchases.send.sendEmail');
  const section: CSSProperties = {
    padding: '12px 14px',
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    marginBottom: 12,
  };
  const label: CSSProperties = {
    color: 'var(--muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6,
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 560, width: '95%' }}>
        <div className="modal-header">
          <div>
            <p className="modal-subtitle">{t('purchases.send.button')}</p>
            <h3 className="modal-title" style={{ margin: 0 }}>
              {t('purchases.send.title', { po: po.po_number, supplier: po.supplier_name })}
            </h3>
          </div>
          <button className="modal-close-btn" onClick={onClose}><IconX size={18} /></button>
        </div>

        {error && <div className="form-error">{error}</div>}
        {!msg && !error && <div className="loading-text">{t('common.loading')}</div>}

        {msg && (
          <>
            <div style={section}>
              <div style={label}>{t('purchases.send.email')}</div>
              {!msg.supplier_email ? (
                <p className="hint-text" style={{ margin: 0 }}>{t('purchases.send.emailNoAddress')}</p>
              ) : !msg.email_configured ? (
                <p className="hint-text" style={{ margin: 0 }}>{t('purchases.send.emailNotSetUp')}</p>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span
                    style={{
                      flex: 1,
                      minWidth: 200,
                      fontSize: 13,
                      color: po.email_status === 'failed' ? 'var(--danger-text)'
                        : po.email_status === 'sent' ? 'var(--ok-text)' : 'var(--text-2)',
                    }}
                  >
                    {emailLine}
                  </span>
                  <button
                    className="btn-secondary"
                    disabled={!canEmail || busy !== null || po.email_status === 'sending'}
                    onClick={sendEmail}
                  >
                    {busy === 'email' ? t('purchases.send.emailing') : emailButton}
                  </button>
                </div>
              )}
            </div>

            <div style={section}>
              <div style={label}>{t('purchases.send.otherWays')}</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  className="btn-primary"
                  style={{ background: 'linear-gradient(180deg,#22c55e,#16a34a)', borderColor: '#15803d' }}
                  disabled={!msg.whatsapp_url}
                  title={msg.whatsapp_url ? undefined : t('purchases.send.noMobile')}
                  onClick={sendWhatsApp}
                >
                  {t('purchases.send.whatsapp')}
                </button>
                <button className="btn-secondary" onClick={() => void downloadPoPdf(po)}>
                  {t('purchases.send.downloadPdf')}
                </button>
                <button className="btn-secondary" onClick={copyText}>
                  {copied ? t('purchases.send.copied') : t('purchases.send.copyText')}
                </button>
              </div>
              <p className="hint-text" style={{ margin: '8px 0 0' }}>
                {msg.whatsapp_url ? t('purchases.send.whatsappPdfHint') : t('purchases.send.noMobile')}
              </p>

              {po.sent_at && po.sent_via ? (
                // Recorded once (email, or marked by hand); sending again above doesn't change it.
                <div style={{ marginTop: 12 }}>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--ok-text)', fontWeight: 600 }}>
                    ✓ {t('purchases.send.fieldSent')}:{' '}
                    {t('purchases.send.sentLine', {
                      via: t(`purchases.send.via.${po.sent_via}` as const),
                      date: formatDateTime(po.sent_at),
                    })}
                    {po.sent_by_name && ` (${t('purchases.send.sentBy', { name: po.sent_by_name })})`}
                  </p>
                  <p className="hint-text" style={{ margin: '4px 0 0' }}>{t('purchases.send.resendHint')}</p>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                  <label className="field-label" style={{ margin: 0 }}>
                    {t('purchases.send.markVia')}
                    <select className="field-input" value={via} onChange={(e) => setVia(e.target.value as POSentVia)}>
                      {MANUAL_VIA.map((v) => <option key={v} value={v}>{t(`purchases.send.via.${v}` as const)}</option>)}
                    </select>
                  </label>
                  <button className="btn-secondary" disabled={busy !== null} onClick={markSent}>
                    <IconCheck size={14} /> {t('purchases.send.markSent')}
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        <div className="modal-buttons">
          <button className="btn-secondary" onClick={onClose}>{t('common.close')}</button>
        </div>
      </div>
    </div>
  );
}

// ── Confirm dialog ────────────────────────────────────────────────────────────

function ConfirmModal({
  title,
  body,
  confirmLabel,
  danger,
  loading,
  onConfirm,
  onClose,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  loading: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 420 }}>
        <div className="modal-header">
          <h3 className="modal-title" style={{ margin: 0 }}>{title}</h3>
          <button className="modal-close-btn" onClick={onClose}><IconX size={18} /></button>
        </div>
        <div className="modal-form">
          <p style={{ margin: 0, color: 'var(--text-2)', lineHeight: 1.6 }}>{body}</p>
        </div>
        <div className="modal-buttons">
          <button className="btn-secondary" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className={danger ? 'btn-primary btn-warning-bg' : 'btn-primary'}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Payment History modal ─────────────────────────────────────────────────────

function PaymentHistoryModal({
  po,
  onClose,
}: {
  po: PurchaseOrderOut;
  onClose: () => void;
}) {
  const [history, setHistory] = useState<POPaymentHistoryOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    purchaseApi.getPaymentHistory(po.id)
      .then((r) => setHistory(r.data))
      .catch((e) => setErr(getErrorMessage(e)))
      .finally(() => setLoading(false));
  }, [po.id]);

  function fmt(v: string | number) {
    return parseFloat(String(v)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  const METHOD_LABEL: Record<string, string> = {
    cash: 'Cash',
    bank_transfer: 'Bank Transfer',
    upi: 'UPI',
    cheque: 'Cheque',
    other: 'Other',
  };

  return (
    <div className="modal-overlay">
      <div
        className="modal-box"
        style={{ maxWidth: 780, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="modal-header">
          <div>
            <p className="modal-subtitle">{po.supplier_name}</p>
            <h3 className="modal-title" style={{ margin: 0 }}>
              Payment History — {po.po_number}
            </h3>
          </div>
          <button className="modal-close-btn" onClick={onClose}><IconX size={18} /></button>
        </div>

        {loading && (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted)' }}>Loading…</div>
        )}
        {err && <div className="page-error" style={{ margin: '16px' }}>{err}</div>}

        {history && (
          <div style={{ padding: '0 2px' }}>
            {/* Summary bar */}
            <div
              style={{
                display: 'flex',
                gap: 0,
                marginBottom: 16,
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                overflow: 'hidden',
              }}
            >
              {[
                { label: 'PO Total', val: history.grand_total, color: 'var(--text)' },
                { label: 'Total Paid', val: history.total_paid, color: 'var(--ok)' },
                { label: 'Outstanding', val: history.outstanding, color: parseFloat(history.outstanding) > 0 ? '#d97706' : 'var(--ok)' },
              ].map((col, i) => (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    textAlign: 'center',
                    padding: '12px 8px',
                    borderRight: i < 2 ? '1px solid var(--border)' : undefined,
                    background: 'var(--surface-2)',
                  }}
                >
                  <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    {col.label}
                  </div>
                  <div style={{ fontWeight: 800, fontSize: 16, color: col.color }}>₹{fmt(col.val)}</div>
                </div>
              ))}
              {/* Payment status + invoice ref */}
              <div style={{ flex: 1, textAlign: 'center', padding: '12px 8px', background: 'var(--surface-2)' }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                  Invoice
                </div>
                {history.invoice_number ? (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--brand)' }}>
                    {history.invoice_number}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>—</div>
                )}
              </div>
            </div>

            {/* Entries */}
            {history.entries.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '40px 20px',
                  color: 'var(--muted)',
                  fontSize: 14,
                  border: '1px dashed var(--border)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                <div style={{ fontSize: 32, marginBottom: 8 }}>💳</div>
                No payments recorded for this purchase order yet.
              </div>
            ) : (
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 32 }}>#</th>
                      <th>Date</th>
                      <th>Method</th>
                      <th>Reference</th>
                      <th className="num">Amount Paid</th>
                      <th className="num">Cumulative Paid</th>
                      <th className="num">Balance After</th>
                      <th>Recorded By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.entries.map((e, idx) => (
                      <tr
                        key={e.payment_id}
                        style={{
                          opacity: e.is_voided ? 0.45 : 1,
                          background: e.is_voided ? 'var(--surface-3)' : undefined,
                        }}
                      >
                        <td style={{ color: 'var(--muted)', fontSize: 12 }}>{idx + 1}</td>
                        <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {new Date(e.payment_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </td>
                        <td>
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '1px 8px',
                              borderRadius: 999,
                              fontSize: 11,
                              fontWeight: 700,
                              background: 'var(--info-bg)',
                              color: 'var(--info-text)',
                            }}
                          >
                            {METHOD_LABEL[e.payment_method] ?? e.payment_method}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                          {e.reference_number || <span style={{ color: 'var(--muted)' }}>—</span>}
                        </td>
                        <td className="num" style={{ fontWeight: 700, color: e.is_voided ? 'var(--muted)' : 'var(--ok)' }}>
                          {e.is_voided && (
                            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--danger)', marginRight: 4, verticalAlign: 'middle', padding: '1px 5px', borderRadius: 3, background: 'var(--danger-bg)' }}>
                              VOID
                            </span>
                          )}
                          ₹{fmt(e.allocated_amount)}
                        </td>
                        <td className="num" style={{ fontWeight: 700 }}>
                          ₹{fmt(e.running_total_paid)}
                        </td>
                        <td
                          className="num"
                          style={{
                            fontWeight: 700,
                            color: parseFloat(e.balance_after) <= 0.01 ? 'var(--ok)' : '#d97706',
                          }}
                        >
                          ₹{fmt(e.balance_after)}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--text-2)' }}>
                          {e.created_by_name || '—'}
                          {e.notes && (
                            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }} title={e.notes}>
                              {e.notes.length > 30 ? e.notes.slice(0, 30) + '…' : e.notes}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  {history.entries.length > 1 && (
                    <tfoot>
                      <tr className="total-row">
                        <td colSpan={4} className="num" style={{ fontSize: 13, fontWeight: 600 }}>
                          {history.entries.filter(e => !e.is_voided).length} payment(s)
                        </td>
                        <td className="num" style={{ fontWeight: 800, fontSize: 15, color: 'var(--ok)' }}>
                          ₹{fmt(history.total_paid)}
                        </td>
                        <td colSpan={3} />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}
          </div>
        )}

        <div className="modal-buttons">
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

// ── Goods arrived without a PO ────────────────────────────────────────────────

interface DirectLine {
  _id: number;
  product: ProductRow;
  qty: string; rate: string; gst: string; mrp: string; hsn: string; batch: string; expiry: string;
  toShop: boolean; // false = godown (default)
}

/** Line value the same way the server works it out (_calc_line): qty × rate, + GST, each to the paisa. */
function directLineValue(l: DirectLine): number {
  const r2 = (n: number) => Math.round(n * 100) / 100;
  const gross = r2((parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0));
  return gross + r2((gross * (parseFloat(l.gst) || 0)) / 100);
}

/** The supplier's bill, entered once: PO + goods receipt + invoice are made together on the server. */
function DirectPurchaseModal({ suppliers, stores, onClose, onSaved }: {
  suppliers: SupplierOut[];
  stores: StoreOut[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [supplierId, setSupplierId] = useState(0);
  const [storeId, setStoreId] = useState<number | ''>(stores.length === 1 ? stores[0].id : '');
  const [invoiceNo, setInvoiceNo] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(isoDateIst());
  const [dueDate, setDueDate] = useState('');
  const [other, setOther] = useState('');
  const [billTotal, setBillTotal] = useState('');
  const [reason, setReason] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [lines, setLines] = useState<DirectLine[]>([]);
  const [godownOn, setGodownOn] = useState(false);
  const [newProductOpen, setNewProductOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [toReview, setToReview] = useState<number[] | null>(null);

  useEffect(() => { getSettings().then((s) => setGodownOn(s.godown_enabled)).catch(() => {}); }, []);

  function addLine(p: ProductRow) {
    if (lines.some((l) => l.product.id === p.id)) {
      setErr(t('purchases.direct.twice', { name: p.name }));
      return;
    }
    setErr('');
    setLines((cur) => [...cur, {
      _id: Date.now() + Math.random(), product: p, qty: '1',
      rate: p.price != null ? String(p.price) : '', gst: String(p.tax_rate ?? 0),
      mrp: '', hsn: '', batch: '', expiry: '', toShop: false,
    }]);
  }

  function setLine(id: number, patch: Partial<DirectLine>) {
    setLines((cur) => cur.map((l) => (l._id === id ? { ...l, ...patch } : l)));
  }

  const goods = lines.reduce((sum, l) => sum + directLineValue(l), 0);
  const expected = goods + (parseFloat(other) || 0);
  const total = parseFloat(billTotal);
  const differs = Number.isFinite(total) && Math.abs(total - expected) > 1; // server allows ₹1 round-off
  const ready = supplierId > 0 && storeId !== '' && invoiceNo.trim() !== '' && file !== null && lines.length > 0
    && lines.every((l) => parseFloat(l.qty) > 0 && l.rate.trim() !== '')
    && Number.isFinite(total) && total > 0 && (!differs || reason.trim() !== '');

  async function save() {
    // `ready` already checked storeId !== '', so TypeScript knows storeId is a number past this line.
    if (!ready || !file) return;
    setSaving(true);
    setErr('');
    try {
      await purchaseApi.createDirect({
        supplier_id: supplierId, store_id: storeId, invoice_number: invoiceNo.trim(), invoice_date: invoiceDate,
        due_date: dueDate || null, other_charges: parseFloat(other) || 0, grand_total: total,
        difference_reason: differs ? reason.trim() : null,
        items: lines.map((l) => ({
          product_id: l.product.id, qty: parseFloat(l.qty), unit_price: parseFloat(l.rate),
          tax_rate: parseFloat(l.gst) || 0, mrp: l.mrp ? parseFloat(l.mrp) : null,
          hsn_code: l.hsn.trim() || null, batch_number: l.batch.trim() || null,
          expiry_date: l.expiry || null, to_shop: godownOn && l.toShop,
        })),
      }, file);
      // New costs: offer to fix selling prices that no longer give the profit wanted.
      const review = await getPriceReview(lines.map((l) => l.product.id)).catch(() => null);
      if (review && review.items.length > 0) {
        setToReview(review.items.map((r) => r.product_id));
        return;
      }
      onSaved();
    } catch (e) {
      setErr(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  if (toReview) {
    return (
      <div className="modal-overlay">
        <div className="modal-box" style={{ maxWidth: 480 }}>
          <h3>{t('purchases.receivedTitle')}</h3>
          <p>{t('purchases.pricesToReview', { count: toReview.length })}</p>
          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onSaved}>{t('purchases.reviewLater')}</button>
            <button type="button" className="btn-primary"
              onClick={() => navigate(`/admin/price-review?products=${toReview.join(',')}`)}>
              {t('purchases.reviewNow')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const small = { padding: '5px 8px', minHeight: 34, width: 90 } as const;
  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 1100, width: '96%', maxHeight: '92vh', overflowY: 'auto' }}>
        <div className="modal-header">
          <h3 className="modal-title" style={{ margin: 0 }}>{t('purchases.direct.title')}</h3>
          <button className="modal-close-btn" onClick={onClose}><IconX size={18} /></button>
        </div>
        <p className="hint-text">{t('purchases.direct.hint')}</p>
        {err && <div className="page-error">{err}</div>}

        <div className="form-row form-row-3">
          <label className="field-label">{t('purchases.fieldSupplier')}
            <select className="field-input" value={supplierId} onChange={(e) => { setSupplierId(Number(e.target.value)); setLines([]); }}>
              <option value={0}>—</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.company_name}</option>)}
            </select>
          </label>
          <label className="field-label">{t('purchases.fieldStore')}
            <select className="field-input" value={storeId} onChange={(e) => setStoreId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">—</option>
              {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label className="field-label">{t('purchases.direct.billFile')}
            <input className="field-input" type="file" accept="application/pdf,image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
        </div>
        <div className="form-row form-row-3">
          <label className="field-label">{t('purchases.direct.invoiceNo')}
            <input className="field-input" value={invoiceNo} maxLength={100} onChange={(e) => setInvoiceNo(e.target.value)} />
          </label>
          <label className="field-label">{t('purchases.direct.invoiceDate')}
            <input className="field-input" type="date" value={invoiceDate} max={isoDateIst()} onChange={(e) => setInvoiceDate(e.target.value)} />
          </label>
          <label className="field-label">{t('purchases.direct.dueDate')}
            <input className="field-input" type="date" value={dueDate} min={invoiceDate} onChange={(e) => setDueDate(e.target.value)} />
          </label>
        </div>

        <ProductSearch onSelect={addLine} storeId={storeId} supplierId={supplierId || undefined} />
        {supplierId > 0 && (
          <button type="button" className="btn-sm" style={{ marginTop: -8, marginBottom: 12 }} onClick={() => setNewProductOpen(true)}>
            + {t('purchases.newProduct')}
          </button>
        )}
        {newProductOpen && (
          <NewProductModal supplierId={supplierId || undefined} storeId={storeId}
            onClose={() => setNewProductOpen(false)}
            onCreated={(p) => { addLine(p); setNewProductOpen(false); }} />
        )}

        {lines.length > 0 && (
          <div className="table-card" style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('purchases.colProduct')}</th>
                  <th className="num">{t('purchases.receiveQty')}</th>
                  <th className="num">{t('purchases.billRate')}</th>
                  <th className="num">{t('purchases.billGst')}</th>
                  <th className="num">MRP</th>
                  <th>HSN</th>
                  <th>Batch No.</th>
                  <th>{t('purchases.expiryDate')}</th>
                  {godownOn && <th>{t('purchases.direct.location')}</th>}
                  <th className="num">{t('purchases.direct.value')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l._id}>
                    <td><strong>{l.product.name}</strong></td>
                    <td><input className="field-input" type="number" min="0" step="0.001" style={small} value={l.qty} onChange={(e) => setLine(l._id, { qty: e.target.value })} /></td>
                    <td><input className="field-input" type="number" min="0" step="0.01" style={small} value={l.rate} onChange={(e) => setLine(l._id, { rate: e.target.value })} /></td>
                    <td><input className="field-input" type="number" min="0" max="100" step="0.01" style={{ ...small, width: 70 }} value={l.gst} onChange={(e) => setLine(l._id, { gst: e.target.value })} /></td>
                    <td><input className="field-input" type="number" min="0" step="0.01" style={small} value={l.mrp} placeholder="—" onChange={(e) => setLine(l._id, { mrp: e.target.value })} /></td>
                    <td><input className="field-input" inputMode="numeric" maxLength={8} style={small} value={l.hsn} placeholder="—" onChange={(e) => setLine(l._id, { hsn: e.target.value.replace(/\D/g, '') })} /></td>
                    <td><input className="field-input" maxLength={100} style={{ ...small, width: 110 }} value={l.batch} onChange={(e) => setLine(l._id, { batch: e.target.value })} /></td>
                    <td><input className="field-input" type="date" style={{ minHeight: 34 }} value={l.expiry} onChange={(e) => setLine(l._id, { expiry: e.target.value })} /></td>
                    {godownOn && (
                      <td>
                        <select className="field-input" style={{ minHeight: 34 }} value={l.toShop ? 'shop' : 'godown'}
                          onChange={(e) => setLine(l._id, { toShop: e.target.value === 'shop' })}>
                          <option value="godown">{t('purchases.direct.godown')}</option>
                          <option value="shop">{t('purchases.direct.shelf')}</option>
                        </select>
                      </td>
                    )}
                    <td className="num">₹{directLineValue(l).toFixed(2)}</td>
                    <td>
                      <button type="button" className="btn-icon" title={t('purchases.direct.removeLine')}
                        onClick={() => setLines((cur) => cur.filter((x) => x._id !== l._id))}>
                        <IconTrash size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="form-row form-row-3" style={{ marginTop: 12 }}>
          <label className="field-label">{t('purchases.direct.otherCharges')}
            <input className="field-input" type="number" min="0" step="0.01" value={other} placeholder="0" onChange={(e) => setOther(e.target.value)} />
          </label>
          <label className="field-label">{t('purchases.direct.billTotal')}
            <input className="field-input" type="number" min="0" step="0.01" value={billTotal} onChange={(e) => setBillTotal(e.target.value)} />
            <span className="hint-text">{t('purchases.direct.expected', { amount: `₹${expected.toFixed(2)}` })}</span>
          </label>
          {differs && (
            <label className="field-label">{t('purchases.direct.reason')}
              <input className="field-input" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
            </label>
          )}
        </div>

        <div className="modal-buttons">
          <button type="button" className="btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn-primary" disabled={!ready || saving} onClick={save}>
            {saving ? t('common.saving') : t('purchases.direct.save')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function PurchasesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [dash, setDash] = useState<PurchaseDashboard | null>(null);
  const [items, setItems] = useState<PurchaseOrderOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<PurchaseStatus | ''>('');
  const [paymentFilter, setPaymentFilter] = useState<'has_outstanding' | 'has_payments' | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [suppliers, setSuppliers] = useState<SupplierOut[]>([]);
  const [stores, setStores] = useState<StoreOut[]>([]);

  type ModalKind =
    'create' | 'edit' | 'detail' | 'receive' | 'payment-history' | 'place-confirm' | 'cancel-confirm' | 'send' | 'direct' | null;
  const [modal, setModal] = useState<ModalKind>(null);
  const [selected, setSelected] = useState<PurchaseOrderOut | null>(null);
  const [actioning, setActioning] = useState(false);

  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    loadDash();
    loadSuppliers();
    loadStores();
    load(1, '', '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadDash() {
    try {
      const r = await purchaseApi.dashboard();
      setDash(r.data);
    } catch { /* non-critical */ }
  }

  async function loadSuppliers() {
    try {
      const r = await supplierApi.list({ status: 'active', per_page: 100 });
      setSuppliers(r.data.items);
    } catch { /* */ }
  }

  async function loadStores() {
    try {
      const all = await listStores();
      setStores(all.filter((s) => s.is_active));
    } catch { /* */ }
  }

  async function load(
    p = page,
    s = search,
    st = statusFilter,
    pf: 'has_outstanding' | 'has_payments' | null = paymentFilter,
  ) {
    setLoading(true);
    setError('');
    try {
      const r = await purchaseApi.list({
        page: p,
        per_page: PER_PAGE,
        status: st || undefined,
        q: s || undefined,
        payment_filter: pf ?? undefined,
      });
      setItems(r.data.items);
      setTotal(r.data.total);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  function handleSearch(val: string) {
    setSearch(val);
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => { setPage(1); load(1, val, statusFilter, paymentFilter); }, 400);
  }

  function handleStatusChange(val: string) {
    const st = val as PurchaseStatus | '';
    setStatusFilter(st);
    setPage(1);
    load(1, search, st, paymentFilter);
  }

  function handlePaymentFilterClick(filter: 'has_outstanding' | 'has_payments') {
    const newPf = paymentFilter === filter ? null : filter;
    setPaymentFilter(newPf);
    setPage(1);
    load(1, search, statusFilter, newPf);
  }

  function clearAllFilters() {
    setSearch('');
    setStatusFilter('');
    setPaymentFilter(null);
    setPage(1);
    load(1, '', '', null);
  }

  function afterSave(_po: PurchaseOrderOut) {
    setModal(null);
    setSelected(null);
    load(page, search, statusFilter, paymentFilter);
    loadDash();
  }

  async function doPlace() {
    if (!selected) return;
    setActioning(true);
    try {
      const placed = (await purchaseApi.placeOrder(selected.id)).data;
      // Straight on to sending it: shows the automatic email's progress, or the WhatsApp / PDF options.
      setSelected(placed);
      setModal('send');
      load(page, search, statusFilter, paymentFilter);
      loadDash();
    } catch (e) {
      alert(getErrorMessage(e));
    } finally {
      setActioning(false);
    }
  }

  async function doCancel() {
    if (!selected) return;
    setActioning(true);
    try {
      await purchaseApi.cancelOrder(selected.id);
      setModal(null);
      setSelected(null);
      load(page, search, statusFilter, paymentFilter);
      loadDash();
    } catch (e) {
      alert(getErrorMessage(e));
    } finally {
      setActioning(false);
    }
  }

  /** A PO came back from a send / email action: show it in the open box and in the list. */
  function poChanged(po: PurchaseOrderOut) {
    setSelected(po);
    setItems((rows) => rows.map((row) => (row.id === po.id ? po : row)));
  }

  const pages = Math.ceil(total / PER_PAGE);

  return (
    <div className="admin-page">
      <AdminNav />

      {/* Page header */}
      <div className="admin-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconClipboardList size={24} />
          <h2>{t('purchases.title')}</h2>
        </div>
        <div className="admin-actions">
          <button className="btn-secondary" onClick={() => { setSelected(null); setModal('direct'); }}>
            {t('purchases.direct.button')}
          </button>
          <button
            className="btn-primary"
            onClick={() => { setSelected(null); setModal('create'); }}
          >
            <IconPlus size={15} /> {t('purchases.add')}
          </button>
        </div>
      </div>

      {/* Dashboard tiles */}
      {dash && (
        <div className="stat-grid" style={{ marginBottom: 24 }}>
          {/* Every tile filters the list below to the orders behind its number; clicking again shows all. */}
          <StatTile label={t('purchases.cardTotal')} value={dash.total} accent="var(--muted)"
                    onClick={clearAllFilters} isActive={false} />
          <StatTile
            label={t('purchases.cardValue')}
            value={`₹${parseFloat(dash.total_value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
            accent="var(--brand)"
            onClick={clearAllFilters}
            isActive={false}
          />
          {([
            ['cardOrdered', 'ordered', dash.ordered, '#0284c7'],
            ['cardPartial', 'partially_received', dash.partially_received, 'var(--warn)'],
            ['cardReceived', 'received', dash.received, 'var(--ok)'],
            ['cardCancelled', 'cancelled', dash.cancelled, 'var(--danger)'],
          ] as const).map(([label, status, value, accent]) => (
            <StatTile
              key={status}
              label={t(`purchases.${label}`)}
              value={value}
              accent={accent}
              onClick={() => handleStatusChange(statusFilter === status ? '' : status)}
              isActive={statusFilter === status}
            />
          ))}
          <StatTile
            label="Amount Paid"
            value={`₹${parseFloat(dash.total_paid || '0').toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
            accent="#7c3aed"
            onClick={() => handlePaymentFilterClick('has_payments')}
            isActive={paymentFilter === 'has_payments'}
          />
          <StatTile
            label="Purchase Due"
            value={`₹${parseFloat(dash.total_due || '0').toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
            accent="#dc2626"
            onClick={() => handlePaymentFilterClick('has_outstanding')}
            isActive={paymentFilter === 'has_outstanding'}
          />
        </div>
      )}

      {/* Filters */}
      <div className="filter-bar">
        <input
          className="field-input filter-input"
          placeholder={t('purchases.searchPlaceholder')}
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
        />
        <select
          className="field-input"
          style={{ flex: '0 0 180px' }}
          value={statusFilter}
          onChange={(e) => handleStatusChange(e.target.value)}
        >
          <option value="">{t('purchases.filterStatus')}</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{t(`purchases.statuses.${s}` as const)}</option>
          ))}
        </select>
        {paymentFilter && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
            <span
              style={{
                padding: '4px 10px',
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 700,
                background: paymentFilter === 'has_outstanding' ? '#fee2e2' : '#ede9fe',
                color: paymentFilter === 'has_outstanding' ? '#dc2626' : '#7c3aed',
                whiteSpace: 'nowrap',
              }}
            >
              {paymentFilter === 'has_outstanding' ? '● Purchase Due' : '● Amount Paid'}
            </span>
          </div>
        )}
        {(search || statusFilter || paymentFilter) && (
          <button
            className="btn-secondary"
            style={{ flexShrink: 0, fontSize: 12, padding: '6px 12px' }}
            onClick={clearAllFilters}
          >
            Clear Filters
          </button>
        )}
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('purchases.loading')}</div>}

      {/* Table */}
      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('purchases.colPo')}</th>
              <th>{t('purchases.colSupplier')}</th>
              <th>{t('purchases.colDate')}</th>
              <th className="num">{t('purchases.colItems')}</th>
              <th className="num">{t('purchases.colTotal')}</th>
              <th>{t('purchases.colStatus')}</th>
              <th>Payment</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={8} className="empty-row">{t('purchases.emptyAll')}</td>
              </tr>
            )}
            {items.map((po) => (
              <tr
                key={po.id}
                className="clickable-row"
                onClick={() => { setSelected(po); setModal('detail'); }}
              >
                <td>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      fontSize: 13,
                      color: 'var(--brand-600)',
                    }}
                  >
                    {po.po_number}
                  </span>
                  {po.is_direct && (
                    <span className="status-badge badge-info" style={{ marginLeft: 6 }}>{t('purchases.direct.badge')}</span>
                  )}
                </td>
                <td style={{ fontWeight: 600 }}>{po.supplier_name}</td>
                <td className="ts-cell">{formatDate(po.purchase_date)}</td>
                <td className="num">{po.items.length}</td>
                <td className="num" style={{ fontWeight: 700 }}>
                  ₹{parseFloat(po.grand_total).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td>
                  <StatusBadge status={po.status} />
                  <SentBadge po={po} />
                </td>
                <td>
                  <PaymentStatusBadge
                    status={po.payment_status}
                    cancelled={po.status === 'cancelled'}
                  />
                  {po.status !== 'cancelled' && po.payment_status !== 'paid' && parseFloat(po.outstanding_amount || '0') > 0.01 && (
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                      ₹{parseFloat(po.outstanding_amount).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} due
                    </div>
                  )}
                </td>
                <td
                  className="table-actions"
                  onClick={(e) => e.stopPropagation()}
                >
                  {po.status === 'draft' && (
                    <button
                      className="btn-sm"
                      title={t('common.edit')}
                      onClick={() => { setSelected(po); setModal('edit'); }}
                    >
                      <IconEdit size={14} />
                    </button>
                  )}
                  {po.status === 'draft' && (
                    <button
                      className="btn-sm"
                      title={t('purchases.placeOrder')}
                      style={{ marginLeft: 4, color: 'var(--ok)', borderColor: 'var(--ok-border)' }}
                      onClick={() => { setSelected(po); setModal('place-confirm'); }}
                    >
                      <IconCheck size={14} />
                    </button>
                  )}
                  {po.payment_status !== 'unpaid' && (
                    <button
                      className="btn-sm"
                      title="Payment History"
                      style={{ marginLeft: 4, color: '#7c3aed', borderColor: '#c4b5fd' }}
                      onClick={() => { setSelected(po); setModal('payment-history'); }}
                    >
                      <IconHistory size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="pagination">
          <button
            disabled={page <= 1}
            onClick={() => { const p = page - 1; setPage(p); load(p, search, statusFilter, paymentFilter); }}
          >
            {t('common.prev')}
          </button>
          <span>{t('common.pageInfo', { page, total })}</span>
          <button
            disabled={page >= pages}
            onClick={() => { const p = page + 1; setPage(p); load(p, search, statusFilter, paymentFilter); }}
          >
            {t('common.next')}
          </button>
        </div>
      )}

      {/* Modals */}
      {(modal === 'create' || modal === 'edit') && (
        <PoFormModal
          editing={modal === 'edit' ? selected : null}
          suppliers={suppliers}
          stores={stores}
          onClose={() => setModal(null)}
          onSaved={afterSave}
        />
      )}

      {modal === 'detail' && selected && (
        <DetailModal
          key={`detail-${selected.id}`}
          po={selected}
          stores={stores}
          onClose={() => { setModal(null); setSelected(null); }}
          onEdit={() => setModal('edit')}
          onPlace={() => setModal('place-confirm')}
          onCancel={() => setModal('cancel-confirm')}
          onReceive={() => setModal('receive')}
          onSend={() => setModal('send')}
          onOpenInvoices={() => navigate(`/admin/suppliers/${selected.supplier_id}?tab=invoices`)}
        />
      )}

      {modal === 'direct' && (
        <DirectPurchaseModal
          suppliers={suppliers}
          stores={stores}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(page, search, statusFilter, paymentFilter); loadDash(); }}
        />
      )}

      {modal === 'receive' && selected && (
        <ReceiveModal
          po={selected}
          onClose={() => setModal('detail')}
          onSaved={() => {
            setModal(null);
            setSelected(null);
            load(page, search, statusFilter, paymentFilter);
            loadDash();
          }}
        />
      )}

      {modal === 'payment-history' && selected && (
        <PaymentHistoryModal
          po={selected}
          onClose={() => { setModal(null); setSelected(null); }}
        />
      )}

      {modal === 'place-confirm' && selected && (
        <ConfirmModal
          title={t('purchases.placeOrder')}
          body={`${t('purchases.placeConfirm')}\n\n${selected.po_number}`}
          confirmLabel={t('purchases.placeOrder')}
          loading={actioning}
          onConfirm={doPlace}
          onClose={() => setModal(selected ? 'detail' : null)}
        />
      )}

      {modal === 'send' && selected && (
        <SendToSupplierModal
          po={selected}
          onClose={() => setModal('detail')}
          onChanged={poChanged}
        />
      )}

      {modal === 'cancel-confirm' && selected && (
        <ConfirmModal
          title={t('purchases.cancelOrder')}
          body={`${t('purchases.cancelConfirm')}\n\n${selected.po_number}`}
          confirmLabel={t('purchases.cancelOrder')}
          danger
          loading={actioning}
          onConfirm={doCancel}
          onClose={() => setModal(selected ? 'detail' : null)}
        />
      )}
    </div>
  );
}
