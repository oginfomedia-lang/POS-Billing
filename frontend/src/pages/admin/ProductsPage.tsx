import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
import { stockIn } from '../../services/api/inventoryApi';
import { useAuth } from '../../hooks/useAuth';
import { useStoreContext, useStores } from '../../store/storeContext';
import { formatRupees } from '../../utils/money';
import type { BarcodeType, CategoryOut, ProductOut, UOMType } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';
import { StatusTabs, type StatusView } from '../../components/admin/StatusTabs';

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
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // Active and deactivated products are listed separately.
  const [view, setView] = useState<StatusView>('active');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [target, setTarget] = useState<ProductOut | null>(null);
  const [formSku, setFormSku] = useState('');
  const [formName, setFormName] = useState('');
  const [formPrice, setFormPrice] = useState('');
  const [formTax, setFormTax] = useState('0');
  const [formMrp, setFormMrp] = useState('');
  const [formHsn, setFormHsn] = useState('');
  const [formCategory, setFormCategory] = useState('');
  const [formUom, setFormUom] = useState<UOMType>('pcs');
  const [formVariableWeight, setFormVariableWeight] = useState(false);
  const [formActive, setFormActive] = useState(true);
  const [barcodesList, setBarcodesList] = useState<BarcodeItem[]>([]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  // Receive stock straight from the product form (no trip to the Inventory page).
  const { user } = useAuth();
  const stores = useStores().filter((s) => s.is_active);
  // The branch picked in the sidebar: the list shows shared products + that branch's own, with its prices.
  const branchId = useStoreContext((s) => s.selectedId);
  const [stockStoreId, setStockStoreId] = useState('');
  const [stockQty, setStockQty] = useState('');
  const [stockNote, setStockNote] = useState('');
  // After goods are received, offer to print that many stickers (same as the Inventory page).
  const [received, setReceived] = useState<{ productId: number; name: string; qty: string; hasBarcode: boolean } | null>(null);

  const barcodeInputRef = useRef<HTMLInputElement>(null);

  // Default store for received stock: the one picked elsewhere in the admin, else the user's own, else the first.
  useEffect(() => {
    if (!stores.length || stores.some((s) => String(s.id) === stockStoreId)) return;
    const preferred = useStoreContext.getState().selectedId ?? user?.store_id;
    setStockStoreId(String((stores.find((s) => s.id === preferred) ?? stores[0]).id));
  }, [stores.length]);

  const stockQtyValid = stockQty.trim() === '' || Number(stockQty) > 0;

  /** Adds the received qty for a just-saved product. Returns false (with the error shown) if it fails. */
  async function receiveStock(product: ProductOut): Promise<boolean> {
    if (stockQty.trim() === '') return true;
    try {
      await stockIn(Number(stockStoreId), product.id, stockQty.trim(), stockNote.trim());
      setReceived({ productId: product.id, name: product.name, qty: stockQty.trim(), hasBarcode: product.barcodes.length > 0 });
      return true;
    } catch (err) {
      setError(t('products.stockNotReceived', { name: product.name, error: getErrorMessage(err) }));
      return false;
    }
  }

  async function fetchAll(p = page) {
    setLoading(true);
    setError('');
    try {
      const [prod, cats] = await Promise.all([
        listProducts({ page: p, per_page: 25, status: view, store_id: branchId ?? undefined }),
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
  }, [page, view, branchId]);

  useEffect(() => {
    if (modal) {
      setTimeout(() => barcodeInputRef.current?.focus(), 100);
    }
  }, [modal]);

  /** Received stock goes to the branch picked in the sidebar, else the user's own, else the first. */
  function defaultStockStore() {
    const preferred = branchId ?? user?.store_id;
    const store = stores.find((s) => s.id === preferred) ?? stores[0];
    if (store) setStockStoreId(String(store.id));
  }

  // Selling price + GST, to compare with the MRP the user types (MRP includes GST).
  const priceNum = parseFloat(formPrice);
  const priceWithGst = Number.isFinite(priceNum) ? priceNum * (1 + (parseFloat(formTax) || 0) / 100) : null;
  const mrpNum = parseFloat(formMrp);
  const mrpTooLow = priceWithGst !== null && Number.isFinite(mrpNum) && mrpNum + 0.005 < priceWithGst;

  function openCreate() {
    defaultStockStore();
    setModal('create');
    setTarget(null);
    setFormSku('');
    setFormName('');
    setFormPrice('');
    setFormTax('0');
    setFormMrp('');
    setFormHsn('');
    setFormCategory('');
    setFormUom('pcs');
    setFormVariableWeight(false);
    setBarcodesList([]);
    setBarcodeInput('');
    setFormActive(true);
    setFormError('');
    setStockQty('');
    setStockNote('');
  }

  function openEdit(p: ProductOut) {
    defaultStockStore();
    setModal('edit');
    setTarget(p);
    setFormSku(p.sku || '');
    setFormName(p.name);
    setFormPrice(String(p.price));
    setFormTax(String(p.tax_rate));
    setFormMrp(p.mrp ?? '');
    setFormHsn(p.hsn_code ?? '');
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
    setStockQty('');
    setStockNote('');
  }

  function handleAddBarcodeFromInput(e?: React.KeyboardEvent | React.MouseEvent) {
    if (e && 'key' in e && e.key !== 'Enter') return;
    if (e) e.preventDefault(); // Prevent modal form submit on Enter key from scanner

    const code = barcodeInput.trim();
    if (!code) return;

    if (barcodesList.some((b) => b.barcode === code)) {
      setFormError(t('products.duplicateBarcode', { code }));
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
    if (!stockQtyValid) {
      setFormError(t('products.stockQtyInvalid'));
      return;
    }
    setSaving(true);
    setFormError('');
    setReceived(null);
    try {
      const created = await createProduct({
        sku: formSku || undefined,
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        mrp: formMrp.trim() ? parseFloat(formMrp) : null,
        hsn_code: formHsn.trim() || null,
        category_id: formCategory ? parseInt(formCategory, 10) : null,
        uom: formUom,
        is_variable_weight: formVariableWeight,
        barcodes: barcodesList,
      });
      setModal(null);
      await receiveStock(created);
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
    if (!stockQtyValid) {
      setFormError(t('products.stockQtyInvalid'));
      return;
    }
    setSaving(true);
    setFormError('');
    setReceived(null);
    try {
      const updated = await updateProduct(target.id, {
        sku: formSku,
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        mrp: formMrp.trim() ? parseFloat(formMrp) : null,
        hsn_code: formHsn.trim() || null,
        category_id: formCategory ? parseInt(formCategory, 10) : null,
        uom: formUom,
        is_variable_weight: formVariableWeight,
        is_active: formActive,
        barcodes: barcodesList,
      });
      setModal(null);
      await receiveStock(updated);
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
        <h2>{t('products.title')}</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>
            {t('products.add')}
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {received && (
        <div className="notice-bar">
          {t('common.received', { qty: received.qty, name: received.name })}
          {received.hasBarcode && Number.isInteger(Number(received.qty)) && (
            <button
              className="btn-primary btn-compact"
              onClick={() => navigate(
                `/admin/labels?product=${received.productId}&qty=${received.qty}`,
                { state: { from: '/admin/products' } },
              )}
            >
              {t('common.printLabels', { count: Number(received.qty) })}
            </button>
          )}
          <button className="btn-sm" onClick={() => setReceived(null)}>{t('common.dismiss')}</button>
        </div>
      )}
      <StatusTabs value={view} onChange={(v) => { setView(v); setPage(1); }} />
      {loading && <div className="loading-text">{t('products.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('products.colSku')}</th>
              <th>{t('products.colName')}</th>
              <th>{t('products.colPrice')}</th>
              <th>{t('products.colMrp')}</th>
              <th>{t('products.colUom')}</th>
              <th>{t('products.colTax')}</th>
              <th>{t('products.colCategory')}</th>
              <th>{t('products.colType')}</th>
              <th>{t('products.colBarcodes')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {!loading && products.length === 0 && (
              <tr>
                <td colSpan={10} className="empty-row">
                  {view === 'active' ? t('products.emptyActive') : t('products.emptyInactive')}
                </td>
              </tr>
            )}
            {products.map((p) => {
              const cat = categories.find((c) => c.id === p.category_id);
              return (
                <tr key={p.id}>
                  <td><code>{p.sku}</code></td>
                  <td>{p.name}</td>
                  <td title={p.store_price ? t('products.branchPriceTip') : undefined}>
                    {formatRupees(p.store_price ?? p.price)}
                    {p.store_price && <span className="status-muted price-hq">{t('products.hqPrice', { price: formatRupees(p.price) })}</span>}
                  </td>
                  <td>{p.mrp ? formatRupees(p.mrp) : '—'}</td>
                  <td><code>{p.uom || 'pcs'}</code></td>
                  <td>{Number(p.tax_rate).toFixed(1)}%</td>
                  <td>{cat?.name ?? '—'}</td>
                  <td>
                    {p.is_variable_weight ? (
                      <span className="barcode-badge badge-scale">{t('products.typeScale')}</span>
                    ) : (
                      <span className="barcode-badge badge-manufacturer">{t('products.typeStandard')}</span>
                    )}
                  </td>
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
                      {t('common.edit')}
                    </button>
                    <button
                      className="btn-sm"
                      onClick={() => navigate(`/admin/labels?product=${p.id}`, { state: { from: '/admin/products' } })}
                      disabled={p.barcodes.length === 0}
                      title={p.barcodes.length ? t('products.labelsTitle') : t('products.labelsNeedBarcode')}
                    >
                      {t('products.labelsBtn')}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
          {t('common.prev')}
        </button>
        <span>
          {t('common.pageInfo', { page, total })}
        </span>
        <button disabled={products.length < 25} onClick={() => setPage(page + 1)}>
          {t('common.next')}
        </button>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box modal-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{modal === 'create' ? t('products.addTitle') : t('products.editTitle', { name: target?.name })}</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={modal === 'create' ? handleCreate : handleEdit} className="modal-form">
              <div className="form-row">
                <label className="field-label">
                  {t('products.sku')}
                  <input
                    className="field-input"
                    value={formSku}
                    onChange={(e) => setFormSku(e.target.value)}
                    placeholder={t('products.skuPlaceholder')}
                  />
                </label>
                <label className="field-label">
                  {t('products.productName')}
                  <input
                    className="field-input"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    required
                    placeholder={t('products.namePlaceholder')}
                  />
                </label>
              </div>

              <div className="form-row form-row-3">
                <label className="field-label">
                  {t('products.price')}
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
                  {t('products.uom')}
                  <select
                    className="field-input"
                    value={formUom}
                    onChange={(e) => setFormUom(e.target.value as any)}
                  >
                    {(['pcs', 'kg', 'g', 'ltr', 'ml', 'pack'] as const).map((u) => (
                      <option key={u} value={u}>{t(`products.uoms.${u}`)}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  {t('products.taxRate')}
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
                  {t('products.category')}
                  <select
                    className="field-input"
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                  >
                    <option value="">{t('common.none')}</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="form-row">
                <label className="field-label">
                  {t('products.mrp')}
                  <input
                    className="field-input"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formMrp}
                    onChange={(e) => setFormMrp(e.target.value)}
                    placeholder={t('products.mrpPlaceholder')}
                  />
                  {priceWithGst !== null && (
                    <span className={`hint-text${mrpTooLow ? ' text-danger' : ''}`}>
                      {mrpTooLow
                        ? t('products.mrpTooLow', { price: formatRupees(priceWithGst.toFixed(2)) })
                        : t('products.priceWithGst', { price: formatRupees(priceWithGst.toFixed(2)) })}
                    </span>
                  )}
                </label>
                <label className="field-label">
                  {t('products.hsn')}
                  <input
                    className="field-input"
                    inputMode="numeric"
                    pattern="[0-9]{4,8}"
                    maxLength={8}
                    value={formHsn}
                    onChange={(e) => setFormHsn(e.target.value.replace(/\D/g, ''))}
                    placeholder={t('products.hsnPlaceholder')}
                    title={t('products.hsnTitle')}
                  />
                </label>
              </div>

              <label className="field-label checkbox-label">
                <input
                  type="checkbox"
                  checked={formVariableWeight}
                  onChange={(e) => setFormVariableWeight(e.target.checked)}
                />
                <strong>{t('products.variableWeight')}</strong>
              </label>

              <div className="field-label">
                <span>{t('products.barcodes')}</span>
                <div className="barcode-scanner-box">
                  <input
                    ref={barcodeInputRef}
                    className="field-input"
                    style={{ flex: 1 }}
                    value={barcodeInput}
                    onChange={(e) => setBarcodeInput(e.target.value)}
                    onKeyDown={handleAddBarcodeFromInput}
                    placeholder={t('products.barcodePlaceholder')}
                    autoFocus
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => handleAddBarcodeFromInput()}
                  >
                    {t('products.addBarcode')}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleGenerateInHouse}
                    disabled={generating}
                  >
                    {generating ? t('products.generating') : t('products.generate')}
                  </button>
                </div>

                <div className="barcode-chips-list">
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
                        title={t('products.removeBarcode')}
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                  {barcodesList.length === 0 && (
                    <span className="hint-text">
                      {t('products.noBarcodes')}
                    </span>
                  )}
                </div>
              </div>

              <fieldset className="form-section">
                <legend>{t('products.receiveStock')}</legend>
                <div className={stores.length > 1 ? 'form-row form-row-3' : 'form-row'}>
                  <label className="field-label">
                    {modal === 'create' ? t('products.openingStock') : t('products.addStock')}
                    <input
                      className="field-input"
                      type="number"
                      min="0.001"
                      step="any"
                      value={stockQty}
                      onChange={(e) => setStockQty(e.target.value)}
                      placeholder={t('products.qtyPlaceholder')}
                    />
                  </label>
                  {stores.length > 1 && (
                    <label className="field-label">
                      {t('common.store')}
                      <select className="field-input" value={stockStoreId} onChange={(e) => setStockStoreId(e.target.value)}>
                        {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                      </select>
                    </label>
                  )}
                  <label className="field-label">
                    {t('common.note')}
                    <input
                      className="field-input"
                      maxLength={500}
                      value={stockNote}
                      onChange={(e) => setStockNote(e.target.value)}
                      placeholder={t('products.notePlaceholder')}
                    />
                  </label>
                </div>
                <span className="hint-text">{t('products.receiveHint')}</span>
              </fieldset>

              {modal === 'edit' && (
                <label className="field-label checkbox-label">
                  <input
                    type="checkbox"
                    checked={formActive}
                    onChange={(e) => setFormActive(e.target.checked)}
                  />
                  {t('products.activeProduct')}
                </label>
              )}

              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(null)}>
                  {t('common.cancel')}
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? t('common.saving') : modal === 'create' ? t('products.createBtn') : t('products.saveChanges')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
