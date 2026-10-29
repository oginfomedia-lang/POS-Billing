// Stock-in, adjustments, ledger, low stock, and expiry alerts.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconX } from '../../components/common/Icons';
import { MarathiInput } from '../../components/common/MarathiInput';
import { getErrorMessage } from '../../services/api/httpClient';
import {
  adjustStock,
  getBatches,
  getExpiringProducts,
  getLedger,
  getStockLevels,
  setStorePrice,
  setThreshold,
  stockIn,
  writeOffBatch,
} from '../../services/api/inventoryApi';
import { useStoreContext, useStores } from '../../store/storeContext';
import type { BatchOut, ExpiringBatchOut, InventoryTxnOut, StockLevelOut } from '../../types/inventory';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

type Tab = 'stock' | 'expiry';
type Kind = 'in' | 'adjust' | 'threshold' | 'price' | 'history' | 'batches';
/** The batch being written off (from the Batches window or the expiry list). */
type WriteOff = { batchId: number; label: string; left: string; name: string; uom: string } | null;
type Modal = { kind: Kind; row: StockLevelOut } | null;



function qtyText(qty: string): string {
  return String(Number(qty));
}

function batchLabel(batchNumber: string | null, id: number): string {
  return batchNumber || `#${id}`;
}

function expiryRowStyle(days: number): { background: string } {
  if (days <= 7) return { background: '#fef2f2' };
  if (days <= 15) return { background: '#fff7ed' };
  return { background: '#fefce8' };
}

export function InventoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // ?tab=expiry opens the expiry alerts straight away (the dashboard's near-expiry tile links here).
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>(searchParams.get('tab') === 'expiry' ? 'expiry' : 'stock');
  const stores = useStores().filter((s) => s.is_active);
  const selectStore = useStoreContext((s) => s.select);
  // The branch picked in the sidebar switcher (null = head office, must pick one).
  const storeId = useStoreContext((s) => s.selectedId);
  const [rows, setRows] = useState<StockLevelOut[]>([]);
  const [filter, setFilter] = useState('');
  const [query, setQuery] = useState(''); // searched a moment after the last key
  const [lowOnly, setLowOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [expiringRows, setExpiringRows] = useState<ExpiringBatchOut[]>([]);
  const [expiryLoading, setExpiryLoading] = useState(false);

  const [modal, setModal] = useState<Modal>(null);
  const [qty, setQty] = useState('');
  const [notes, setNotes] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [batchNumber, setBatchNumber] = useState('');
  const [ledger, setLedger] = useState<InventoryTxnOut[]>([]);
  const [batches, setBatches] = useState<BatchOut[]>([]);
  const [writeOff, setWriteOff] = useState<WriteOff>(null);
  const [woQty, setWoQty] = useState('');
  const [woReason, setWoReason] = useState('');
  const [woError, setWoError] = useState('');
  const [woSaving, setWoSaving] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [printOffer, setPrintOffer] = useState<{ productId: number; name: string; qty: number } | null>(null);

  async function fetchLevels(id = storeId) {
    if (id === null) { setRows([]); return; }
    setLoading(true);
    setError('');
    try {
      setRows(await getStockLevels(id, query));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function fetchExpiring(id = storeId) {
    if (id === null) return;
    setExpiryLoading(true);
    try {
      setExpiringRows(await getExpiringProducts(id));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setExpiryLoading(false);
    }
  }

  useEffect(() => { fetchLevels(); }, [storeId, query]);
  // Search on the server (English, Marathi, or Marathi typed in English letters), 350 ms after the last key.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(filter.trim()), 350);
    return () => clearTimeout(timer);
  }, [filter]);
  useEffect(() => { if (tab === 'expiry') fetchExpiring(); }, [tab, storeId]);

  async function open(kind: Kind, row: StockLevelOut) {
    setQty(
      kind === 'adjust' ? qtyText(row.qty_on_hand)
        : kind === 'threshold' ? (row.low_stock_threshold === null ? '' : qtyText(row.low_stock_threshold))
        : kind === 'price' ? (row.store_price ?? '')
        : '',
    );
    setNotes('');
    setExpiryDate('');
    setBatchNumber('');
    setFormError('');
    setLedger([]);
    setBatches([]);
    setModal({ kind, row });
    if (kind === 'history' && storeId !== null) {
      try {
        setLedger(await getLedger(storeId, row.product_id));
      } catch (err) {
        setFormError(getErrorMessage(err));
      }
    }
    if (kind === 'batches') loadBatches(row.product_id);
  }

  async function loadBatches(productId: number) {
    if (storeId === null) return;
    try {
      setBatches(await getBatches(storeId, productId));
    } catch (err) {
      setFormError(getErrorMessage(err));
    }
  }

  function openWriteOff(target: NonNullable<WriteOff>) {
    setWoQty(qtyText(target.left));
    setWoReason('');
    setWoError('');
    setWriteOff(target);
  }

  async function handleWriteOff(e: FormEvent) {
    e.preventDefault();
    if (!writeOff) return;
    setWoSaving(true);
    setWoError('');
    try {
      const all = Number(woQty) === Number(writeOff.left);
      await writeOffBatch(writeOff.batchId, all ? null : woQty.trim(), woReason.trim());
      setWriteOff(null);
      fetchLevels();
      if (tab === 'expiry') fetchExpiring();
      if (modal?.kind === 'batches') loadBatches(modal.row.product_id);
    } catch (err) {
      setWoError(getErrorMessage(err));
    } finally {
      setWoSaving(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!modal || storeId === null) return;
    setSaving(true);
    setFormError('');
    try {
      if (modal.kind === 'in') {
        await stockIn(storeId, modal.row.product_id, qty.trim(), notes.trim(), expiryDate || undefined, batchNumber.trim());
        const received = Number(qty);
        setPrintOffer(
          modal.row.barcode
            ? {
                productId: modal.row.product_id,
                name: `${received} ${modal.row.uom || 'pcs'} × ${modal.row.product_name}`,
                qty: Math.max(1, Math.round(received)),
              }
            : null,
        );
      } else if (modal.kind === 'price') {
        await setStorePrice(storeId, modal.row.product_id, qty.trim() === '' ? null : qty.trim());
      } else if (modal.kind === 'threshold') {
        await setThreshold(storeId, modal.row.product_id, qty.trim() === '' ? null : qty.trim());
      } else {
        await adjustStock(storeId, modal.row.product_id, qty.trim(), notes.trim());
      }
      setModal(null);
      fetchLevels();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function expiryText(days: number | null): string {
    if (days === null) return '—';
    if (days < 0) return t('inventory.expiredAgo', { count: -days });
    if (days === 0) return t('inventory.expiresToday');
    return t('inventory.daysLeft', { count: days });
  }

  // The server already filtered by the search text; only the low-stock tick is applied here.
  const visible = rows.filter((r) => !lowOnly || r.is_low);
  const lowCount = rows.filter((r) => r.is_low).length;

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('inventory.title')}</h2>
      </div>

      {error && <div className="page-error">{error}</div>}

      {storeId === null && (
        <div className="notice-bar notice-info">
          {t('inventory.chooseBranch')}
          <select className="field-input filter-input" value="" onChange={(e) => selectStore(Number(e.target.value))}>
            <option value="" disabled>{t('stores.switcherLabel')}</option>
            {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      )}

      <div className="filter-bar">
        {tab === 'stock' && (
          <>
            <MarathiInput
              className="field-input filter-input"
              placeholder={t('inventory.searchPlaceholder')}
              value={filter}
              onChange={setFilter}
              maxLength={100}
            />
            <label className="field-label checkbox-label">
              <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
              {t('inventory.lowOnly', { count: lowCount })}
            </label>
          </>
        )}
      </div>

      <div className="tab-bar">
        <button
          className={`tab-btn${tab === 'stock' ? ' tab-active' : ''}`}
          onClick={() => setTab('stock')}
        >
          {t('inventory.tabStock')}
        </button>
        <button
          className={`tab-btn${tab === 'expiry' ? ' tab-active' : ''}`}
          onClick={() => setTab('expiry')}
        >
          {t('inventory.tabExpiry')}
          {expiringRows.length > 0 && <span className="badge-count"> {expiringRows.length}</span>}
        </button>
      </div>

      {printOffer && (
        <div className="notice-bar">
          {t('common.received', { qty: printOffer.qty, name: printOffer.name })}
          <button
            className="btn-primary btn-compact"
            onClick={() => navigate(
              `/admin/labels?product=${printOffer.productId}&qty=${printOffer.qty}`,
              { state: { from: '/admin/inventory' } },
            )}
          >
            {t('common.printLabels', { count: printOffer.qty })}
          </button>
          <button className="btn-sm" onClick={() => setPrintOffer(null)}>{t('common.dismiss')}</button>
        </div>
      )}

      {tab === 'stock' && (
        <>
          {loading && <div className="loading-text">{t('common.loading')}</div>}
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th>{t('inventory.colProduct')}</th><th>{t('inventory.colBarcode')}</th><th className="num">{t('inventory.colInStock')}</th><th className="num">{t('inventory.colLowAt')}</th><th className="num">{t('inventory.colPrice')}</th><th>{t('inventory.colStatus')}</th><th /></tr>
              </thead>
              <tbody>
                {!loading && visible.length === 0 && (
                  <tr><td colSpan={7} className="empty-row">{t('inventory.empty')}</td></tr>
                )}
                {visible.map((r) => (
                  <tr key={r.product_id}>
                    <td>{r.product_name}</td>
                    <td>{r.barcode ?? '—'}</td>
                    <td className="num">{qtyText(r.qty_on_hand)} {r.uom || 'pcs'}</td>
                    <td className="num" title={r.low_stock_threshold === null ? t('inventory.defaultTip') : t('inventory.productTip')}>
                      {qtyText(r.effective_threshold)} {r.uom || 'pcs'}{r.low_stock_threshold === null && <span className="status-muted"> {t('inventory.default')}</span>}
                    </td>
                    <td className="num" title={r.store_price === null ? t('inventory.hqPrice') : t('inventory.branchPrice')}>
                      {formatRupees(r.price)}
                      {r.store_price !== null && <span className="price-tag-branch">{t('inventory.branchPrice')}</span>}
                    </td>
                    <td>
                      {Number(r.qty_on_hand) <= 0
                        ? <span className="stock-badge stock-out">{t('inventory.outOfStock')}</span>
                        : r.is_low ? <span className="stock-badge stock-low">{t('inventory.low')}</span> : '—'}
                    </td>
                    <td className="table-actions">
                      <button className="btn-sm" onClick={() => open('in', r)}>{t('inventory.stockIn')}</button>
                      <button className="btn-sm" onClick={() => open('adjust', r)}>{t('inventory.adjust')}</button>
                      <button className="btn-sm" onClick={() => open('threshold', r)}>{t('inventory.lowLevel')}</button>
                      <button className="btn-sm" onClick={() => open('price', r)}>{t('inventory.setPrice')}</button>
                      <button className="btn-sm" onClick={() => open('batches', r)}>{t('inventory.batches')}</button>
                      <button className="btn-sm" onClick={() => open('history', r)}>{t('inventory.history')}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'expiry' && (
        <>
          {expiryLoading && <div className="loading-text">{t('common.loading')}</div>}
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th>{t('inventory.colProduct')}</th><th>{t('inventory.colBatch')}</th><th className="num">{t('inventory.colLeft')}</th><th className="num">{t('inventory.colInStock')}</th><th>{t('inventory.colExpiry')}</th><th className="num">{t('inventory.colDaysLeft')}</th><th /></tr>
              </thead>
              <tbody>
                {!expiryLoading && expiringRows.length === 0 && (
                  <tr><td colSpan={7} className="empty-row">{t('inventory.noExpiring')}</td></tr>
                )}
                {expiringRows.map((r) => (
                  <tr key={r.batch_id ?? r.product_id} style={expiryRowStyle(r.days_to_expiry)}>
                    <td>{r.product_name}</td>
                    <td>{r.batch_id !== null ? batchLabel(r.batch_number, r.batch_id) : '—'}</td>
                    <td className="num">{r.batch_qty !== null ? `${qtyText(r.batch_qty)} ${r.uom || 'pcs'}` : '—'}</td>
                    <td className="num">{qtyText(r.qty_on_hand)} {r.uom || 'pcs'}</td>
                    <td>{r.nearest_expiry}</td>
                    <td className="num">{expiryText(r.days_to_expiry)}</td>
                    <td className="table-actions">
                      {r.batch_id !== null && r.batch_qty !== null && (
                        <button
                          className="btn-sm"
                          onClick={() => openWriteOff({
                            batchId: r.batch_id!, label: batchLabel(r.batch_number, r.batch_id!), left: r.batch_qty!,
                            name: r.product_name, uom: r.uom || 'pcs',
                          })}
                        >
                          {t('inventory.writeOff')}
                        </button>
                      )}
                      <button
                        className="btn-primary btn-sm"
                        onClick={() => navigate(
                          `/admin/discounts?product_id=${r.product_id}&product_name=${encodeURIComponent(r.product_name)}&ends_at=${r.nearest_expiry}`,
                        )}
                      >
                        {t('inventory.createOffer')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint-text">{t('inventory.expiryLegend')}</p>
        </>
      )}


      {modal && (
        <div className="modal-overlay">
          <div className={`modal-box${modal.kind === 'history' || modal.kind === 'batches' ? ' modal-wide' : ''}`}>
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setModal(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>
              {t(({ in: 'inventory.titleIn', adjust: 'inventory.titleAdjust', threshold: 'inventory.titleThreshold', price: 'inventory.titlePrice', history: 'inventory.titleHistory', batches: 'inventory.titleBatches' } as const)[modal.kind], { name: modal.row.product_name })}
            </h3>
            {formError && <div className="form-error">{formError}</div>}

            {modal.kind === 'batches' ? (
              <>
                <p className="hint-text">{t('inventory.batchesHint')}</p>
                <div className="table-card">
                  <table className="data-table">
                    <thead>
                      <tr><th>{t('inventory.colBatch')}</th><th>{t('inventory.colExpiry')}</th><th className="num">{t('inventory.colLeft')}</th><th>{t('inventory.colSource')}</th><th>{t('inventory.colReceived')}</th><th /></tr>
                    </thead>
                    <tbody>
                      {batches.length === 0 && <tr><td colSpan={6} className="empty-row">{t('inventory.noBatches')}</td></tr>}
                      {batches.map((b) => (
                        <tr key={b.id} style={b.days_to_expiry !== null && b.days_to_expiry <= 30 ? expiryRowStyle(b.days_to_expiry) : undefined}>
                          <td>{batchLabel(b.batch_number, b.id)}</td>
                          <td>{b.expiry_date ? `${b.expiry_date} · ${expiryText(b.days_to_expiry)}` : '—'}</td>
                          <td className="num">{qtyText(b.qty_remaining)} / {qtyText(b.qty_received)} {modal.row.uom || 'pcs'}</td>
                          <td>{t(`inventory.batchSource.${b.source}`)}</td>
                          <td className="ts-cell">{formatDateTime(b.received_at)}</td>
                          <td className="table-actions">
                            <button
                              className="btn-sm"
                              onClick={() => openWriteOff({
                                batchId: b.id, label: batchLabel(b.batch_number, b.id), left: b.qty_remaining,
                                name: modal.row.product_name, uom: modal.row.uom || 'pcs',
                              })}
                            >
                              {t('inventory.writeOff')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.close')}</button>
                </div>
              </>
            ) : modal.kind === 'history' ? (
              <>
                <div className="table-card">
                  <table className="data-table">
                    <thead>
                      <tr><th>{t('inventory.colWhen')}</th><th>{t('inventory.colType')}</th><th className="num">{t('inventory.colQty')}</th><th>{t('inventory.colExpiry')}</th><th>{t('inventory.colRef')}</th></tr>
                    </thead>
                    <tbody>
                      {ledger.length === 0 && <tr><td colSpan={5} className="empty-row">{t('inventory.noMovements')}</td></tr>}
                      {ledger.map((txn) => (
                        <tr key={txn.id}>
                          <td className="ts-cell">{formatDateTime(txn.created_at)}</td>
                          <td>{t(`inventory.txn.${txn.txn_type}`)}</td>
                          <td className="num">{Number(txn.qty) > 0 ? '+' : ''}{qtyText(txn.qty)} {modal.row.uom || 'pcs'}</td>
                          <td>{txn.expiry_date ?? '—'}</td>
                          <td>{txn.txn_type === 'sale' && txn.reference_id ? t('inventory.saleRef', { id: txn.reference_id }) : txn.notes ?? '—'}</td>

                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.close')}</button>
                </div>
              </>
            ) : modal.kind === 'price' ? (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">{t('inventory.priceHint', { price: formatRupees(modal.row.base_price) })}</p>
                <label className="field-label">
                  {t('inventory.priceLabel')}
                  <input
                    className="field-input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={qty}
                    placeholder={t('inventory.useHqPrice')}
                    onChange={(e) => setQty(e.target.value)}
                    autoFocus
                  />
                </label>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.save')}</button>
                </div>
              </form>
            ) : modal.kind === 'threshold' ? (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">
                  {t('inventory.thresholdHint', { qty: `${qtyText(modal.row.effective_threshold)} ${modal.row.uom || 'pcs'}` })}
                </p>
                <label className="field-label">
                  {t('inventory.lowLevelLabel', { uom: modal.row.uom || 'pcs' })}
                  <input
                    className="field-input"
                    type="number"
                    min="0"
                    step={modal.row.uom === 'pcs' || modal.row.uom === 'pack' ? '1' : '0.001'}
                    value={qty}
                    placeholder={t('inventory.useDefault')}
                    onChange={(e) => setQty(e.target.value)}
                    autoFocus
                  />
                </label>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.save')}</button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">{t('inventory.currentStock')} <strong>{qtyText(modal.row.qty_on_hand)} {modal.row.uom || 'pcs'}</strong></p>
                <label className="field-label">
                  {modal.kind === 'in' ? t('inventory.qtyReceived', { uom: modal.row.uom || 'pcs' }) : t('inventory.countedQty', { uom: modal.row.uom || 'pcs' })}
                  <input
                    className="field-input"
                    type="number"
                    min={modal.kind === 'in' ? (modal.row.uom === 'pcs' || modal.row.uom === 'pack' ? '1' : '0.001') : '0'}
                    step={modal.row.uom === 'pcs' || modal.row.uom === 'pack' ? '1' : '0.001'}
                    value={qty}
                    onChange={(e) => setQty(e.target.value)}
                    onFocus={(e) => e.target.select()}
                    required
                    autoFocus
                  />
                </label>
                {modal.kind === 'in' && (
                  <label className="field-label">
                    {t('inventory.batchOptional')}
                    <input
                      className="field-input"
                      value={batchNumber}
                      onChange={(e) => setBatchNumber(e.target.value)}
                      maxLength={100}
                    />
                  </label>
                )}
                {modal.kind === 'in' && (
                  <label className="field-label">
                    {t('inventory.expiryOptional')}
                    <input
                      className="field-input"
                      type="date"
                      value={expiryDate}
                      onChange={(e) => setExpiryDate(e.target.value)}
                    />
                  </label>
                )}
                <label className="field-label">
                  {modal.kind === 'in' ? t('inventory.noteIn') : t('inventory.reasonAdjust')}
                  <input
                    className="field-input"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    required={modal.kind === 'adjust'}
                    maxLength={500}
                    placeholder={modal.kind === 'adjust' ? t('inventory.reasonPlaceholder') : ''}
                  />
                </label>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.save')}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {writeOff && (
        <div className="modal-overlay">
          <div className="modal-box">
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setWriteOff(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>{t('inventory.titleWriteOff', { batch: writeOff.label, name: writeOff.name })}</h3>
            {woError && <div className="form-error">{woError}</div>}
            <form onSubmit={handleWriteOff} className="modal-form">
              <p className="hint-text">{t('inventory.writeOffHint', { qty: `${qtyText(writeOff.left)} ${writeOff.uom}` })}</p>
              <label className="field-label">
                {t('inventory.writeOffQty')}
                <input
                  className="field-input"
                  type="number"
                  min="0.001"
                  max={writeOff.left}
                  step={writeOff.uom === 'pcs' || writeOff.uom === 'pack' ? '1' : '0.001'}
                  value={woQty}
                  onChange={(e) => setWoQty(e.target.value)}
                  required
                  autoFocus
                />
              </label>
              <label className="field-label">
                {t('inventory.writeOffReason')}
                <input
                  className="field-input"
                  value={woReason}
                  onChange={(e) => setWoReason(e.target.value)}
                  placeholder={t('inventory.writeOffReasonPlaceholder')}
                  maxLength={200}
                  required
                />
              </label>
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setWriteOff(null)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={woSaving}>{woSaving ? t('common.saving') : t('inventory.writeOff')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
