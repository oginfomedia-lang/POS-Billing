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
  getRefillList,
  getStockLevels,
  setShelfMin,
  setStorePrice,
  setThreshold,
  stockIn,
  returnBatchToSupplier,
  transferStock,
  writeOffBatch,
} from '../../services/api/inventoryApi';
import { getSettings } from '../../services/api/reportApi';
import { useStoreContext, useStores } from '../../store/storeContext';
import type {
  BatchOut,
  ExpiringBatchOut,
  InventoryTxnOut,
  RefillOut,
  StockLevelOut,
  TransferDirection,
} from '../../types/inventory';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

type Tab = 'stock' | 'expiry' | 'refill';
type Kind = 'in' | 'adjust' | 'threshold' | 'price' | 'history' | 'batches' | 'move' | 'shelf';
/** What a stock-take counted: everything, or only one place. */
type Counted = 'all' | 'shop' | 'godown';
/** The batch being written off or sent back to its supplier (from the Batches window or the expiry list). */
type WriteOff = {
  batchId: number; label: string; left: string; name: string; uom: string; mode: 'write_off' | 'return';
} | null;
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
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [printOffer, setPrintOffer] = useState<{ productId: number; name: string; qty: number } | null>(null);

  // Godown (Settings → Godown). Off = one stock figure, the screen looks as before.
  const [godownOn, setGodownOn] = useState(false);
  const [refillRows, setRefillRows] = useState<RefillOut[]>([]);
  const [direction, setDirection] = useState<TransferDirection>('to_shop');
  const [counted, setCounted] = useState<Counted>('all');
  const [toGodown, setToGodown] = useState(false);
  const [woFromGodown, setWoFromGodown] = useState(false);

  useEffect(() => { getSettings().then((s) => setGodownOn(s.godown_enabled)).catch(() => {}); }, []);

  async function fetchRefill(id = storeId) {
    if (id === null || !godownOn) return;
    try {
      setRefillRows(await getRefillList(id));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  useEffect(() => { fetchRefill(); }, [storeId, godownOn]);

  /** The figure a stock-take starts from: the whole stock, or only the shelf / godown being counted. */
  function countedStart(row: StockLevelOut, what: Counted): string {
    return qtyText(what === 'shop' ? row.shop_qty : what === 'godown' ? row.godown_qty : row.qty_on_hand);
  }

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
        : kind === 'shelf' ? (row.shelf_min_qty === null ? '' : qtyText(row.shelf_min_qty))
        : '',
    );
    setDirection('to_shop');
    setCounted('all');
    setToGodown(false);
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
    setWoFromGodown(false);
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
      const qty = all ? null : woQty.trim();
      const fromGodown = godownOn && woFromGodown;
      if (writeOff.mode === 'return') {
        const ret = await returnBatchToSupplier(writeOff.batchId, qty, woReason.trim(), fromGodown);
        const amount = formatRupees(ret.amount);
        setNotice(Number(ret.applied_to_invoice) > 0
          ? t('inventory.returnDone', { number: ret.return_number, supplier: ret.supplier_name, amount })
          : t('inventory.returnDoneCredit', { number: ret.return_number, supplier: ret.supplier_name, amount }));
      } else {
        await writeOffBatch(writeOff.batchId, qty, woReason.trim(), fromGodown);
      }
      setWriteOff(null);
      fetchLevels();
      fetchRefill();
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
        await stockIn(
          storeId, modal.row.product_id, qty.trim(), notes.trim(), expiryDate || undefined, batchNumber.trim(),
          godownOn && toGodown,
        );
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
      } else if (modal.kind === 'move') {
        await transferStock(storeId, modal.row.product_id, qty.trim(), direction, notes.trim());
      } else if (modal.kind === 'shelf') {
        await setShelfMin(storeId, modal.row.product_id, qty.trim() === '' ? null : qty.trim());
      } else {
        await adjustStock(
          storeId, modal.row.product_id, qty.trim(), notes.trim(), godownOn && counted !== 'all' ? counted : null,
        );
      }
      setModal(null);
      fetchLevels();
      fetchRefill();
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
      {notice && (
        <div className="page-error" style={{ background: 'var(--ok-bg)', color: 'var(--ok-text)', borderColor: 'var(--ok-text)' }}>
          <span style={{ flex: 1 }}>{notice}</span>
          <button type="button" className="btn-sm" onClick={() => setNotice('')}>{t('common.close')}</button>
        </div>
      )}

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
        {godownOn && (
          <button
            className={`tab-btn${tab === 'refill' ? ' tab-active' : ''}`}
            onClick={() => setTab('refill')}
          >
            {t('inventory.godown.tabRefill')}
            {refillRows.length > 0 && <span className="badge-count"> {refillRows.length}</span>}
          </button>
        )}
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
                <tr>
                  <th>{t('inventory.colProduct')}</th><th>{t('inventory.colBarcode')}</th>
                  {godownOn && <th className="num">{t('inventory.godown.colShop')}</th>}
                  {godownOn && <th className="num">{t('inventory.godown.colGodown')}</th>}
                  <th className="num">{godownOn ? t('inventory.godown.colTotal') : t('inventory.colInStock')}</th>
                  <th className="num">{t('inventory.colLowAt')}</th><th className="num">{t('inventory.colPrice')}</th>
                  <th>{t('inventory.colStatus')}</th><th />
                </tr>
              </thead>
              <tbody>
                {!loading && visible.length === 0 && (
                  <tr><td colSpan={godownOn ? 9 : 7} className="empty-row">{t('inventory.empty')}</td></tr>
                )}
                {visible.map((r) => (
                  <tr key={r.product_id}>
                    <td>{r.product_name}</td>
                    <td>{r.barcode ?? '—'}</td>
                    {godownOn && <td className="num">{qtyText(r.shop_qty)} {r.uom || 'pcs'}</td>}
                    {godownOn && <td className="num">{qtyText(r.godown_qty)} {r.uom || 'pcs'}</td>}
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
                        : r.is_low ? <span className="stock-badge stock-low">{t('inventory.low')}</span> : !r.needs_refill && '—'}
                      {godownOn && r.needs_refill && (
                        <span className="stock-badge stock-low">{t('inventory.godown.refill')}</span>
                      )}
                    </td>
                    <td className="table-actions">
                      <button className="btn-sm" onClick={() => open('in', r)}>{t('inventory.stockIn')}</button>
                      {godownOn && <button className="btn-sm" onClick={() => open('move', r)}>{t('inventory.godown.move')}</button>}
                      {godownOn && <button className="btn-sm" onClick={() => open('shelf', r)}>{t('inventory.godown.shelfLevel')}</button>}
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
                            name: r.product_name, uom: r.uom || 'pcs', mode: 'write_off',
                          })}
                        >
                          {t('inventory.writeOff')}
                        </button>
                      )}
                      {r.batch_id !== null && r.batch_qty !== null && r.batch_source === 'grn' && (
                        <button
                          className="btn-sm"
                          title={t('inventory.returnHintShort')}
                          onClick={() => openWriteOff({
                            batchId: r.batch_id!, label: batchLabel(r.batch_number, r.batch_id!), left: r.batch_qty!,
                            name: r.product_name, uom: r.uom || 'pcs', mode: 'return',
                          })}
                        >
                          {t('inventory.returnToSupplier')}
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

      {tab === 'refill' && godownOn && (
        <>
          <p className="hint-text">{t('inventory.godown.refillHint')}</p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('inventory.colProduct')}</th>
                  <th className="num">{t('inventory.godown.colShop')}</th>
                  <th className="num">{t('inventory.godown.colRefillAt')}</th>
                  <th className="num">{t('inventory.godown.colGodown')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {refillRows.length === 0 && (
                  <tr><td colSpan={5} className="empty-row">{t('inventory.godown.refillEmpty')}</td></tr>
                )}
                {refillRows.map((r) => {
                  const row = rows.find((x) => x.product_id === r.product_id);
                  return (
                    <tr key={r.product_id}>
                      <td>{r.product_name}</td>
                      <td className="num">{qtyText(r.shop_qty)} {r.uom || 'pcs'}</td>
                      <td className="num">{qtyText(r.shelf_min_qty)} {r.uom || 'pcs'}</td>
                      <td className="num">{qtyText(r.godown_qty)} {r.uom || 'pcs'}</td>
                      <td className="table-actions">
                        {row && (
                          <button className="btn-primary btn-sm" onClick={() => open('move', row)}>
                            {t('inventory.godown.moveToShop')}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}


      {modal && (
        <div className="modal-overlay">
          <div className={`modal-box${modal.kind === 'history' || modal.kind === 'batches' ? ' modal-wide' : ''}`}>
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setModal(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>
              {t(({
                in: 'inventory.titleIn', adjust: 'inventory.titleAdjust', threshold: 'inventory.titleThreshold',
                price: 'inventory.titlePrice', history: 'inventory.titleHistory', batches: 'inventory.titleBatches',
                move: 'inventory.godown.titleMove', shelf: 'inventory.godown.titleShelf',
              } as const)[modal.kind], { name: modal.row.product_name })}
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
                                name: modal.row.product_name, uom: modal.row.uom || 'pcs', mode: 'write_off',
                              })}
                            >
                              {t('inventory.writeOff')}
                            </button>
                            {b.source === 'grn' && (
                              <button
                                className="btn-sm"
                                title={t('inventory.returnHintShort')}
                                onClick={() => openWriteOff({
                                  batchId: b.id, label: batchLabel(b.batch_number, b.id), left: b.qty_remaining,
                                  name: modal.row.product_name, uom: modal.row.uom || 'pcs', mode: 'return',
                                })}
                              >
                                {t('inventory.returnToSupplier')}
                              </button>
                            )}
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
            ) : modal.kind === 'move' ? (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">
                  {t('inventory.godown.where', {
                    shop: `${qtyText(modal.row.shop_qty)} ${modal.row.uom || 'pcs'}`,
                    godown: `${qtyText(modal.row.godown_qty)} ${modal.row.uom || 'pcs'}`,
                  })}
                </p>
                <label className="field-label">
                  {t('inventory.godown.direction')}
                  <select className="field-input" value={direction} onChange={(e) => setDirection(e.target.value as TransferDirection)}>
                    <option value="to_shop">{t('inventory.godown.toShop')}</option>
                    <option value="to_godown">{t('inventory.godown.toGodown')}</option>
                  </select>
                </label>
                <label className="field-label">
                  {t('inventory.godown.moveQty', { uom: modal.row.uom || 'pcs' })}
                  <input
                    className="field-input"
                    type="number"
                    min="0.001"
                    max={direction === 'to_shop' ? modal.row.godown_qty : modal.row.shop_qty}
                    step={modal.row.uom === 'pcs' || modal.row.uom === 'pack' ? '1' : '0.001'}
                    value={qty}
                    onChange={(e) => setQty(e.target.value)}
                    required
                    autoFocus
                  />
                </label>
                <label className="field-label">
                  {t('inventory.godown.moveNote')}
                  <input className="field-input" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={255} />
                </label>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('inventory.godown.move')}</button>
                </div>
              </form>
            ) : modal.kind === 'shelf' ? (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">{t('inventory.godown.shelfHint')}</p>
                <label className="field-label">
                  {t('inventory.godown.shelfLabel', { uom: modal.row.uom || 'pcs' })}
                  <input
                    className="field-input"
                    type="number"
                    min="0"
                    step={modal.row.uom === 'pcs' || modal.row.uom === 'pack' ? '1' : '0.001'}
                    value={qty}
                    placeholder={t('inventory.godown.noAlert')}
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
                {godownOn && modal.kind === 'adjust' && (
                  <label className="field-label">
                    {t('inventory.godown.counted')}
                    <select
                      className="field-input"
                      value={counted}
                      onChange={(e) => {
                        const what = e.target.value as Counted;
                        setCounted(what);
                        setQty(countedStart(modal.row, what));
                      }}
                    >
                      <option value="all">{t('inventory.godown.countAll')}</option>
                      <option value="shop">{t('inventory.godown.countShop')}</option>
                      <option value="godown">{t('inventory.godown.countGodown')}</option>
                    </select>
                  </label>
                )}
                {godownOn && modal.kind === 'in' && (
                  <label className="field-label checkbox-label">
                    <input type="checkbox" checked={toGodown} onChange={(e) => setToGodown(e.target.checked)} />
                    {t('inventory.godown.intoGodown')}
                  </label>
                )}
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
            <h3>{t(writeOff.mode === 'return' ? 'inventory.titleReturn' : 'inventory.titleWriteOff', { batch: writeOff.label, name: writeOff.name })}</h3>
            {woError && <div className="form-error">{woError}</div>}
            <form onSubmit={handleWriteOff} className="modal-form">
              <p className="hint-text">{t(writeOff.mode === 'return' ? 'inventory.returnHint' : 'inventory.writeOffHint', { qty: `${qtyText(writeOff.left)} ${writeOff.uom}` })}</p>
              <label className="field-label">
                {t(writeOff.mode === 'return' ? 'inventory.returnQty' : 'inventory.writeOffQty')}
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
              {godownOn && (
                <label className="field-label checkbox-label">
                  <input type="checkbox" checked={woFromGodown} onChange={(e) => setWoFromGodown(e.target.checked)} />
                  {t('inventory.godown.fromGodown')}
                </label>
              )}
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setWriteOff(null)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={woSaving}>
                  {woSaving ? t('common.saving') : t(writeOff.mode === 'return' ? 'inventory.returnToSupplier' : 'inventory.writeOff')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
