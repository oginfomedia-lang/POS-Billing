// Create and update automatic offers: % / ₹ off, buy-X-get-Y and quantity price, for a bill, product or category.
import type { TFunction } from 'i18next';
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { StatusTabs, type StatusView } from '../../components/admin/StatusTabs';
import { getErrorMessage } from '../../services/api/httpClient';
import { listCategories, listProducts } from '../../services/api/productApi';
import { listStores } from '../../services/api/storeApi';
import { listDiscounts, saveDiscount } from '../../services/api/reportApi';
import type { StoreOut } from '../../types/api';
import type { CategoryOut, ProductOut } from '../../types/product';
import type { DiscountIn, DiscountOut, DiscountScope, DiscountType } from '../../types/report';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';
import { useCanSwitchStore, useStoreContext } from '../../store/storeContext';

interface DiscountForm {
  name: string;
  discount_type: DiscountType;
  value: string;
  scope: DiscountScope;
  product_id: string;
  /** Display only: name of the chosen product. Not sent to the server. */
  product_name: string;
  category_id: string;
  store_id: string;
  min_bill_amount: string;
  max_discount_amount: string;
  buy_qty: string;
  get_qty: string;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
}

const EMPTY: DiscountForm = {
  name: '',
  discount_type: 'percentage',
  value: '',
  scope: 'bill',
  product_id: '',
  product_name: '',
  category_id: '',
  store_id: '',
  min_bill_amount: '',
  max_discount_amount: '',
  buy_qty: '',
  get_qty: '',
  starts_at: '',
  ends_at: '',
  is_active: true,
};

/** Offer types that work per item only, never on the whole bill. */
const ITEM_ONLY_TYPES: DiscountType[] = ['buy_x_get_y', 'qty_price'];

type OfferStatus = 'running' | 'scheduled' | 'expired' | 'paused';

/** Same rules the server uses when picking offers (discount_repository.active_for_store). */
function offerStatus(d: DiscountOut, now = Date.now()): OfferStatus {
  if (!d.is_active) return 'paused';
  if (d.ends_at && new Date(d.ends_at).getTime() <= now) return 'expired';
  if (d.starts_at && new Date(d.starts_at).getTime() > now) return 'scheduled';
  return 'running';
}

/** Short human description of what the offer gives, for the table. */
function offerValueLabel(d: DiscountOut, t: TFunction): string {
  switch (d.discount_type) {
    case 'percentage':
      return d.max_discount_amount
        ? t('discounts.valuePctMax', { value: Number(d.value), max: formatRupees(d.max_discount_amount) })
        : t('discounts.valuePct', { value: Number(d.value) });
    case 'fixed':
      return t(d.scope === 'bill' ? 'discounts.valueFixed' : 'discounts.valueFixedEach', { amount: formatRupees(d.value) });
    case 'buy_x_get_y':
      return t('discounts.valueBxgy', { buy: d.buy_qty, get: d.get_qty });
    case 'qty_price':
      return t('discounts.valueQtyPrice', { qty: d.buy_qty, amount: formatRupees(d.value) });
  }
}

function toLocalInput(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function fromLocalInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

function fromDiscount(discount: DiscountOut): DiscountForm {
  return {
    name: discount.name,
    discount_type: discount.discount_type,
    value: discount.value,
    scope: discount.scope,
    product_id: discount.product_id === null ? '' : String(discount.product_id),
    product_name: discount.product_name ?? '',
    category_id: discount.category_id === null ? '' : String(discount.category_id),
    store_id: discount.store_id === null ? '' : String(discount.store_id),
    min_bill_amount: discount.min_bill_amount ?? '',
    max_discount_amount: discount.max_discount_amount ?? '',
    buy_qty: discount.buy_qty === null ? '' : String(discount.buy_qty),
    get_qty: discount.get_qty === null ? '' : String(discount.get_qty),
    starts_at: toLocalInput(discount.starts_at),
    ends_at: toLocalInput(discount.ends_at),
    is_active: discount.is_active,
  };
}

function toDiscount(form: DiscountForm): DiscountIn {
  return {
    name: form.name.trim(),
    discount_type: form.discount_type,
    value: form.discount_type === 'buy_x_get_y' ? '0' : form.value,
    scope: form.scope,
    product_id: form.scope === 'product' && form.product_id ? Number(form.product_id) : null,
    category_id: form.scope === 'category' && form.category_id ? Number(form.category_id) : null,
    store_id: form.store_id ? Number(form.store_id) : null,
    min_bill_amount: form.scope === 'bill' && form.min_bill_amount ? form.min_bill_amount : null,
    max_discount_amount: form.discount_type === 'percentage' && form.max_discount_amount ? form.max_discount_amount : null,
    buy_qty: ITEM_ONLY_TYPES.includes(form.discount_type) && form.buy_qty ? Number(form.buy_qty) : null,
    get_qty: form.discount_type === 'buy_x_get_y' && form.get_qty ? Number(form.get_qty) : null,
    starts_at: fromLocalInput(form.starts_at),
    ends_at: fromLocalInput(form.ends_at),
    is_active: form.is_active,
  };
}

export function DiscountsPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const [discounts, setDiscounts] = useState<DiscountOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [stores, setStores] = useState<StoreOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<DiscountForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [productResults, setProductResults] = useState<ProductOut[]>([]);
  // Running/scheduled offers on one tab; paused and expired ones on the other.
  const [view, setView] = useState<StatusView>('active');

  // Branch picked in the sidebar: its own offers plus the all-branch ones. Head office only can make all-branch offers.
  const branchId = useStoreContext((s) => s.selectedId);
  const isHeadOffice = useCanSwitchStore();

  async function reloadDiscounts() {
    setDiscounts(await listDiscounts(branchId));
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([listDiscounts(branchId), listCategories(), listStores()])
      .then(([ds, cs, ss]) => {
        if (!cancelled) {
          setDiscounts(ds);
          setCategories(cs);
          setStores(ss);
        }
      })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [branchId]);

  // Auto-open create modal when navigated from Expiry Alerts with ?product_id=...
  useEffect(() => {
    if (loading) return;
    const params = new URLSearchParams(location.search);
    const pid = params.get('product_id');
    if (!pid) return;
    const endsAt = params.get('ends_at') ?? '';
    const productName = params.get('product_name') ?? '';
    setEditingId(null);
    setForm({
      ...EMPTY,
      scope: 'product',
      product_id: pid,
      name: productName ? `Expiry offer – ${productName}` : '',
      ends_at: endsAt ? `${endsAt}T23:59` : '',
    });
    setError('');
    setModal(true);
  }, [loading, location.search]);
  // Search products as you type (debounced), instead of loading only the first 100.
  useEffect(() => {
    const q = productSearch.trim();
    if (!q) { setProductResults([]); return; }
    const t = window.setTimeout(() => {
      listProducts({ q, per_page: 10, active_only: true })
        .then((r) => setProductResults(r.items))
        .catch((err) => setError(getErrorMessage(err)));
    }, 250);
    return () => window.clearTimeout(t);
  }, [productSearch]);

  useEffect(() => {
    if (loading) return;
    const params = new URLSearchParams(location.search);
    const pid = params.get('product_id');
    if (!pid) return;
    const endsAt = params.get('ends_at') ?? '';
    const productName = params.get('product_name') ?? '';
    setEditingId(null);
    setForm({
      ...EMPTY,
      scope: 'product',
      product_id: pid,
      name: productName ? `Expiry offer – ${productName}` : '',
      ends_at: endsAt ? `${endsAt}T23:59` : '',
    });
    setError('');
    setModal(true);
  }, [loading, location.search]);

  function openCreate() {
    setEditingId(null);
    setForm({ ...EMPTY, store_id: branchId === null ? '' : String(branchId) });
    setProductSearch('');
    setError('');
    setModal(true);
  }

  function openEdit(discount: DiscountOut) {
    setEditingId(discount.id);
    setForm(fromDiscount(discount));
    setProductSearch('');
    setError('');
    setModal(true);
  }

  function update<K extends keyof DiscountForm>(key: K, value: DiscountForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  /** Changing to "Whole bill" drops item-only types back to Percentage. */
  function changeScope(scope: DiscountScope) {
    setForm((f) => ({
      ...f,
      scope,
      discount_type: scope === 'bill' && ITEM_ONLY_TYPES.includes(f.discount_type) ? 'percentage' : f.discount_type,
    }));
  }

  function chooseProduct(p: ProductOut) {
    setForm((f) => ({ ...f, product_id: String(p.id), product_name: p.name }));
    setProductSearch('');
    setProductResults([]);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (form.scope === 'product' && !form.product_id) {
      setError(t('discounts.chooseProduct'));
      return;
    }
    setSaving(true);
    setError('');
    try {
      await saveDiscount(editingId, toDiscount(form));
      await reloadDiscounts();
      setModal(false);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const isLive = (d: DiscountOut) => ['running', 'scheduled'].includes(offerStatus(d));
  const visibleDiscounts = discounts.filter((d) => isLive(d) === (view === 'active'));
  const offerCounts = { active: discounts.filter(isLive).length, inactive: discounts.filter((d) => !isLive(d)).length };

  function targetLabel(discount: DiscountOut): string {
    if (discount.scope === 'product') return discount.product_name ?? t('discounts.productN', { id: discount.product_id });
    if (discount.scope === 'category') return discount.category_name ?? t('discounts.categoryN', { id: discount.category_id });
    return discount.min_bill_amount
      ? t('discounts.billsMin', { amount: formatRupees(discount.min_bill_amount) })
      : t('discounts.anyBill');
  }

  return (
    <div className="admin-page discounts-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('discounts.title')}</h2>
        <button className="btn-primary" onClick={openCreate}>{t('discounts.add')}</button>
      </div>
      {error && !modal && <div className="page-error">{error}</div>}
      <StatusTabs value={view} onChange={setView} counts={offerCounts} inactiveLabel={t('discounts.pausedExpired')} />
      {loading && <div className="loading-text">{t('discounts.loading')}</div>}
      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr><th>{t('common.name')}</th><th>{t('discounts.colAppliesTo')}</th><th>{t('discounts.colTarget')}</th><th>{t('common.store')}</th><th>{t('discounts.colDiscount')}</th><th>{t('discounts.colSchedule')}</th><th>{t('discounts.colStatus')}</th><th /></tr>
          </thead>
          <tbody>
            {!loading && visibleDiscounts.length === 0 && (
              <tr>
                <td colSpan={8} className="empty-row">
                  {view === 'active' ? t('discounts.emptyActive') : t('discounts.emptyInactive')}
                </td>
              </tr>
            )}
            {visibleDiscounts.map((d) => {
              const status = offerStatus(d);
              return (
                <tr key={d.id}>
                  <td>{d.name}</td>
                  <td>{t(`discounts.scopes.${d.scope}`)}</td>
                  <td>{targetLabel(d)}</td>
                  <td>{stores.find((s) => s.id === d.store_id)?.name ?? t('common.allStores')}</td>
                  <td>{offerValueLabel(d, t)}</td>
                  <td className="ts-cell">
                    {d.starts_at ? formatDateTime(d.starts_at) : t('discounts.now')}
                    {' – '}
                    {d.ends_at ? formatDateTime(d.ends_at) : t('discounts.noEnd')}
                  </td>
                  <td><span className={`stock-badge offer-status-${status}`}>{t(`discounts.statuses.${status}`)}</span></td>
                  <td>
                    <button
                      className="btn-sm"
                      onClick={() => openEdit(d)}
                      disabled={!isHeadOffice && d.store_id === null}
                      title={!isHeadOffice && d.store_id === null ? t('discounts.hqOnly') : undefined}
                    >
                      {t('common.edit')}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="hint-text">{t('discounts.hint')}</p>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal-box modal-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingId === null ? t('discounts.addTitle') : t('discounts.editTitle')}</h3>
            {error && <div className="form-error">{error}</div>}
            <form onSubmit={submit} className="modal-form">
              <label className="field-label">
                {t('common.name')}
                <input className="field-input" maxLength={100} value={form.name} onChange={(e) => update('name', e.target.value)} required />
              </label>

              <div className="form-row">
                <label className="field-label">
                  {t('discounts.appliesTo')}
                  <select className="field-input" value={form.scope} onChange={(e) => changeScope(e.target.value as DiscountScope)}>
                    <option value="bill">{t('discounts.scopes.bill')}</option>
                    <option value="product">{t('discounts.scopes.product')}</option>
                    <option value="category">{t('discounts.scopes.category')}</option>
                  </select>
                </label>
                <label className="field-label">
                  {t('common.store')}
                  <select className="field-input" value={form.store_id} onChange={(e) => update('store_id', e.target.value)}>
                    {isHeadOffice && <option value="">{t('common.allStores')}</option>}
                    {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                  </select>
                </label>
              </div>

              <label className="field-label">
                {t('discounts.offerType')}
                <select className="field-input" value={form.discount_type} onChange={(e) => update('discount_type', e.target.value as DiscountType)}>
                  <option value="percentage">{t('discounts.types.percentage')}</option>
                  <option value="fixed">{t('discounts.types.fixed')}</option>
                  {form.scope !== 'bill' && <option value="buy_x_get_y">{t('discounts.types.buy_x_get_y')}</option>}
                  {form.scope !== 'bill' && <option value="qty_price">{t('discounts.types.qty_price')}</option>}
                </select>
              </label>

              <div className="form-row">
                {form.discount_type === 'percentage' && (
                  <>
                    <label className="field-label">
                      {t('discounts.percentage')}
                      <input className="field-input" type="number" min="0.01" max="100" step="0.01" value={form.value} onChange={(e) => update('value', e.target.value)} required />
                    </label>
                    <label className="field-label">
                      {t('discounts.maxDiscount')}
                      <input className="field-input" type="number" min="0.01" step="0.01" placeholder={t('discounts.noLimit')} value={form.max_discount_amount} onChange={(e) => update('max_discount_amount', e.target.value)} />
                    </label>
                  </>
                )}
                {form.discount_type === 'fixed' && (
                  <label className="field-label">
                    {form.scope === 'bill' ? t('discounts.amountBill') : t('discounts.amountUnit')}
                    <input className="field-input" type="number" min="0.01" step="0.01" value={form.value} onChange={(e) => update('value', e.target.value)} required />
                  </label>
                )}
                {form.discount_type === 'buy_x_get_y' && (
                  <>
                    <label className="field-label">
                      {t('discounts.buys')}
                      <input className="field-input" type="number" min="1" step="1" value={form.buy_qty} onChange={(e) => update('buy_qty', e.target.value)} required />
                    </label>
                    <label className="field-label">
                      {t('discounts.getsFree')}
                      <input className="field-input" type="number" min="1" step="1" value={form.get_qty} onChange={(e) => update('get_qty', e.target.value)} required />
                    </label>
                  </>
                )}
                {form.discount_type === 'qty_price' && (
                  <>
                    <label className="field-label">
                      {t('discounts.bundleSize')}
                      <input className="field-input" type="number" min="2" step="1" value={form.buy_qty} onChange={(e) => update('buy_qty', e.target.value)} required />
                    </label>
                    <label className="field-label">
                      {t('discounts.bundlePrice')}
                      <input className="field-input" type="number" min="0.01" step="0.01" value={form.value} onChange={(e) => update('value', e.target.value)} required />
                    </label>
                  </>
                )}
              </div>
              {form.discount_type === 'buy_x_get_y' && form.buy_qty && form.get_qty && (
                <p className="hint-text">
                  {t('discounts.bxgyHint', {
                    pct: Math.round((Number(form.get_qty) / (Number(form.buy_qty) + Number(form.get_qty))) * 100),
                    total: Number(form.buy_qty) + Number(form.get_qty),
                    buy: form.buy_qty,
                  })}
                </p>
              )}

              {form.scope === 'product' && (
                <label className="field-label">
                  {t('discounts.product')}
                  <div className="product-picker">
                    <input
                      className="field-input"
                      placeholder={form.product_name || t('discounts.productSearch')}
                      value={productSearch}
                      onChange={(e) => setProductSearch(e.target.value)}
                    />
                    {productResults.length > 0 && (
                      <ul className="picker-results">
                        {productResults.map((p) => (
                          <li key={p.id}>
                            <button type="button" onClick={() => chooseProduct(p)}>
                              {p.name} <span className="status-muted">{p.sku}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {form.product_name && <span className="hint-text">{t('discounts.selected')} <strong>{form.product_name}</strong></span>}
                </label>
              )}
              {form.scope === 'category' && (
                <label className="field-label">
                  {t('discounts.category')}
                  <select className="field-input" value={form.category_id} onChange={(e) => update('category_id', e.target.value)} required>
                    <option value="">{t('discounts.chooseCategory')}</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                  <span className="hint-text">{t('discounts.subcategories')}</span>
                </label>
              )}
              {form.scope === 'bill' && (
                <label className="field-label">
                  {t('discounts.minBill')}
                  <input className="field-input" type="number" min="0" step="0.01" value={form.min_bill_amount} onChange={(e) => update('min_bill_amount', e.target.value)} />
                </label>
              )}

              <div className="form-row">
                <label className="field-label">
                  {t('discounts.startsAt')}
                  <input className="field-input" type="datetime-local" value={form.starts_at} onChange={(e) => update('starts_at', e.target.value)} />
                </label>
                <label className="field-label">
                  {t('discounts.endsAt')}
                  <input className="field-input" type="datetime-local" value={form.ends_at} onChange={(e) => update('ends_at', e.target.value)} />
                </label>
              </div>
              <label className="field-label checkbox-label">
                <input type="checkbox" checked={form.is_active} onChange={(e) => update('is_active', e.target.checked)} />
                {t('common.active')}
              </label>
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(false)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? t('common.saving') : t('discounts.saveBtn')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
