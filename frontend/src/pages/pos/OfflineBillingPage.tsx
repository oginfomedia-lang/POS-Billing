// Cash billing while the server can't be reached. Uses this PC's copy of the product list, prices and offers
// (src/offline), saves each bill on this PC, and the bills upload by themselves when the server is back
// (hooks/useOfflineSync). Needs a shift opened on this PC while the server was up.
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { IconCash, IconLogOut, IconShoppingCart, IconTrash, IconX } from '../../components/common/Icons';
import { useAuth } from '../../hooks/useAuth';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useServerStatusStore } from '../../hooks/useServerStatus';
import { changeDue, priceCart } from '../../offline/bill';
import { Dec } from '../../offline/decimal';
import { scan, search } from '../../offline/lookup';
import { loadCatalog, queuedBills } from '../../offline/sync';
import type { OfflineBill, OfflineCatalog, OfflineProduct } from '../../offline/types';
import { openDrawer } from '../../services/hardware/printerService';
import { useCounterStore } from '../../store/counterStore';
import { useOfflineStore } from '../../store/offlineStore';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

const QUICK_CASH = [100, 200, 500, 2000];

export function OfflineBillingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const online = useServerStatusStore((s) => s.status === 'online');
  const counterCode = useCounterStore((s) => s.config?.counterCode ?? 'C00');
  const { lastShift, cart, add, setQty, remove, clearCart } = useOfflineStore();
  const shift = lastShift && user && lastShift.user_id === user.id ? lastShift : null;

  const [catalog, setCatalog] = useState<OfflineCatalog | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [weighing, setWeighing] = useState<OfflineProduct | null>(null);
  const [kg, setKg] = useState('');
  const [paying, setPaying] = useState(false);
  const [tendered, setTendered] = useState('');
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<OfflineBill[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!shift) { setLoaded(true); return; }
    loadCatalog(shift.store_id).then(setCatalog).finally(() => setLoaded(true));
  }, [shift?.store_id]);

  useEffect(() => {
    queuedBills().then((bills) => setRefused(bills.filter((b) => b.sync_error))).catch(() => undefined);
  }, []);

  const priced = useMemo(() => (catalog ? priceCart(cart, catalog, new Date()) : null), [cart, catalog]);
  const suggestions = useMemo(() => (catalog && code.trim().length >= 2 ? search(catalog, code, 8) : []), [catalog, code]);
  const total = priced?.bill.total ?? '0.00';
  const hasItems = cart.length > 0;
  const tenderedOk = tendered.trim() !== '' && !Dec.of(tendered || '0').lt(total);

  function addProduct(product: OfflineProduct, qty = '1') {
    if (product.is_variable_weight && qty === '1') {
      setKg('');
      setWeighing(product);
      return;
    }
    add(product, qty);
    setCode('');
    setError('');
    input.current?.focus();
  }

  function handleScan(e: FormEvent) {
    e.preventDefault();
    if (!catalog || !code.trim()) return;
    const result = scan(catalog, code);
    if (result.ok) {
      addProduct(result.hit.product, result.hit.qty);
      return;
    }
    if (suggestions.length === 1) {
      addProduct(suggestions[0]);
      return;
    }
    setError(result.reason === 'zero-weight' ? t('offline.zeroWeight')
      : result.reason === 'no-price' ? t('offline.noPrice')
      : result.plu ? t('offline.noScaleItem', { plu: result.plu })
      : t('offline.notFound', { code: code.trim() }));
  }

  function handleWeight(e: FormEvent) {
    e.preventDefault();
    if (!weighing || !(Number(kg) > 0)) return;
    add(weighing, Dec.of(kg).quantize(3, 'half-even').toString());
    setWeighing(null);
    setCode('');
    input.current?.focus();
  }

  function startPay() {
    if (!hasItems || !priced) return;
    setTendered(total);
    setPaying(true);
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!priced || !catalog || !shift || !user || !tenderedOk || saving) return;
    setSaving(true);
    try {
      const files = window.posBridge.offline;
      const cash = Dec.of(tendered).quantize(2).toString();
      const bill: OfflineBill = {
        offline_id: crypto.randomUUID(),
        bill_number: await files.nextBillNumber(counterCode),
        shift_id: shift.id,
        billed_at: new Date().toISOString(),
        items: priced.items,
        bill_offer_id: priced.bill.bill_offer_id,
        bill_offer_name: priced.bill.bill_offer_name,
        bill_offer_discount: priced.bill.bill_offer_discount,
        subtotal: priced.bill.subtotal,
        discount_amount: priced.bill.discount_amount,
        tax_amount: priced.bill.tax_amount,
        total: priced.bill.total,
        cash_tendered: cash,
        change_due: changeDue(priced.bill.total, cash),
        cashier_id: user.id,
        cashier_name: user.full_name || user.username,
        counter_code: counterCode,
        store: catalog.store,
        settings: catalog.settings,
      };
      await files.queueBill(bill);
      useOfflineStore.setState((s) => ({ pending: s.pending + 1 }));
      clearCart();
      openDrawer(); // don't wait: a drawer problem must not hold up the bill
      navigate(`/pos/offline/receipt/${bill.offline_id}?print=1`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  async function retry(bill: OfflineBill) {
    const again: OfflineBill = { ...bill, sync_error: null };
    await window.posBridge.offline.queueBill(again);
    setRefused((r) => r.filter((b) => b.offline_id !== bill.offline_id));
  }

  const popupOpen = paying || weighing !== null;
  useKeyboardShortcuts({ F12: startPay }, !popupOpen);
  useKeyboardShortcuts({ Escape: () => { setPaying(false); setWeighing(null); } }, popupOpen);

  const blocked = !shift ? t('offline.noShift') : loaded && !catalog ? t('offline.noCatalog') : null;

  return (
    <div className="billing-page">
      <header className="billing-topbar">
        <div className="pos-brand-tag">
          <IconShoppingCart size={22} color="#4f46e5" />
          <span className="pos-counter-title">{t('offline.title')}{catalog ? ` — ${catalog.store.name}` : ''}</span>
        </div>
        {catalog && shift && (
          <form className="offline-scan" onSubmit={handleScan}>
            <input
              ref={input}
              className="field-input"
              value={code}
              onChange={(e) => { setCode(e.target.value); setError(''); }}
              placeholder={t('offline.scanPlaceholder')}
              autoFocus
              disabled={popupOpen}
            />
            {suggestions.length > 0 && (
              <ul className="offline-suggestions">
                {suggestions.map((p) => (
                  <li key={p.id}>
                    <button type="button" onClick={() => addProduct(p)}>
                      <span>{p.name}</span>
                      <span className="status-muted">{formatRupees(p.price)}{p.is_variable_weight ? '/kg' : ''}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </form>
        )}
        <div className="billing-meta">
          <span className="cashier-chip"><span className="cashier-name">{user?.full_name || user?.username}</span></span>
          <button className="btn-logout-icon" onClick={logout} title={t('common.logout')}>
            <IconLogOut size={16} />
          </button>
        </div>
      </header>

      {online ? (
        <div className="notice-bar notice-info">
          {t('offline.serverBack')}
          <button className="btn-primary btn-compact" onClick={() => navigate('/pos/billing')} disabled={hasItems}>
            {t('offline.backToNormal')}
          </button>
        </div>
      ) : (
        <div className="notice-bar">{t('offline.banner')}</div>
      )}
      {catalog && <p className="hint-text offline-catalog-age">{t('offline.catalogAge', { when: formatDateTime(catalog.generated_at) })}</p>}
      {refused.map((b) => (
        <div key={b.offline_id} className="page-error">
          <span>{t('offline.refused', { bill: b.bill_number, error: b.sync_error })}</span>
          <button className="btn-sm error-retry" onClick={() => retry(b)}>{t('offline.retry')}</button>
        </div>
      ))}
      {blocked && <div className="page-error">{blocked}</div>}
      {error && <div className="page-error">{error}</div>}

      {!blocked && priced && (
        <div className="billing-body">
          <section className="billing-cart">
            <div className="table-card">
              <table className="data-table">
                <thead>
                  <tr><th>{t('offline.colItem')}</th><th className="num">{t('offline.colQty')}</th><th className="num">{t('offline.colRate')}</th><th className="num">{t('offline.colAmount')}</th><th /></tr>
                </thead>
                <tbody>
                  {!hasItems && <tr><td colSpan={5} className="empty-row">{t('offline.empty')}</td></tr>}
                  {cart.map((line, i) => {
                    const item = priced.items[i];
                    const step = line.product.is_variable_weight ? '0.001' : '1';
                    return (
                      <tr key={line.product.id}>
                        <td>
                          {line.product.name}
                          {Number(item.offer_discount) > 0 && (
                            <div className="status-muted">{item.offer_name}: −{formatRupees(item.offer_discount)}</div>
                          )}
                        </td>
                        <td className="num">
                          <input
                            className="field-input offline-qty"
                            type="number"
                            min={step}
                            step={step}
                            value={line.qty}
                            onChange={(e) => Number(e.target.value) > 0 && setQty(line.product.id, e.target.value)}
                          />
                        </td>
                        <td className="num">{formatRupees(item.unit_price)}</td>
                        <td className="num">{formatRupees(item.line_total)}</td>
                        <td className="table-actions">
                          <button className="btn-sm" onClick={() => remove(line.product.id)} title={t('offline.remove')}>
                            <IconTrash size={14} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
          <aside className="offline-summary">
            <div className="receipt-row"><span>{t('offline.subtotal')}</span><span>{formatRupees(priced.bill.subtotal)}</span></div>
            {Number(priced.bill.discount_amount) > 0 && (
              <div className="receipt-row">
                <span>{priced.bill.bill_offer_name ?? t('offline.discount')}</span><span>− {formatRupees(priced.bill.discount_amount)}</span>
              </div>
            )}
            <div className="receipt-row"><span>{t('offline.gst')}</span><span>{formatRupees(priced.bill.tax_amount)}</span></div>
            <div className="receipt-row receipt-total"><span>{t('offline.total')}</span><span>{formatRupees(total)}</span></div>
            <button className="btn-primary btn-icon offline-pay" disabled={!hasItems} onClick={startPay}>
              <IconCash size={18} />
              <span>{t('offline.payCash')}</span>
            </button>
            <button
              className="btn-secondary"
              disabled={!hasItems}
              onClick={() => window.confirm(t('offline.clearConfirm')) && clearCart()}
            >
              {t('offline.clear')}
            </button>
          </aside>
        </div>
      )}

      {weighing && (
        <div className="modal-overlay">
          <div className="modal-box">
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setWeighing(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>{t('offline.weightFor', { name: weighing.name })}</h3>
            <form onSubmit={handleWeight} className="modal-form">
              <input className="field-input" type="number" min="0.001" step="0.001" value={kg}
                     onChange={(e) => setKg(e.target.value)} required autoFocus />
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setWeighing(null)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary">{t('common.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {paying && priced && (
        <div className="modal-overlay">
          <div className="modal-box">
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setPaying(false)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>{t('offline.total')}: {formatRupees(total)}</h3>
            <form onSubmit={handleSave} className="modal-form">
              <label className="field-label">
                {t('offline.cashReceived')}
                <input className="field-input" type="number" min="0" step="0.01" value={tendered}
                       onChange={(e) => setTendered(e.target.value)} onFocus={(e) => e.target.select()} required autoFocus />
              </label>
              <div className="table-actions">
                {QUICK_CASH.map((n) => (
                  <button key={n} type="button" className="btn-sm" onClick={() => setTendered(String(n))}>₹{n}</button>
                ))}
              </div>
              {tenderedOk
                ? <p className="receipt-row receipt-total"><span>{t('offline.change')}</span><span>{formatRupees(changeDue(total, tendered))}</span></p>
                : tendered.trim() !== '' && <div className="form-error">{t('offline.short')}</div>}
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setPaying(false)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={!tenderedOk || saving}>
                  {saving ? t('offline.saving') : t('offline.confirm')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
