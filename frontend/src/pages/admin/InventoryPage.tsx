// Stock-in, adjustments, ledger, low stock, expiry alerts.
import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';
import { adjustStock, getLedger, getStockLevels, setThreshold, stockIn, getExpiringProducts } from '../../services/api/inventoryApi';
import { listStores } from '../../services/api/storeApi';
import type { StoreOut } from '../../types/api';
import type { ExpiringBatchOut, InventoryTxnOut, StockLevelOut } from '../../types/inventory';
import { formatDateTime } from '../../utils/format';

type Kind = 'in' | 'adjust' | 'threshold' | 'history';
type Modal = { kind: Kind; row: StockLevelOut } | null;
type Tab = 'stock' | 'expiry';

const TXN_LABEL: Record<string, string> = {
  purchase: 'Stock in',
  sale: 'Sale',
  return: 'Return',
  adjustment: 'Adjustment',
};

function qtyText(qty: string): string {
  return String(Number(qty));
}

function expiryRowStyle(days: number): { background: string } {
  if (days <= 7) return { background: '#fef2f2' };
  if (days <= 15) return { background: '#fff7ed' };
  return { background: '#fefce8' };
}

export function InventoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [stores, setStores] = useState<StoreOut[]>([]);
  const [storeId, setStoreId] = useState<number | null>(user?.store_id ?? null);
  const [rows, setRows] = useState<StockLevelOut[]>([]);
  const [filter, setFilter] = useState('');
  const [lowOnly, setLowOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [tab, setTab] = useState<Tab>('stock');
  const [expiringRows, setExpiringRows] = useState<ExpiringBatchOut[]>([]);
  const [expiryLoading, setExpiryLoading] = useState(false);
  const [expiryDate, setExpiryDate] = useState('');

  const [modal, setModal] = useState<Modal>(null);
  const [qty, setQty] = useState('');
  const [notes, setNotes] = useState('');
  const [ledger, setLedger] = useState<InventoryTxnOut[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [printOffer, setPrintOffer] = useState<{ productId: number; name: string; qty: number } | null>(null);

  useEffect(() => {
    listStores()
      .then((list) => {
        setStores(list);
        setStoreId((cur) => cur ?? list[0]?.id ?? null);
      })
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  async function fetchLevels(id = storeId) {
    if (id === null) return;
    setLoading(true);
    setError('');
    try {
      setRows(await getStockLevels(id));
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

  useEffect(() => { fetchLevels(); }, [storeId]);
  useEffect(() => { if (tab === 'expiry') fetchExpiring(); }, [tab, storeId]);

  async function open(kind: Kind, row: StockLevelOut) {
    setQty(
      kind === 'adjust' ? qtyText(row.qty_on_hand)
        : kind === 'threshold' ? (row.low_stock_threshold === null ? '' : qtyText(row.low_stock_threshold))
        : '',
    );
    setNotes('');
    setExpiryDate('');
    setFormError('');
    setLedger([]);
    setModal({ kind, row });
    if (kind === 'history' && storeId !== null) {
      try {
        setLedger(await getLedger(storeId, row.product_id));
      } catch (err) {
        setFormError(getErrorMessage(err));
      }
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!modal || storeId === null) return;
    setSaving(true);
    setFormError('');
    try {
      if (modal.kind === 'in') {
        await stockIn(storeId, modal.row.product_id, qty.trim(), notes.trim(), expiryDate || undefined);
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

  const needle = filter.trim().toLowerCase();
  const visible = rows.filter(
    (r) =>
      (!lowOnly || r.is_low) &&
      (!needle || r.product_name.toLowerCase().includes(needle) || (r.barcode ?? '').includes(needle)),
  );
  const lowCount = rows.filter((r) => r.is_low).length;

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>Inventory</h2>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="tab-bar">
        <button
          className={`tab-btn${tab === 'stock' ? ' tab-active' : ''}`}
          onClick={() => setTab('stock')}
        >
          Stock Levels
        </button>
        <button
          className={`tab-btn${tab === 'expiry' ? ' tab-active' : ''}`}
          onClick={() => setTab('expiry')}
        >
          Expiry Alerts
          {expiringRows.length > 0 && <span className="badge-count"> {expiringRows.length}</span>}
        </button>
      </div>

      {tab === 'stock' && (
        <>
          <div className="filter-bar">
            <select
              className="field-input filter-input"
              value={storeId ?? ''}
              onChange={(e) => setStoreId(Number(e.target.value))}
            >
              {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <input
              className="field-input filter-input"
              placeholder="Search name or barcode"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <label className="field-label checkbox-label">
              <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
              Low / out of stock only ({lowCount})
            </label>
          </div>

          {printOffer && (
            <div className="notice-bar">
              Received {printOffer.qty} × {printOffer.name}.
              <button
                className="btn-primary btn-compact"
                onClick={() => navigate(
                  `/admin/labels?product=${printOffer.productId}&qty=${printOffer.qty}`,
                  { state: { from: '/admin/inventory' } },
                )}
              >
                Print {printOffer.qty} labels
              </button>
              <button className="btn-sm" onClick={() => setPrintOffer(null)}>Dismiss</button>
            </div>
          )}

          {loading && <div className="loading-text">Loading…</div>}

          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Barcode</th>
                  <th className="num">In stock</th>
                  <th className="num">Low at</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {!loading && visible.length === 0 && (
                  <tr><td colSpan={6} className="empty-row">No products match.</td></tr>
                )}
                {visible.map((r) => (
                  <tr key={r.product_id}>
                    <td>{r.product_name}</td>
                    <td>{r.barcode ?? '—'}</td>
                    <td className="num">{qtyText(r.qty_on_hand)} {r.uom || 'pcs'}</td>
                    <td className="num" title={r.low_stock_threshold === null ? 'Store-wide default (Settings)' : 'Set for this product'}>
                      {qtyText(r.effective_threshold)} {r.uom || 'pcs'}{r.low_stock_threshold === null && <span className="status-muted"> (default)</span>}
                    </td>
                    <td>
                      {Number(r.qty_on_hand) <= 0
                        ? <span className="stock-badge stock-out">Out of stock</span>
                        : r.is_low ? <span className="stock-badge stock-low">Low</span> : '—'}
                    </td>
                    <td className="table-actions">
                      <button className="btn-sm" onClick={() => open('in', r)}>Stock In</button>
                      <button className="btn-sm" onClick={() => open('adjust', r)}>Adjust</button>
                      <button className="btn-sm" onClick={() => open('threshold', r)}>Low level</button>
                      <button className="btn-sm" onClick={() => open('history', r)}>History</button>
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
          <div className="filter-bar">
            <select
              className="field-input filter-input"
              value={storeId ?? ''}
              onChange={(e) => setStoreId(Number(e.target.value))}
            >
              {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <button className="btn-secondary" onClick={() => fetchExpiring()}>Refresh</button>
          </div>

          {expiryLoading && <div className="loading-text">Loading expiry data…</div>}

          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Barcode</th>
                  <th className="num">In Stock</th>
                  <th>Expiry Date</th>
                  <th className="num">Days Left</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {!expiryLoading && expiringRows.length === 0 && (
                  <tr><td colSpan={6} className="empty-row">No products expiring within 30 days.</td></tr>
                )}
                {expiringRows.map((r) => (
                  <tr key={r.product_id} style={expiryRowStyle(r.days_to_expiry)}>
                    <td>{r.product_name}</td>
                    <td>{r.barcode ?? '—'}</td>
                    <td className="num">{qtyText(r.qty_on_hand)} {r.uom}</td>
                    <td>{r.nearest_expiry}</td>
                    <td className="num">{r.days_to_expiry}d</td>
                    <td>
                      <button
                        className="btn-primary btn-sm"
                        onClick={() => navigate(
                          `/admin/discounts?product_id=${r.product_id}&product_name=${encodeURIComponent(r.product_name)}&ends_at=${r.nearest_expiry}`,
                        )}
                      >
                        Create Offer
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint-text">
            Colour key: <span style={{ background: '#fef2f2', padding: '0 6px' }}>≤7 days</span>{' '}
            <span style={{ background: '#fff7ed', padding: '0 6px' }}>≤15 days</span>{' '}
            <span style={{ background: '#fefce8', padding: '0 6px' }}>≤30 days</span>
          </p>
        </>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className={`modal-box${modal.kind === 'history' ? ' modal-wide' : ''}`} onClick={(e) => e.stopPropagation()}>
            <h3>
              {{ in: 'Stock In', adjust: 'Adjust Stock', threshold: 'Low-Stock Level', history: 'Stock History' }[modal.kind]}
              {' — '}{modal.row.product_name}
            </h3>
            {formError && <div className="form-error">{formError}</div>}

            {modal.kind === 'history' ? (
              <>
                <div className="table-card">
                  <table className="data-table">
                    <thead>
                      <tr><th>When</th><th>Type</th><th className="num">Qty</th><th>Expiry</th><th>Ref / Note</th></tr>
                    </thead>
                    <tbody>
                      {ledger.length === 0 && <tr><td colSpan={5} className="empty-row">No movements yet.</td></tr>}
                      {ledger.map((t) => (
                        <tr key={t.id}>
                          <td className="ts-cell">{formatDateTime(t.created_at)}</td>
                          <td>{TXN_LABEL[t.txn_type] ?? t.txn_type}</td>
                          <td className="num">{Number(t.qty) > 0 ? '+' : ''}{qtyText(t.qty)} {modal.row.uom || 'pcs'}</td>
                          <td>{t.expiry_date ?? '—'}</td>
                          <td>{t.txn_type === 'sale' && t.reference_id ? `Sale #${t.reference_id}` : t.notes ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Close</button>
                </div>
              </>
            ) : modal.kind === 'threshold' ? (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">
                  The product shows as "Low" when stock is at or below this level. Leave empty to use the store-wide
                  default from Settings (currently {qtyText(modal.row.effective_threshold)} {modal.row.uom || 'pcs'}).
                </p>
                <label className="field-label">
                  Low-stock level ({modal.row.uom || 'pcs'})
                  <input
                    className="field-input"
                    type="number"
                    min="0"
                    step={modal.row.uom === 'pcs' || modal.row.uom === 'pack' ? '1' : '0.001'}
                    value={qty}
                    placeholder="Use default"
                    onChange={(e) => setQty(e.target.value)}
                    autoFocus
                  />
                </label>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">Currently in stock: <strong>{qtyText(modal.row.qty_on_hand)} {modal.row.uom || 'pcs'}</strong></p>
                <label className="field-label">
                  {modal.kind === 'in' ? `Quantity received (${modal.row.uom || 'pcs'})` : `Counted quantity (${modal.row.uom || 'pcs'})`}
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
                    Expiry date (optional)
                    <input
                      className="field-input"
                      type="date"
                      value={expiryDate}
                      onChange={(e) => setExpiryDate(e.target.value)}
                    />
                  </label>
                )}
                <label className="field-label">
                  {modal.kind === 'in' ? 'Note (optional, e.g. supplier invoice no.)' : 'Reason (required)'}
                  <input
                    className="field-input"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    required={modal.kind === 'adjust'}
                    maxLength={500}
                    placeholder={modal.kind === 'adjust' ? 'e.g. stock-take, 2 damaged' : ''}
                  />
                </label>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
