// Create and update automatic bill, product, and category discounts.
import { type FormEvent, useEffect, useState } from 'react';
import { AdminNav } from '../../components/admin/AdminNav';
import { getErrorMessage } from '../../services/api/httpClient';
import { listCategories, listProducts } from '../../services/api/productApi';
import { listStores } from '../../services/api/storeApi';
import { listDiscounts, saveDiscount } from '../../services/api/reportApi';
import type { StoreOut } from '../../types/api';
import type { CategoryOut, ProductOut } from '../../types/product';
import type { DiscountIn, DiscountOut, DiscountScope, DiscountType } from '../../types/report';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

interface DiscountForm {
  name: string;
  discount_type: DiscountType;
  value: string;
  scope: DiscountScope;
  product_id: string;
  category_id: string;
  store_id: string;
  min_bill_amount: string;
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
  category_id: '',
  store_id: '',
  min_bill_amount: '',
  starts_at: '',
  ends_at: '',
  is_active: true,
};

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
    category_id: discount.category_id === null ? '' : String(discount.category_id),
    store_id: discount.store_id === null ? '' : String(discount.store_id),
    min_bill_amount: discount.min_bill_amount ?? '',
    starts_at: toLocalInput(discount.starts_at),
    ends_at: toLocalInput(discount.ends_at),
    is_active: discount.is_active,
  };
}

function toDiscount(form: DiscountForm): DiscountIn {
  return {
    name: form.name.trim(),
    discount_type: form.discount_type,
    value: form.value,
    scope: form.scope,
    product_id: form.scope === 'product' && form.product_id ? Number(form.product_id) : null,
    category_id: form.scope === 'category' && form.category_id ? Number(form.category_id) : null,
    store_id: form.store_id ? Number(form.store_id) : null,
    min_bill_amount: form.scope === 'bill' && form.min_bill_amount ? form.min_bill_amount : null,
    starts_at: fromLocalInput(form.starts_at),
    ends_at: fromLocalInput(form.ends_at),
    is_active: form.is_active,
  };
}

export function DiscountsPage() {
  const [discounts, setDiscounts] = useState<DiscountOut[]>([]);
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [stores, setStores] = useState<StoreOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<DiscountForm>(EMPTY);
  const [saving, setSaving] = useState(false);

  async function reloadDiscounts() {
    setDiscounts(await listDiscounts());
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([listDiscounts(), listProducts({ per_page: 100 }), listCategories(), listStores()])
      .then(([ds, ps, cs, ss]) => {
        if (!cancelled) {
          setDiscounts(ds);
          setProducts(ps.items);
          setCategories(cs);
          setStores(ss);
        }
      })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY);
    setError('');
    setModal(true);
  }

  function openEdit(discount: DiscountOut) {
    setEditingId(discount.id);
    setForm(fromDiscount(discount));
    setError('');
    setModal(true);
  }

  function update<K extends keyof DiscountForm>(key: K, value: DiscountForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
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

  function targetLabel(discount: DiscountOut): string {
    if (discount.scope === 'product') {
      return products.find((p) => p.id === discount.product_id)?.name ?? `Product #${discount.product_id}`;
    }
    if (discount.scope === 'category') {
      return categories.find((c) => c.id === discount.category_id)?.name ?? `Category #${discount.category_id}`;
    }
    return discount.min_bill_amount ? `Bills ≥ ${formatRupees(discount.min_bill_amount)}` : 'Any bill';
  }

  return (
    <div className="admin-page discounts-page">
      <AdminNav />
      <div className="admin-header">
        <h2>Discounts</h2>
        <button className="btn-primary" onClick={openCreate}>+ Add Discount</button>
      </div>
      {error && !modal && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading discounts…</div>}
      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Applies to</th><th>Target / minimum</th><th>Store</th><th>Discount</th><th>Schedule</th><th>Status</th><th /></tr>
          </thead>
          <tbody>
            {!loading && discounts.length === 0 && (
              <tr><td colSpan={8} className="empty-row">No discounts configured.</td></tr>
            )}
            {discounts.map((d) => (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td>{d.scope}</td>
                <td>{targetLabel(d)}</td>
                <td>{stores.find((s) => s.id === d.store_id)?.name ?? 'All stores'}</td>
                <td>{d.discount_type === 'percentage' ? `${d.value}%` : formatRupees(d.value)}</td>
                <td className="ts-cell">
                  {d.starts_at ? formatDateTime(d.starts_at) : 'Now'}
                  {' – '}
                  {d.ends_at ? formatDateTime(d.ends_at) : 'No end'}
                </td>
                <td>{d.is_active ? 'Active' : 'Inactive'}</td>
                <td><button className="btn-sm" onClick={() => openEdit(d)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint-text">The best eligible discount is applied automatically when a bill is recalculated; discounts do not stack.</p>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal-box modal-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingId === null ? 'Add Discount' : 'Edit Discount'}</h3>
            {error && <div className="form-error">{error}</div>}
            <form onSubmit={submit} className="modal-form">
              <label className="field-label">
                Name
                <input className="field-input" maxLength={100} value={form.name} onChange={(e) => update('name', e.target.value)} required />
              </label>
              <div className="form-row">
                <label className="field-label">
                  Discount type
                  <select className="field-input" value={form.discount_type} onChange={(e) => update('discount_type', e.target.value as DiscountType)}>
                    <option value="percentage">Percentage</option>
                    <option value="fixed">Fixed amount</option>
                  </select>
                </label>
                <label className="field-label">
                  {form.discount_type === 'percentage' ? 'Percentage (%)' : 'Amount (₹)'}
                  <input className="field-input" type="number" min="0.01" max={form.discount_type === 'percentage' ? 100 : undefined} step="0.01" value={form.value} onChange={(e) => update('value', e.target.value)} required />
                </label>
              </div>
              <div className="form-row">
                <label className="field-label">
                  Applies to
                  <select className="field-input" value={form.scope} onChange={(e) => update('scope', e.target.value as DiscountScope)}>
                    <option value="bill">Whole bill</option>
                    <option value="product">Specific product</option>
                    <option value="category">Category</option>
                  </select>
                </label>
                <label className="field-label">
                  Store
                  <select className="field-input" value={form.store_id} onChange={(e) => update('store_id', e.target.value)}>
                    <option value="">All stores</option>
                    {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                  </select>
                </label>
              </div>
              {form.scope === 'product' && (
                <label className="field-label">
                  Product
                  <select className="field-input" value={form.product_id} onChange={(e) => update('product_id', e.target.value)} required>
                    <option value="">Choose a product</option>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
                  </select>
                </label>
              )}
              {form.scope === 'category' && (
                <label className="field-label">
                  Category
                  <select className="field-input" value={form.category_id} onChange={(e) => update('category_id', e.target.value)} required>
                    <option value="">Choose a category</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </label>
              )}
              {form.scope === 'bill' && (
                <label className="field-label">
                  Minimum bill amount (optional)
                  <input className="field-input" type="number" min="0" step="0.01" value={form.min_bill_amount} onChange={(e) => update('min_bill_amount', e.target.value)} />
                </label>
              )}
              <div className="form-row">
                <label className="field-label">
                  Starts at (optional)
                  <input className="field-input" type="datetime-local" value={form.starts_at} onChange={(e) => update('starts_at', e.target.value)} />
                </label>
                <label className="field-label">
                  Ends at (optional)
                  <input className="field-input" type="datetime-local" value={form.ends_at} onChange={(e) => update('ends_at', e.target.value)} />
                </label>
              </div>
              <label className="field-label checkbox-label">
                <input type="checkbox" checked={form.is_active} onChange={(e) => update('is_active', e.target.checked)} />
                Active
              </label>
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Saving…' : 'Save discount'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
