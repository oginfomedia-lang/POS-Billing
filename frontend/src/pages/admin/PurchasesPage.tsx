// Purchase Orders management page — admin and manager.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import {
  IconCheck,
  IconClipboardList,
  IconEdit,
  IconPlus,
  IconTrash,
  IconX,
} from '../../components/common/Icons';
import { getErrorMessage } from '../../services/api/httpClient';
import { purchaseApi } from '../../services/api/purchaseApi';
import type {
  GoodsReceiptItemPayload,
  PurchaseOrderCreatePayload,
  PurchaseOrderItemPayload,
  PurchaseOrderUpdatePayload,
} from '../../services/api/purchaseApi';
import { supplierApi } from '../../services/api/supplierApi';
import { listStores } from '../../services/api/storeApi';
import { listProducts } from '../../services/api/productApi';
import type {
  GoodsReceiptOut,
  PurchaseDashboard,
  PurchaseOrderItemOut,
  PurchaseOrderOut,
  PurchaseStatus,
  SupplierOut,
  StoreOut,
} from '../../types/api';
import { formatDate } from '../../utils/format';

const PER_PAGE = 20;

const STATUS_OPTIONS: PurchaseStatus[] = [
  'draft', 'ordered', 'partially_received', 'received', 'cancelled',
];

// Colour tokens per status — uses CSS vars so dark-mode adapts
const STATUS_ACCENT: Record<PurchaseStatus, string> = {
  draft:              'var(--muted)',
  ordered:            '#0284c7',
  partially_received: '#d97706',
  received:           'var(--ok)',
  cancelled:          'var(--danger)',
};

const STATUS_BG: Record<PurchaseStatus, string> = {
  draft:              'var(--surface-3)',
  ordered:            'var(--info-bg)',
  partially_received: 'var(--warn-bg)',
  received:           'var(--ok-bg)',
  cancelled:          'var(--danger-bg)',
};

const STATUS_FG: Record<PurchaseStatus, string> = {
  draft:              'var(--muted)',
  ordered:            'var(--info-text)',
  partially_received: 'var(--warn-text)',
  received:           'var(--ok-text)',
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
}: {
  label: string;
  value: string | number;
  accent: string;
  sub?: string;
}) {
  return (
    <div
      className="stat-tile"
      style={{ '--accent': accent } as React.CSSProperties}
    >
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
      <div className="stat-label">{label}</div>
    </div>
  );
}

// ── Product search dropdown ───────────────────────────────────────────────────

interface ProductRow {
  id: number;
  name: string;
  sku: string | null;
  price: number;
  tax_rate: number;
}

/** Matches shown in the picker; type more of the name / SKU / barcode to narrow it down. */
const PICKER_LIMIT = 20;
const SEARCH_DELAY_MS = 300;

/**
 * Product picker for PO lines. Searches on the server (name, SKU or exact barcode), so every product can
 * be found however big the catalogue is. With an empty box it shows the first few products.
 */
function ProductSearch({
  onSelect,
  storeId,
}: {
  onSelect: (p: ProductRow) => void;
  storeId?: number | '';
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<ProductRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const sid = typeof storeId === 'number' && storeId > 0 ? storeId : undefined;
    const timer = window.setTimeout(() => {
      setLoading(true);
      listProducts({ q: q.trim() || undefined, per_page: PICKER_LIMIT, active_only: true, store_id: sid })
        .then((data) => {
          if (cancelled) return;
          setResults((data.items || []).map((p) => ({
            id: p.id,
            name: p.name,
            sku: p.sku,
            price: parseFloat(p.store_price ?? p.price ?? '0'),
            tax_rate: parseFloat(p.tax_rate ?? '0'),
          })));
        })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, q.trim() ? SEARCH_DELAY_MS : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [q, open, storeId]);

  function pick(p: ProductRow) {
    onSelect(p);
    setQ('');
    setOpen(false);
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ position: 'relative', maxWidth: 560 }}>
        <label className="field-label" style={{ marginBottom: 4, display: 'block', fontSize: 12 }}>
          {t('purchases.productSearch', 'Search product name or SKU')}
        </label>
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
                {t('purchases.noProductMatch', 'No product found')}
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
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-2)', marginLeft: 12, flexShrink: 0 }}>
                  ₹{p.price.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
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
  const today = new Date().toISOString().slice(0, 10);

  const [supplierId, setSupplierId] = useState(editing?.supplier_id ?? 0);
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
        unit_price: p.price,
        discount_percent: 0,
        tax_rate: p.tax_rate,
      },
    ]);
  }

  function updateLine(id: number, field: string, value: number) {
    setLines((prev) =>
      prev.map((l) => l._id !== id ? l : { ...l, [field]: value }),
    );
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
    if (!supplierId) { setErr(t('purchases.fieldSupplier') + ' is required'); return; }
    if (lines.length === 0) { setErr(t('purchases.noItems')); return; }
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
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-box"
        style={{ maxWidth: 900, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
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
                  onChange={(e) => setSupplierId(Number(e.target.value))}
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
                  onChange={(e) => setPurchaseDate(e.target.value)}
                />
              </label>
              <label className="field-label">
                {t('purchases.fieldExpected')}
                <input
                  className="field-input"
                  type="date"
                  value={expectedDate}
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
            <ProductSearch onSelect={addLine} storeId={storeId} />

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
                              value={l.unit_price}
                              onChange={(e) => updateLine(l._id, 'unit_price', parseFloat(e.target.value) || 0)}
                              style={{ padding: '5px 8px', minHeight: 32 }}
                            />
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
}: {
  po: PurchaseOrderOut;
  stores: StoreOut[];
  onClose: () => void;
  onPlace: () => void;
  onCancel: () => void;
  onReceive: () => void;
  onEdit: () => void;
}) {
  const { t } = useTranslation();
  const [receipts, setReceipts] = useState<GoodsReceiptOut[] | null>(null);
  const [showReceipts, setShowReceipts] = useState(false);

  const canPlace = po.status === 'draft';
  const canCancel = po.status === 'draft' || po.status === 'ordered';
  const canReceive = po.status === 'ordered' || po.status === 'partially_received';
  const canEdit = po.status === 'draft';

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
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-box"
        style={{ maxWidth: 820, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
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
                        {ri.product_name}: {ri.qty_received}
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
  const today = new Date().toISOString().slice(0, 16);
  const [receivedAt, setReceivedAt] = useState(today);
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<{ item: PurchaseOrderItemOut; qty: string; expiry: string }[]>(
    () =>
      po.items
        .filter((i) => parseFloat(i.received_qty) < parseFloat(i.ordered_qty))
        .map((i) => ({
          item: i,
          qty: (parseFloat(i.ordered_qty) - parseFloat(i.received_qty)).toFixed(3),
          expiry: '',
        })),
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  async function submit() {
    const items: GoodsReceiptItemPayload[] = lines
      .filter((l) => parseFloat(l.qty) > 0)
      .map((l) => ({
        purchase_order_item_id: l.item.id,
        qty_received: parseFloat(l.qty),
        expiry_date: l.expiry || null,
      }));
    if (items.length === 0) { setErr('No items to receive.'); return; }
    setSaving(true);
    setErr('');
    try {
      await purchaseApi.receiveGoods(po.id, {
        received_at: receivedAt || null,
        notes: notes || null,
        items,
      });
      onSaved();
    } catch (e) {
      setErr(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-box"
        style={{ maxWidth: 680, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <p className="modal-subtitle">{po.po_number}</p>
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

          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('purchases.colProduct')}</th>
                  <th className="num">{t('purchases.receiveQty')}</th>
                  <th>{t('purchases.expiryDate')}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l, idx) => {
                  const outstanding = parseFloat(l.item.ordered_qty) - parseFloat(l.item.received_qty);
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
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((x, i) => i === idx ? { ...x, qty: e.target.value } : x)
                            )
                          }
                          style={{ padding: '5px 8px', minHeight: 34, width: 100 }}
                        />
                      </td>
                      <td>
                        <input
                          className="field-input"
                          type="date"
                          value={l.expiry}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((x, i) => i === idx ? { ...x, expiry: e.target.value } : x)
                            )
                          }
                          style={{ minHeight: 34 }}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
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

// ── Main page ─────────────────────────────────────────────────────────────────

export function PurchasesPage() {
  const { t } = useTranslation();

  const [dash, setDash] = useState<PurchaseDashboard | null>(null);
  const [items, setItems] = useState<PurchaseOrderOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<PurchaseStatus | ''>('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [suppliers, setSuppliers] = useState<SupplierOut[]>([]);
  const [stores, setStores] = useState<StoreOut[]>([]);

  type ModalKind = 'create' | 'edit' | 'detail' | 'receive' | 'place-confirm' | 'cancel-confirm' | null;
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

  async function load(p = page, s = search, st = statusFilter) {
    setLoading(true);
    setError('');
    try {
      const r = await purchaseApi.list({
        page: p,
        per_page: PER_PAGE,
        status: st || undefined,
        q: s || undefined,
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
    searchTimeout.current = setTimeout(() => { setPage(1); load(1, val, statusFilter); }, 400);
  }

  function handleStatusChange(val: string) {
    const st = val as PurchaseStatus | '';
    setStatusFilter(st);
    setPage(1);
    load(1, search, st);
  }

  function afterSave(_po: PurchaseOrderOut) {
    setModal(null);
    setSelected(null);
    load(page, search, statusFilter);
    loadDash();
  }

  async function doPlace() {
    if (!selected) return;
    setActioning(true);
    try {
      await purchaseApi.placeOrder(selected.id);
      setModal(null);
      setSelected(null);
      load(page, search, statusFilter);
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
      load(page, search, statusFilter);
      loadDash();
    } catch (e) {
      alert(getErrorMessage(e));
    } finally {
      setActioning(false);
    }
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
          <StatTile label={t('purchases.cardTotal')}    value={dash.total}                accent="var(--muted)" />
          <StatTile
            label={t('purchases.cardValue')}
            value={`₹${parseFloat(dash.total_value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
            accent="var(--brand)"
          />
          <StatTile label={t('purchases.cardOrdered')}  value={dash.ordered}              accent="#0284c7" />
          <StatTile label={t('purchases.cardPartial')}  value={dash.partially_received}   accent="var(--warn)" />
          <StatTile label={t('purchases.cardReceived')} value={dash.received}             accent="var(--ok)" />
          <StatTile label={t('purchases.cardCancelled')} value={dash.cancelled}           accent="var(--danger)" />
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
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="empty-row">{t('purchases.emptyAll')}</td>
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
                </td>
                <td style={{ fontWeight: 600 }}>{po.supplier_name}</td>
                <td className="ts-cell">{formatDate(po.purchase_date)}</td>
                <td className="num">{po.items.length}</td>
                <td className="num" style={{ fontWeight: 700 }}>
                  ₹{parseFloat(po.grand_total).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td><StatusBadge status={po.status} /></td>
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
            onClick={() => { const p = page - 1; setPage(p); load(p, search, statusFilter); }}
          >
            {t('common.prev')}
          </button>
          <span>{t('common.pageInfo', { page, total })}</span>
          <button
            disabled={page >= pages}
            onClick={() => { const p = page + 1; setPage(p); load(p, search, statusFilter); }}
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
          po={selected}
          stores={stores}
          onClose={() => { setModal(null); setSelected(null); }}
          onEdit={() => setModal('edit')}
          onPlace={() => setModal('place-confirm')}
          onCancel={() => setModal('cancel-confirm')}
          onReceive={() => setModal('receive')}
        />
      )}

      {modal === 'receive' && selected && (
        <ReceiveModal
          po={selected}
          onClose={() => setModal('detail')}
          onSaved={() => {
            setModal(null);
            setSelected(null);
            load(page, search, statusFilter);
            loadDash();
          }}
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
