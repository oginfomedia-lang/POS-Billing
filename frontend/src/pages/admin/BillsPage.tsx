// Bills and returns for a date range — where the dashboard and report tiles lead.
// Same dates, branch and "paid bills only" rules as the sales report, so the totals here match the tiles.
// Filters live in the address (?tab=&from=&to=&status=&method=&discount=1&q=), so a tile can open the page
// already filtered, and coming back from a bill keeps them.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { getErrorMessage } from '../../services/api/httpClient';
import { getBills, getReturns } from '../../services/api/reportApi';
import { useStoreContext, useStoreDisplayName } from '../../store/storeContext';
import type { BillListOut, ReturnListOut } from '../../types/report';
import { formatDateTime, isoDateIst, monthStartIst } from '../../utils/format';
import { formatRupees } from '../../utils/money';

type Tab = 'bills' | 'returns';
type Method = '' | 'cash' | 'card' | 'upi';
const PER_PAGE = 50;
const SEARCH_DELAY_MS = 350;

const QUICK_RANGES = [
  { label: 'reports.today', from: () => isoDateIst(), to: () => isoDateIst() },
  { label: 'reports.yesterday', from: () => isoDateIst(1), to: () => isoDateIst(1) },
  { label: 'reports.last7', from: () => isoDateIst(6), to: () => isoDateIst() },
  { label: 'reports.thisMonth', from: monthStartIst, to: () => isoDateIst() },
] as const;

export function BillsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const storeId = useStoreContext((s) => s.selectedId);
  const storeName = useStoreDisplayName();

  const tab: Tab = params.get('tab') === 'returns' ? 'returns' : 'bills';
  const from = params.get('from') || isoDateIst();
  const to = params.get('to') || from;
  const status = params.get('status') === 'voided' ? 'voided' : 'paid';
  const method = (['cash', 'card', 'upi'].includes(params.get('method') ?? '') ? params.get('method') : '') as Method;
  const discounted = params.get('discount') === '1';
  const q = params.get('q') ?? '';
  const page = Math.max(1, Number(params.get('page')) || 1);

  const [search, setSearch] = useState(q);
  const [bills, setBills] = useState<BillListOut | null>(null);
  const [returns, setReturns] = useState<ReturnListOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const requestNo = useRef(0);

  /** Change filters (any filter change goes back to page 1). Replaces the history entry: Back leaves the page. */
  function update(changes: Record<string, string | null>, keepPage = false) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === '') next.delete(k);
      else next.set(k, v);
    }
    if (!keepPage) next.delete('page');
    setParams(next, { replace: true });
  }

  // Bill-number search applies after a short pause.
  useEffect(() => {
    if (search === q) return;
    const timer = window.setTimeout(() => update({ q: search.trim() || null }), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const mine = ++requestNo.current;
    setLoading(true);
    setError('');
    const range = { store_id: storeId, date_from: from, date_to: to, page, per_page: PER_PAGE };
    const load = tab === 'returns'
      ? getReturns(range).then((r) => { if (mine === requestNo.current) setReturns(r); })
      : getBills({ ...range, status, method: method || undefined, discounted, q: q || undefined })
          .then((r) => { if (mine === requestNo.current) setBills(r); });
    load
      .catch((err) => { if (mine === requestNo.current) setError(getErrorMessage(err)); })
      .finally(() => { if (mine === requestNo.current) setLoading(false); });
  }, [tab, from, to, status, method, discounted, q, page, storeId]);

  const data = tab === 'returns' ? returns : bills;
  const pages = data?.pages ?? 1;

  return (
    <div className="admin-page bills-page">
      <AdminNav />
      <div className="admin-header">
        <div>
          <h2>{t('bills.title')}</h2>
          <p className="hint-text">{storeName} · {from === to ? from : t('reports.range', { from, to })}</p>
        </div>
      </div>

      <div className="tab-bar" role="tablist">
        {(['bills', 'returns'] as Tab[]).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} className={`tab${tab === k ? ' active' : ''}`}
                  onClick={() => update({ tab: k === 'bills' ? null : k })}>
            {t(k === 'bills' ? 'bills.tabBills' : 'bills.tabReturns')}
          </button>
        ))}
      </div>

      <div className="filter-bar">
        {QUICK_RANGES.map((r) => (
          <button key={r.label} type="button" className={`btn-sm${from === r.from() && to === r.to() ? ' btn-sm-active' : ''}`}
                  onClick={() => update({ from: r.from(), to: r.to() })}>
            {t(r.label)}
          </button>
        ))}
        <input className="field-input filter-input" type="date" value={from} max={to} aria-label={t('bills.from')}
               onChange={(e) => e.target.value && update({ from: e.target.value })} />
        <span className="hint-text">{t('reports.to')}</span>
        <input className="field-input filter-input" type="date" value={to} min={from} max={isoDateIst()} aria-label={t('bills.to')}
               onChange={(e) => e.target.value && update({ to: e.target.value })} />
      </div>

      {tab === 'bills' && (
        <div className="filter-bar">
          <select className="field-input filter-input" value={status} aria-label={t('bills.colStatus')}
                  onChange={(e) => update({ status: e.target.value === 'voided' ? 'voided' : null })}>
            <option value="paid">{t('bills.statusPaid')}</option>
            <option value="voided">{t('bills.statusVoided')}</option>
          </select>
          <select className="field-input filter-input" value={method} aria-label={t('bills.colPayment')}
                  onChange={(e) => update({ method: e.target.value || null })}>
            <option value="">{t('bills.allMethods')}</option>
            <option value="cash">{t('methods.cash')}</option>
            <option value="card">{t('methods.card')}</option>
            <option value="upi">{t('methods.upi')}</option>
          </select>
          <label className="checkbox-label">
            <input type="checkbox" checked={discounted} onChange={(e) => update({ discount: e.target.checked ? '1' : null })} />
            {t('bills.discountedOnly')}
          </label>
          <input className="field-input filter-input" placeholder={t('bills.searchBill')} value={search}
                 onChange={(e) => setSearch(e.target.value)} />
        </div>
      )}

      {error && <div className="page-error">{error}</div>}

      {data && (
        <div className="bills-totals">
          {tab === 'bills' && bills ? (
            <>
              <span><strong>{bills.totals.count}</strong> {t('bills.billsWord', { count: bills.totals.count })}</span>
              <span>{t('bills.colTotal')} <strong>{formatRupees(bills.totals.total)}</strong></span>
              <span>{t('bills.colDiscount')} <strong>{formatRupees(bills.totals.discount)}</strong></span>
              <span>{t('bills.colGst')} <strong>{formatRupees(bills.totals.tax)}</strong></span>
            </>
          ) : returns ? (
            <>
              <span><strong>{returns.totals.count}</strong> {t('bills.returnsWord', { count: returns.totals.count })}</span>
              <span>{t('bills.colRefund')} <strong>{formatRupees(returns.totals.total)}</strong></span>
            </>
          ) : null}
          {loading && <span className="hint-text">{t('common.loading')}</span>}
        </div>
      )}

      <div className="table-card">
        {tab === 'bills' ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('bills.colBill')}</th><th>{t('bills.colTime')}</th><th>{t('bills.colCashier')}</th>
                <th className="num">{t('bills.colItems')}</th><th>{t('bills.colPayment')}</th>
                <th className="num">{t('bills.colDiscount')}</th><th className="num">{t('bills.colGst')}</th>
                <th className="num">{t('bills.colTotal')}</th><th className="num">{t('bills.colRefunded')}</th>
              </tr>
            </thead>
            <tbody>
              {bills?.items.length === 0 && !loading && (
                <tr><td colSpan={9} className="empty-row">{t('bills.empty')}</td></tr>
              )}
              {bills?.items.map((b) => (
                <tr key={b.id} className={b.status === 'paid' ? 'clickable-row' : undefined}
                    onClick={b.status === 'paid' ? () => navigate(`/pos/reprint/${b.id}?from=bills`) : undefined}
                    title={b.status === 'paid' ? t('bills.openHint') : undefined}>
                  <td className="mono">{b.bill_number ?? `#${b.id}`}</td>
                  <td>{formatDateTime(b.at)}</td>
                  <td>{b.cashier_name}{b.counter_code ? ` · ${b.counter_code}` : ''}</td>
                  <td className="num">{b.items_count}</td>
                  <td>{b.methods.length ? b.methods.map((m) => t(`methods.${m}`)).join(' + ') : '—'}</td>
                  <td className="num">{Number(b.discount) > 0 ? formatRupees(b.discount) : '—'}</td>
                  <td className="num">{formatRupees(b.tax)}</td>
                  <td className="num"><strong>{formatRupees(b.total)}</strong></td>
                  <td className="num">{Number(b.refunded) > 0 ? `− ${formatRupees(b.refunded)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('bills.colReturnNo')}</th><th>{t('bills.colTime')}</th><th>{t('bills.colBill')}</th>
                <th>{t('bills.colCashier')}</th><th>{t('bills.colApprovedBy')}</th><th>{t('bills.colReason')}</th>
                <th className="num">{t('bills.colItems')}</th><th className="num">{t('bills.colRefund')}</th>
              </tr>
            </thead>
            <tbody>
              {returns?.items.length === 0 && !loading && (
                <tr><td colSpan={8} className="empty-row">{t('bills.emptyReturns')}</td></tr>
              )}
              {returns?.items.map((r) => (
                <tr key={r.id} className="clickable-row" onClick={() => navigate(`/pos/return-receipt/${r.id}`)}
                    title={t('bills.openReturnHint')}>
                  <td className="mono">{r.return_number ?? `#${r.id}`}</td>
                  <td>{formatDateTime(r.created_at)}</td>
                  <td className="mono">{r.bill_number ?? '—'}</td>
                  <td>{r.cashier_name}</td>
                  <td>{r.approved_by_name}</td>
                  <td>{r.reason}</td>
                  <td className="num">{r.items_count}</td>
                  <td className="num"><strong>− {formatRupees(r.refund_amount)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => update({ page: String(page - 1) }, true)}>{t('common.prev')}</button>
        <span>{t('common.pageInfo', { page, total: data?.totals.count ?? 0 })}</span>
        <button disabled={page >= pages} onClick={() => update({ page: String(page + 1) }, true)}>{t('common.next')}</button>
      </div>
    </div>
  );
}
