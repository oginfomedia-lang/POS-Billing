// Stock-in, adjustments, ledger, low stock.
import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';
import { adjustStock, getLedger, getStockLevels, setThreshold, stockIn } from '../../services/api/inventoryApi';
import { listStores } from '../../services/api/storeApi';
import type { StoreOut } from '../../types/api';
import type { InventoryTxnOut, StockLevelOut } from '../../types/inventory';
import { formatDateTime } from '../../utils/format';

type Kind = 'in' | 'adjust' | 'threshold' | 'history';
type Modal = { kind: Kind; row: StockLevelOut } | null;

const TXN_LABEL: Record<string, string> = {
  purchase: 'Stock in',
  sale: 'Sale',
  return: 'Return',
  adjustment: 'Adjustment',
};

/** "12.500" -> "12.5" */
function qtyText(qty: string): string {
  return String(Number(qty));
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

  const [modal, setModal] = useState<Modal>(null);
  const [qty, setQty] = useState('');
  const [notes, setNotes] = useState('');
  const [ledger, setLedger] = useState<InventoryTxnOut[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  // After goods are received, offer to print that many stickers.
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

  useEffect(() => { fetchLevels(); }, [storeId]);

  async function open(kind: Kind, row: StockLevelOut) {
    setQty(
      kind === 'adjust' ? qtyText(row.qty_on_hand)
        : kind === 'threshold' ? (row.low_stock_threshold === null ? '' : qtyText(row.low_stock_threshold))
        : '',
    );
    setNotes('');
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
        await stockIn(storeId, modal.row.product_id, qty.trim(), notes.trim());
        const received = Number(qty);
        setPrintOffer(
          Number.isInteger(received) && modal.row.barcode
            ? { productId: modal.row.product_id, name: modal.row.product_name, qty: received }
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

      <table className="data-table">
        <thead>
          <tr><th>Product</th><th>Barcode</th><th className="num">In stock</th><th className="num">Low at</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {!loading && visible.length === 0 && (
            <tr><td colSpan={6} className="empty-row">No products match.</td></tr>
          )}
          {visible.map((r) => (
            <tr key={r.product_id}>
              <td>{r.product_name}</td>
              <td>{r.barcode ?? '—'}</td>
              <td className="num">{qtyText(r.qty_on_hand)}</td>
              <td className="num" title={r.low_stock_threshold === null ? 'Store-wide default (Settings)' : 'Set for this product'}>
                {qtyText(r.effective_threshold)}{r.low_stock_threshold === null && <span className="status-muted"> (default)</span>}
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
                <table className="data-table">
                  <thead>
                    <tr><th>When</th><th>Type</th><th className="num">Qty</th><th>Ref / Note</th></tr>
                  </thead>
                  <tbody>
                    {ledger.length === 0 && <tr><td colSpan={4} className="empty-row">No movements yet.</td></tr>}
                    {ledger.map((t) => (
                      <tr key={t.id}>
                        <td className="ts-cell">{formatDateTime(t.created_at)}</td>
                        <td>{TXN_LABEL[t.txn_type] ?? t.txn_type}</td>
                        <td className="num">{Number(t.qty) > 0 ? '+' : ''}{qtyText(t.qty)}</td>
                        <td>{t.txn_type === 'sale' && t.reference_id ? `Sale #${t.reference_id}` : t.notes ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="modal-buttons">
                  <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Close</button>
                </div>
              </>
            ) : modal.kind === 'threshold' ? (
              <form onSubmit={handleSubmit} className="modal-form">
                <p className="hint-text">
                  The product shows as "Low" when stock is at or below this level. Leave empty to use the store-wide
                  default from Settings (currently {qtyText(modal.row.effective_threshold)}).
                </p>
                <label className="field-label">
                  Low-stock level
                  <input
                    className="field-input"
                    type="number"
                    min="0"
                    step="any"
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
                <p className="hint-text">Currently in stock: <strong>{qtyText(modal.row.qty_on_hand)}</strong></p>
                <label className="field-label">
                  {modal.kind === 'in' ? 'Quantity received' : 'Counted quantity (new stock level)'}
                  <input
                    className="field-input"
                    type="number"
                    min={modal.kind === 'in' ? '0.001' : '0'}
                    step="any"
                    value={qty}
                    onChange={(e) => setQty(e.target.value)}
                    onFocus={(e) => e.target.select()}
                    required
                    autoFocus
                  />
                </label>
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
