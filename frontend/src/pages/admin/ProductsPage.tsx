import { useEffect, useState } from 'react';
import { createProduct, listCategories, listProducts, updateProduct } from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { CategoryOut, ProductOut } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';

export function ProductsPage() {
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [target, setTarget] = useState<ProductOut | null>(null);
  const [formName, setFormName] = useState('');
  const [formPrice, setFormPrice] = useState('');
  const [formTax, setFormTax] = useState('0');
  const [formCategory, setFormCategory] = useState('');
  const [formBarcodes, setFormBarcodes] = useState('');
  const [formActive, setFormActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  async function fetchAll(p = page) {
    setLoading(true);
    setError('');
    try {
      const [prod, cats] = await Promise.all([
        listProducts({ page: p, per_page: 25 }),
        listCategories(),
      ]);
      setProducts(prod.items);
      setTotal(prod.total);
      setCategories(cats);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchAll(); }, [page]);

  function openCreate() {
    setModal('create');
    setTarget(null);
    setFormName(''); setFormPrice(''); setFormTax('0');
    setFormCategory(''); setFormBarcodes(''); setFormActive(true); setFormError('');
  }

  function openEdit(p: ProductOut) {
    setModal('edit');
    setTarget(p);
    setFormName(p.name);
    setFormPrice(String(p.price));
    setFormTax(String(p.tax_rate));
    setFormCategory(p.category_id ? String(p.category_id) : '');
    setFormActive(p.is_active);
    setFormError('');
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setFormError('');
    try {
      await createProduct({
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        category_id: formCategory ? parseInt(formCategory) : null,
        barcodes: formBarcodes.split(',').map((b) => b.trim()).filter(Boolean),
      });
      setModal(null);
      fetchAll();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!target) return;
    setSaving(true); setFormError('');
    try {
      await updateProduct(target.id, {
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        category_id: formCategory ? parseInt(formCategory) : null,
        is_active: formActive,
      });
      setModal(null);
      fetchAll();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>Products</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>+ Add Product</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th><th>Price</th><th>Tax %</th><th>Category</th><th>Active</th><th>Barcodes</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {products.map((p) => {
            const cat = categories.find((c) => c.id === p.category_id);
            return (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>₹{Number(p.price).toFixed(2)}</td>
                <td>{Number(p.tax_rate).toFixed(1)}%</td>
                <td>{cat?.name ?? '—'}</td>
                <td>{p.is_active ? '✓' : '—'}</td>
                <td>{p.barcodes.map((b) => b.barcode).join(', ') || '—'}</td>
                <td className="table-actions">
                  <button className="btn-sm" onClick={() => openEdit(p)}>Edit</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
        <span>Page {page} · {total} products</span>
        <button disabled={products.length < 25} onClick={() => setPage(page + 1)}>Next →</button>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3>{modal === 'create' ? 'Add Product' : `Edit ${target?.name}`}</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={modal === 'create' ? handleCreate : handleEdit} className="modal-form">
              <label className="field-label">Name
                <input className="field-input" value={formName} onChange={(e) => setFormName(e.target.value)} required />
              </label>
              <label className="field-label">Price (₹)
                <input className="field-input" type="number" step="0.01" min="0" value={formPrice} onChange={(e) => setFormPrice(e.target.value)} required />
              </label>
              <label className="field-label">Tax Rate (%)
                <input className="field-input" type="number" step="0.01" min="0" max="100" value={formTax} onChange={(e) => setFormTax(e.target.value)} />
              </label>
              <label className="field-label">Category
                <select className="field-input" value={formCategory} onChange={(e) => setFormCategory(e.target.value)}>
                  <option value="">— None —</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              {modal === 'create' && (
                <label className="field-label">Barcodes (comma-separated)
                  <input className="field-input" value={formBarcodes} onChange={(e) => setFormBarcodes(e.target.value)} placeholder="1234567890123, 9876543210987" />
                </label>
              )}
              {modal === 'edit' && (
                <label className="field-label checkbox-label">
                  <input type="checkbox" checked={formActive} onChange={(e) => setFormActive(e.target.checked)} />
                  Active
                </label>
              )}
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : modal === 'create' ? 'Create' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
