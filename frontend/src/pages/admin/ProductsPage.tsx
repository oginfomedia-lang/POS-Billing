import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  createProduct,
  deleteBarcode,
  generateInhouseBarcode,
  generateNewInhouseBarcode,
  listCategories,
  listProducts,
  updateProduct,
} from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { BarcodeType, CategoryOut, ProductOut, UOMType } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';

interface BarcodeItem {
  barcode: string;
  barcode_type: BarcodeType;
}

function inferBarcodeType(code: string): BarcodeType {
  const clean = code.trim();
  if (clean.startsWith('290') && clean.length === 13) return 'IN_HOUSE';
  if (clean.startsWith('20') && clean.length === 13) return 'PRICE_EMBEDDED';
  return 'MANUFACTURER';
}

export function ProductsPage() {
  const navigate = useNavigate();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [target, setTarget] = useState<ProductOut | null>(null);
  const [formSku, setFormSku] = useState('');
  const [formName, setFormName] = useState('');
  const [formPrice, setFormPrice] = useState('');
  const [formTax, setFormTax] = useState('0');
  const [formCategory, setFormCategory] = useState('');
  const [formUom, setFormUom] = useState<UOMType>('pcs');
  const [formVariableWeight, setFormVariableWeight] = useState(false);
  const [formActive, setFormActive] = useState(true);
  const [barcodesList, setBarcodesList] = useState<BarcodeItem[]>([]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const barcodeInputRef = useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    fetchAll();
  }, [page]);

  useEffect(() => {
    if (modal) {
      setTimeout(() => barcodeInputRef.current?.focus(), 100);
    }
  }, [modal]);

  function openCreate() {
    setModal('create');
    setTarget(null);
    setFormSku('');
    setFormName('');
    setFormPrice('');
    setFormTax('0');
    setFormCategory('');
    setFormUom('pcs');
    setFormVariableWeight(false);
    setBarcodesList([]);
    setBarcodeInput('');
    setFormActive(true);
    setFormError('');
  }

  function openEdit(p: ProductOut) {
    setModal('edit');
    setTarget(p);
    setFormSku(p.sku || '');
    setFormName(p.name);
    setFormPrice(String(p.price));
    setFormTax(String(p.tax_rate));
    setFormCategory(p.category_id ? String(p.category_id) : '');
    setFormUom(p.uom || 'pcs');
    setFormVariableWeight(p.is_variable_weight || false);
    setFormActive(p.is_active);
    setBarcodesList(
      p.barcodes
        ? p.barcodes.map((b) => ({
            barcode: b.barcode,
            barcode_type: b.barcode_type || 'MANUFACTURER',
          }))
        : [],
    );
    setBarcodeInput('');
    setFormError('');
  }

  function handleAddBarcodeFromInput(e?: React.KeyboardEvent | React.MouseEvent) {
    if (e && 'key' in e && e.key !== 'Enter') return;
    if (e) e.preventDefault(); // Prevent modal form submit on Enter key from scanner

    const code = barcodeInput.trim();
    if (!code) return;

    if (barcodesList.some((b) => b.barcode === code)) {
      setFormError(`Barcode '${code}' is already added to this item.`);
      return;
    }

    const bType = inferBarcodeType(code);
    setBarcodesList([...barcodesList, { barcode: code, barcode_type: bType }]);
    setBarcodeInput('');
    setFormError('');
  }

  async function handleGenerateInHouse() {
    setGenerating(true);
    setFormError('');
    try {
      if (target?.id) {
        const generated = await generateInhouseBarcode(target.id);
        if (!barcodesList.some((b) => b.barcode === generated.barcode)) {
          setBarcodesList([
            ...barcodesList,
            { barcode: generated.barcode, barcode_type: generated.barcode_type || 'IN_HOUSE' },
          ]);
        }
      } else {
        // Product not saved yet: the server hands out an unused code; it's attached when you click Create.
        if (barcodesList.some((b) => b.barcode_type === 'IN_HOUSE')) return;
        const code = await generateNewInhouseBarcode();
        setBarcodesList([...barcodesList, { barcode: code, barcode_type: 'IN_HOUSE' }]);
      }
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  async function handleRemoveBarcode(barcodeToRemove: string) {
    if (target?.id) {
      try {
        await deleteBarcode(target.id, barcodeToRemove);
      } catch {
        // Ignore error if barcode wasn't saved on backend yet
      }
    }
    setBarcodesList(barcodesList.filter((b) => b.barcode !== barcodeToRemove));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      await createProduct({
        sku: formSku || undefined,
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        category_id: formCategory ? parseInt(formCategory, 10) : null,
        uom: formUom,
        is_variable_weight: formVariableWeight,
        barcodes: barcodesList,
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
    setSaving(true);
    setFormError('');
    try {
      await updateProduct(target.id, {
        sku: formSku,
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        category_id: formCategory ? parseInt(formCategory, 10) : null,
        uom: formUom,
        is_variable_weight: formVariableWeight,
        is_active: formActive,
        barcodes: barcodesList,
      });
      setModal(null);
      fetchAll();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function getBadgeClass(type: BarcodeType): string {
    switch (type) {
      case 'IN_HOUSE':
        return 'badge-inhouse';
      case 'PRICE_EMBEDDED':
        return 'badge-scale';
      default:
        return 'badge-manufacturer';
    }
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>Products Management</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>
            + Add Product
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading products…</div>}

      <table className="data-table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>Name</th>
            <th>Price</th>
            <th>UOM</th>
            <th>Tax %</th>
            <th>Category</th>
            <th>Type</th>
            <th>Active</th>
            <th>Barcodes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {products.map((p) => {
            const cat = categories.find((c) => c.id === p.category_id);
            return (
              <tr key={p.id}>
                <td><code>{p.sku}</code></td>
                <td>{p.name}</td>
                <td>₹{Number(p.price).toFixed(2)}</td>
                <td><code>{p.uom || 'pcs'}</code></td>
                <td>{Number(p.tax_rate).toFixed(1)}%</td>
                <td>{cat?.name ?? '—'}</td>
                <td>
                  {p.is_variable_weight ? (
                    <span className="barcode-badge badge-scale">Scale (Weight)</span>
                  ) : (
                    <span className="barcode-badge badge-manufacturer">Standard</span>
                  )}
                </td>
                <td>{p.is_active ? '✓' : '—'}</td>
                <td>
                  <div className="barcode-chips-list">
                    {p.barcodes && p.barcodes.length > 0 ? (
                      p.barcodes.map((b) => (
                        <span key={b.id || b.barcode} className="barcode-chip">
                          {b.barcode}
                          <span className={`barcode-badge ${getBadgeClass(b.barcode_type)}`}>
                            {b.barcode_type || 'MFG'}
                          </span>
                        </span>
                      ))
                    ) : (
                      '—'
                    )}
                  </div>
                </td>
                <td className="table-actions">
                  <button className="btn-sm" onClick={() => openEdit(p)}>
                    Edit
                  </button>
                  <button
                    className="btn-sm"
                    onClick={() => navigate(`/admin/labels?product=${p.id}`, { state: { from: '/admin/products' } })}
                    disabled={p.barcodes.length === 0}
                    title={p.barcodes.length ? 'Print barcode stickers' : 'Add or generate a barcode first'}
                  >
                    Labels
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
          ← Prev
        </button>
        <span>
          Page {page} · {total} products
        </span>
        <button disabled={products.length < 25} onClick={() => setPage(page + 1)}>
          Next →
        </button>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box modal-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{modal === 'create' ? 'Add New Product' : `Edit ${target?.name}`}</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={modal === 'create' ? handleCreate : handleEdit} className="modal-form">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label className="field-label">
                  Product SKU / Code
                  <input
                    className="field-input"
                    value={formSku}
                    onChange={(e) => setFormSku(e.target.value)}
                    placeholder="e.g. SKU-00123"
                  />
                </label>
                <label className="field-label">
                  Product Name
                  <input
                    className="field-input"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    required
                    placeholder="e.g. DMart Premia Almonds"
                  />
                </label>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px' }}>
                <label className="field-label">
                  Price (₹)
                  <input
                    className="field-input"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formPrice}
                    onChange={(e) => setFormPrice(e.target.value)}
                    required
                  />
                </label>
                <label className="field-label">
                  Unit (UOM)
                  <select
                    className="field-input"
                    value={formUom}
                    onChange={(e) => setFormUom(e.target.value as any)}
                  >
                    <option value="pcs">pcs (Pieces)</option>
                    <option value="kg">kg (Kilograms)</option>
                    <option value="g">g (Grams)</option>
                    <option value="ltr">ltr (Liters)</option>
                    <option value="ml">ml (Milliliters)</option>
                    <option value="pack">pack (Packets)</option>
                  </select>
                </label>
                <label className="field-label">
                  Tax Rate (%)
                  <input
                    className="field-input"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    value={formTax}
                    onChange={(e) => setFormTax(e.target.value)}
                  />
                </label>
                <label className="field-label">
                  Category
                  <select
                    className="field-input"
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                  >
                    <option value="">— None —</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="field-label checkbox-label" style={{ marginTop: '4px' }}>
                <input
                  type="checkbox"
                  checked={formVariableWeight}
                  onChange={(e) => setFormVariableWeight(e.target.checked)}
                />
                <strong>Is Variable-Weight Item (Scale Produce / Loose Pack)?</strong>
              </label>

              <div className="field-label">
                <span>Associated Barcodes</span>
                <div className="barcode-scanner-box">
                  <input
                    ref={barcodeInputRef}
                    className="field-input"
                    style={{ flex: 1 }}
                    value={barcodeInput}
                    onChange={(e) => setBarcodeInput(e.target.value)}
                    onKeyDown={handleAddBarcodeFromInput}
                    placeholder="Scan USB scanner or type barcode, then Enter"
                    autoFocus
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => handleAddBarcodeFromInput()}
                  >
                    + Add
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleGenerateInHouse}
                    disabled={generating}
                  >
                    {generating ? 'Generating…' : '⚡ Generate In-House Barcode'}
                  </button>
                </div>

                <div className="barcode-chips-list" style={{ marginTop: '10px' }}>
                  {barcodesList.map((b) => (
                    <span key={b.barcode} className="barcode-chip">
                      {b.barcode}
                      <span className={`barcode-badge ${getBadgeClass(b.barcode_type)}`}>
                        {b.barcode_type}
                      </span>
                      <button
                        type="button"
                        className="chip-remove-btn"
                        onClick={() => handleRemoveBarcode(b.barcode)}
                        title="Remove Barcode"
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                  {barcodesList.length === 0 && (
                    <span style={{ fontSize: '13px', color: 'var(--muted)' }}>
                      No barcodes mapped yet. Scan or generate one above.
                    </span>
                  )}
                </div>
              </div>

              {modal === 'edit' && (
                <label className="field-label checkbox-label">
                  <input
                    type="checkbox"
                    checked={formActive}
                    onChange={(e) => setFormActive(e.target.checked)}
                  />
                  Active Product
                </label>
              )}

              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Saving…' : modal === 'create' ? 'Create Product' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
