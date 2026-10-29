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
  previewSku,
  updateProduct,
} from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import { stockIn } from '../../services/api/inventoryApi';
import { supplierApi } from '../../services/api/supplierApi';
import { useAuth } from '../../hooks/useAuth';
import { useStoreContext, useStores } from '../../store/storeContext';
import { formatRupees } from '../../utils/money';
import { skuField } from '../../utils/sku';
import type { BarcodeType, CategoryOut, ProductOut, UOMType } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconX } from '../../components/common/Icons';
import { MarathiInput } from '../../components/common/MarathiInput';
import { ProductImportDialog } from '../../components/admin/ProductImportDialog';
import type { SupplierOut } from '../../types/api';
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
  // Search box: name / SKU / barcode, English or Marathi ("sakhar" also finds "साखर").
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState(''); // what was actually searched (a moment after the last key)

  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [target, setTarget] = useState<ProductOut | null>(null);
  const [formSku, setFormSku] = useState('');
  // New products get an automatic SKU from the server on save; skuPreview is what it will look like.
  // An admin may tick "own SKU" and type one instead (also to change an existing product's SKU).
  const [skuPreview, setSkuPreview] = useState('');
  const [ownSku, setOwnSku] = useState(false);
  const [savedSku, setSavedSku] = useState<{ name: string; sku: string } | null>(null);
  const [formName, setFormName] = useState('');
  const [formPrice, setFormPrice] = useState('');
  const [formTax, setFormTax] = useState('0');
  const [formMrp, setFormMrp] = useState('');
  const [formCost, setFormCost] = useState('');
  const [formHsn, setFormHsn] = useState('');
  const [formCategory, setFormCategory] = useState('');
  const [formSupplier, setFormSupplier] = useState('');
  const [suppliers, setSuppliers] = useState<SupplierOut[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [formUom, setFormUom] = useState<UOMType>('pcs');
  const [formVariableWeight, setFormVariableWeight] = useState(false);
  // Loose items: the item code set on the weighing scale.
  const [formPlu, setFormPlu] = useState('');
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
        listProducts({ page: p, per_page: 25, status: view, store_id: branchId ?? undefined, q: query || undefined }),
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
  }, [page, view, branchId, query]);

  // Search 350 ms after the last key, from page 1.
  useEffect(() => {
    const timer = setTimeout(() => { setPage(1); setQuery(search.trim()); }, 350);
    return () => clearTimeout(timer);
  }, [search]);

  // Suppliers for the product form (the usual supplier of a product). Optional: the form works without them.
  useEffect(() => {
    supplierApi.list({ status: 'active', per_page: 500 })
      .then((r) => setSuppliers(r.data.items))
      .catch(() => setSuppliers([]));
  }, []);

  useEffect(() => {
    if (modal) {
      setTimeout(() => barcodeInputRef.current?.focus(), 100);
    }
  }, [modal]);

  // Live SKU preview while a new product's category and name are typed (a moment after the last key).
  useEffect(() => {
    if (modal !== 'create' || ownSku || !formCategory || !formName.trim()) {
      setSkuPreview('');
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      previewSku(parseInt(formCategory, 10), formName)
        .then((r) => { if (!stale) setSkuPreview(r.sku); })
        .catch(() => { if (!stale) setSkuPreview(''); });
    }, 300);
    return () => { stale = true; clearTimeout(timer); };
  }, [modal, ownSku, formCategory, formName]);

  const sku = skuField({
    mode: modal === 'edit' ? 'edit' : 'create', ownSku, savedSku: target?.sku ?? '',
    categoryId: formCategory, name: formName, preview: skuPreview,
  });

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
  // Purchase cost: admin and manager (the server hides it from cashiers). The branch's average cost
  // (from goods receipts) wins over the default cost.
  const seesCost = user?.role === 'admin' || user?.role === 'manager';
  const branchAvgCost = target?.store_avg_cost ?? null;
  const costNum = parseFloat(branchAvgCost ?? formCost);
  const belowCost = Number.isFinite(priceNum) && Number.isFinite(costNum) && priceNum + 0.005 < costNum;
  const costPayload = seesCost ? { cost_price: formCost.trim() ? parseFloat(formCost) : null } : {};

  function openCreate() {
    defaultStockStore();
    setModal('create');
    setTarget(null);
    setFormSku('');
    setSkuPreview('');
    setOwnSku(false);
    setFormName('');
    setFormPrice('');
    setFormTax('0');
    setFormMrp('');
    setFormCost('');
    setFormHsn('');
    setFormCategory('');
    setFormSupplier('');
    setFormUom('pcs');
    setFormVariableWeight(false);
    setFormPlu('');
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
    setOwnSku(false);
    setFormName(p.name);
    setFormPrice(String(p.price));
    setFormTax(String(p.tax_rate));
    setFormMrp(p.mrp ?? '');
    setFormCost(p.cost_price != null ? String(Number(p.cost_price)) : '');
    setFormHsn(p.hsn_code ?? '');
    setFormCategory(p.category_id ? String(p.category_id) : '');
    setFormSupplier(p.supplier_id ? String(p.supplier_id) : '');
    setFormUom(p.uom || 'pcs');
    setFormVariableWeight(p.is_variable_weight || false);
    setFormPlu(p.plu_code ?? '');
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

    if (barcodesList.length > 0) {
      setFormError(t('products.oneBarcodeHint'));
      return;
    }

    setBarcodesList([{ barcode: code, barcode_type: inferBarcodeType(code) }]);
    setBarcodeInput('');
    setFormError('');
  }

  async function handleGenerateInHouse() {
    if (barcodesList.length > 0) return; // one barcode per product
    setGenerating(true);
    setFormError('');
    try {
      if (target?.id) {
        const generated = await generateInhouseBarcode(target.id);
        setBarcodesList([{ barcode: generated.barcode, barcode_type: generated.barcode_type || 'IN_HOUSE' }]);
      } else {
        // Product not saved yet: the server hands out an unused code; it's attached when you click Create.
        const code = await generateNewInhouseBarcode();
        setBarcodesList([{ barcode: code, barcode_type: 'IN_HOUSE' }]);
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
    setSavedSku(null);
    try {
      const created = await createProduct({
        sku: ownSku && formSku.trim() ? formSku.trim() : undefined,
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        mrp: formMrp.trim() ? parseFloat(formMrp) : null,
        ...costPayload,
        hsn_code: formHsn.trim() || null,
        category_id: formCategory ? parseInt(formCategory, 10) : null,
        supplier_id: formSupplier ? parseInt(formSupplier, 10) : null,
        uom: formUom,
        is_variable_weight: formVariableWeight,
        plu_code: formVariableWeight ? formPlu.trim() || null : null,
        barcodes: barcodesList,
      });
      setModal(null);
      setSavedSku({ name: created.name, sku: created.sku });
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
        ...(ownSku ? { sku: formSku.trim() } : {}), // otherwise the SKU stays as it is
        name: formName,
        price: parseFloat(formPrice),
        tax_rate: parseFloat(formTax) || 0,
        mrp: formMrp.trim() ? parseFloat(formMrp) : null,
        ...costPayload,
        hsn_code: formHsn.trim() || null,
        category_id: formCategory ? parseInt(formCategory, 10) : null,
        supplier_id: formSupplier ? parseInt(formSupplier, 10) : null,
        uom: formUom,
        is_variable_weight: formVariableWeight,
        plu_code: formVariableWeight ? formPlu.trim() || null : null,
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
          <button className="btn-secondary" onClick={() => setImportOpen(true)}>
            {t('import.open')}
          </button>
          <button className="btn-primary" onClick={openCreate}>
            {t('products.add')}
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {savedSku && (
        <div className="notice-bar">
          {t('products.savedWithSku', { name: savedSku.name, sku: savedSku.sku })}
          <button className="btn-sm" onClick={() => setSavedSku(null)}>{t('common.dismiss')}</button>
        </div>
      )}
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
      <div className="form-row" style={{ marginBottom: 12 }}>
        <MarathiInput
          className="field-input"
          value={search}
          onChange={setSearch}
          maxLength={100}
          placeholder={t('products.searchPlaceholder')}
        />
      </div>
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
                      <span className="barcode-badge badge-scale">
                        {t('products.typeScale')}{p.plu_code ? ` · ${t('products.pluShort', { code: p.plu_code })}` : ''}
                      </span>
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
        <div className="modal-overlay">
          <div className="modal-box modal-wide">
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setModal(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>{modal === 'create' ? t('products.addTitle') : t('products.editTitle', { name: target?.name })}</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={modal === 'create' ? handleCreate : handleEdit} className="modal-form">
              <div className="form-row">
                <label className="field-label">
                  {sku.kind === 'preview' ? t('products.skuPreviewLabel') : t('products.sku')}
                  {sku.kind === 'own' ? (
                    <input
                      className="field-input"
                      value={formSku}
                      onChange={(e) => setFormSku(e.target.value)}
                      maxLength={50}
                      required={modal === 'edit'}
                      placeholder={t('products.skuPlaceholder')}
                    />
                  ) : (
                    <input
                      className="field-input"
                      readOnly
                      tabIndex={-1}
                      value={sku.kind === 'waiting' ? '' : sku.sku}
                      placeholder={t('products.skuWaiting')}
                    />
                  )}
                  <span className="hint-text">
                    {sku.kind === 'preview' ? t('products.skuPreviewHint')
                      : sku.kind === 'saved' ? t('products.skuSavedHint')
                      : sku.kind === 'waiting' ? t('products.skuWaitingHint') : t('products.skuOwnHint')}
                  </span>
                </label>
                <label className="field-label">
                  {t('products.productName')}
                  <MarathiInput
                    className="field-input"
                    value={formName}
                    onChange={setFormName}
                    required
                    maxLength={200}
                    placeholder={t('products.namePlaceholder')}
                  />
                </label>
              </div>
              {user?.role === 'admin' && (
                <label className="field-label checkbox-label">
                  <input
                    type="checkbox"
                    checked={ownSku}
                    onChange={(e) => {
                      setOwnSku(e.target.checked);
                      setFormSku(modal === 'edit' ? target?.sku ?? '' : '');
                    }}
                  />
                  {modal === 'edit' ? t('products.skuChangeOwn') : t('products.skuUseOwn')}
                </label>
              )}

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
                    {/* Deactivated categories are not offered, except the one this product already has. */}
                    {categories.filter((c) => c.is_active || String(c.id) === formCategory).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  {t('products.supplier')}
                  <select
                    className="field-input"
                    value={formSupplier}
                    onChange={(e) => setFormSupplier(e.target.value)}
                  >
                    <option value="">{t('common.none')}</option>
                    {/* Keep showing a supplier that was deactivated after it was set. */}
                    {formSupplier && !suppliers.some((x) => String(x.id) === formSupplier) && (
                      <option value={formSupplier}>#{formSupplier}</option>
                    )}
                    {suppliers.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.company_name} ({x.supplier_code})
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

              {seesCost && (
                <label className="field-label">
                  {t('products.costPrice')}
                  <input
                    className="field-input"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formCost}
                    onChange={(e) => setFormCost(e.target.value)}
                    placeholder={t('products.costPlaceholder')}
                  />
                  {!formCost.trim() && branchAvgCost === null && (
                    <span className="hint-text">{t('products.costAutoHint')}</span>
                  )}
                  {branchAvgCost !== null && (
                    <span className="hint-text">{t('products.branchAvgCost', { cost: formatRupees(Number(branchAvgCost).toFixed(2)) })}</span>
                  )}
                  {belowCost && (
                    <span className="hint-text text-danger">{t('products.belowCost', { cost: formatRupees(costNum.toFixed(2)) })}</span>
                  )}
                </label>
              )}

              <label className="field-label checkbox-label">
                <input
                  type="checkbox"
                  checked={formVariableWeight}
                  onChange={(e) => {
                    setFormVariableWeight(e.target.checked);
                    // Loose items are sold by the kg.
                    if (e.target.checked && formUom === 'pcs') setFormUom('kg');
                  }}
                />
                <strong>{t('products.variableWeight')}</strong>
              </label>
              {formVariableWeight && (
                <label className="field-label">
                  {t('products.pluCode')}
                  <input
                    className="field-input"
                    inputMode="numeric"
                    maxLength={6}
                    value={formPlu}
                    onChange={(e) => setFormPlu(e.target.value.replace(/\D/g, ''))}
                    placeholder="123"
                  />
                  <span className="hint-text">{t('products.pluHint')}</span>
                </label>
              )}

              <div className="field-label">
                <span>{t('products.barcodes')}</span>
                {barcodesList.length === 0 && (
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
                )}

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
                  <span className="hint-text">
                    {barcodesList.length === 0 ? t('products.noBarcodes') : t('products.oneBarcodeHint')}
                  </span>
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
      {importOpen && (
        <ProductImportDialog
          stores={stores}
          defaultStoreId={branchId ?? user?.store_id ?? null}
          onImported={() => fetchAll()}
          onClose={() => setImportOpen(false)}
        />
      )}
    </div>
  );
}
