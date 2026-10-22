// Sales, GST, shift, per-cashier collection and (admin only) profit reports.
import type { ParseKeys } from 'i18next';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';
import { getCollectionReport, getProfitReport, getSalesReport, getShiftReport } from '../../services/api/reportApi';
import type { CollectionReportOut, ProfitReportOut, SalesReportOut, ShiftRow } from '../../types/report';
import { downloadCsv } from '../../utils/csv';
import { formatDateTime, isoDateIst, monthStartIst } from '../../utils/format';
import { formatRupees } from '../../utils/money';
import { useStoreContext, useStoreDisplayName } from '../../store/storeContext';

type Tab = 'sales' | 'gst' | 'shifts' | 'collection' | 'profit';
const QUICK_RANGES: { label: ParseKeys; from: () => string; to: () => string }[] = [
  { label: 'reports.today', from: () => isoDateIst(), to: () => isoDateIst() },
  { label: 'reports.yesterday', from: () => isoDateIst(1), to: () => isoDateIst(1) },
  { label: 'reports.last7', from: () => isoDateIst(6), to: () => isoDateIst() },
  { label: 'reports.thisMonth', from: monthStartIst, to: () => isoDateIst() },
];

/** "12.50%", or a dash when there were no sales to divide by. */
function pct(value: string | null): string {
  return value === null ? '—' : `${Number(value)}%`;
}

export function ReportsPage() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  // ?tab=gst / ?tab=shifts (dashboard tiles) and ?from=&to= open the report at that place.
  const [params] = useSearchParams();
  const asked = params.get('tab') as Tab | null;
  const [tab, setTab] = useState<Tab>(asked && ['sales', 'gst', 'shifts', 'collection', 'profit'].includes(asked) ? asked : 'sales');
  const storeId = useStoreContext((s) => s.selectedId);
  const storeName = useStoreDisplayName();
  const [dateFrom, setDateFrom] = useState(params.get('from') || isoDateIst());
  const [dateTo, setDateTo] = useState(params.get('to') || params.get('from') || isoDateIst());

  /** The bills / returns behind a tile, for the same dates (branch from the sidebar). */
  function openBills(extra = '') {
    navigate(`/admin/bills?from=${dateFrom}&to=${dateTo}${extra}`);
  }

  /** Profit tiles: down to the tables that make up the figure. */
  function showProfitDetail() {
    document.getElementById('profit-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  const [sales, setSales] = useState<SalesReportOut | null>(null);
  const [shifts, setShifts] = useState<ShiftRow[]>([]);
  const [collection, setCollection] = useState<CollectionReportOut | null>(null);
  const [profit, setProfit] = useState<ProfitReportOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!dateFrom || !dateTo) return;
    const filter = { store_id: storeId, date_from: dateFrom, date_to: dateTo };
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([
      getSalesReport(filter), getShiftReport(filter), getCollectionReport(filter),
      isAdmin ? getProfitReport(filter) : Promise.resolve(null),
    ])
      .then(([s, sh, c, p]) => { if (!cancelled) { setSales(s); setShifts(sh); setCollection(c); setProfit(p); } })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [storeId, dateFrom, dateTo, isAdmin]);

  const range = dateFrom === dateTo ? dateFrom : `${dateFrom}_to_${dateTo}`;

  function exportCsv() {
    if (!sales) return;
    if (tab === 'sales') {
      downloadCsv(`sales_${range}.csv`, ['Date', 'Bills', 'Total'], sales.daily.map((d) => [d.day, d.bills, d.total]));
    } else if (tab === 'gst') {
      downloadCsv(
        `gst_${range}.csv`,
        ['HSN', 'GST rate %', 'Taxable value', 'CGST', 'SGST', 'Total GST'],
        [
          ...sales.gst.map((g) => ['All', g.tax_rate, g.taxable, g.cgst, g.sgst, g.tax]),
          ...sales.gst_hsn.map((g) => [g.hsn_code ?? 'No HSN', g.tax_rate, g.taxable, g.cgst, g.sgst, g.tax]),
        ],
      );
    } else if (tab === 'profit') {
      if (!profit) return;
      downloadCsv(
        `profit_${range}.csv`,
        ['Product', 'Category', 'Qty', 'Sales (excl. GST)', 'Cost of goods', 'Gross profit', 'Margin %'],
        [
          ...profit.products.map((r) => [r.product_name, r.category, r.qty, r.net_sales, r.cogs, r.gross_profit, r.margin_pct]),
          ...profit.uncosted.map((r) => [r.product_name, 'No cost price', r.qty, r.net_sales, null, null, null]),
          ['Total', null, null, profit.summary.costed_sales, profit.summary.cogs, profit.summary.gross_profit, profit.summary.margin_pct],
        ],
      );
    } else if (tab === 'collection') {
      if (!collection) return;
      downloadCsv(
        `collection_${range}.csv`,
        ['Cashier', 'Counter', 'Bills', 'Cash', 'UPI', 'Card', 'Total', 'Refunds', 'Net', 'Cash short/over', 'Shift open'],
        collection.rows.map((r) => [
          r.cashier_name, r.counter_code, r.bills, r.cash, r.upi, r.card, r.total, r.refunds, r.net, r.cash_difference, r.shift_open ? 'Yes' : 'No',
        ]),
      );
    } else {
      downloadCsv(
        `shifts_${range}.csv`,
        ['Shift', 'Cashier', 'Counter', 'Opened', 'Closed', 'Bills', 'Opening float', 'Cash sales', 'Cash refunds', 'Expected', 'Counted', 'Difference'],
        shifts.map((s) => [
          s.id, s.cashier_name, s.counter_code, s.opened_at, s.closed_at, s.bills,
          s.opening_float, s.cash_sales, s.cash_refunds, s.expected_cash, s.actual_cash, s.difference,
        ]),
      );
    }
  }

  const s = sales?.summary;
  const gstTotals = sales?.gst.reduce(
    (t, g) => ({ taxable: t.taxable + Number(g.taxable), cgst: t.cgst + Number(g.cgst), sgst: t.sgst + Number(g.sgst), tax: t.tax + Number(g.tax) }),
    { taxable: 0, cgst: 0, sgst: 0, tax: 0 },
  );

  return (
    <div className="admin-page reports-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('reports.title')}</h2>
        <div className="admin-actions no-print">
          <button className="btn-secondary" onClick={exportCsv} disabled={!sales}>{t('reports.csv')}</button>
          <button className="btn-secondary" onClick={() => window.print()} disabled={!sales}>{t('common.print')}</button>
        </div>
      </div>

      <div className="filter-bar no-print">
        <input className="field-input filter-input" type="date" value={dateFrom} max={dateTo} onChange={(e) => setDateFrom(e.target.value)} />
        <span className="filter-sep">{t('reports.to')}</span>
        <input className="field-input filter-input" type="date" value={dateTo} min={dateFrom} max={isoDateIst()} onChange={(e) => setDateTo(e.target.value)} />
        {QUICK_RANGES.map((r) => (
          <button key={r.label} className="btn-sm" onClick={() => { setDateFrom(r.from()); setDateTo(r.to()); }}>{t(r.label)}</button>
        ))}
      </div>

      <div className="tab-bar no-print" role="tablist">
        {(['sales', 'gst', 'shifts', 'collection', ...(isAdmin ? ['profit'] : [])] as Tab[]).map((tabKey) => (
          <button key={tabKey} role="tab" aria-selected={tab === tabKey} className={`tab${tab === tabKey ? ' active' : ''}`} onClick={() => setTab(tabKey)}>
            {t(`reports.tabs.${tabKey}`)}
          </button>
        ))}
      </div>

      <p className="print-only report-title">
        {storeName} · {t(`reports.printTitles.${tab}`)} — {dateFrom === dateTo ? dateFrom : t('reports.range', { from: dateFrom, to: dateTo })}
      </p>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      {sales && s && tab === 'sales' && (
        <>
          <div className="stat-grid">
            <button className="stat-tile stat-link" onClick={() => openBills()}>
              <span className="stat-label">{t('reports.netSales')}</span>
              <span className="stat-value">{formatRupees(s.net_total)}</span>
              {s.returns > 0 && <span className="stat-sub">{t('reports.salesMinusReturns', { sales: formatRupees(s.total), returns: formatRupees(s.refunded) })}</span>}
            </button>
            <button className="stat-tile stat-link" onClick={() => openBills('&tab=returns')}>
              <span className="stat-label">{t('reports.returns')}</span>
              <span className="stat-value">{formatRupees(s.refunded)}</span>
              <span className="stat-sub">{t('reports.returnsCount', { count: s.returns })}</span>
            </button>
            <button className="stat-tile stat-link" onClick={() => openBills()}><span className="stat-label">{t('reports.bills')}</span><span className="stat-value">{s.bills}</span><span className="stat-sub">{t('reports.avgVoided', { avg: formatRupees(s.average_bill), voided: s.voided })}</span></button>
            <button className="stat-tile stat-link" onClick={() => openBills()}><span className="stat-label">{t('reports.gross')}</span><span className="stat-value">{formatRupees(s.subtotal)}</span></button>
            <button className="stat-tile stat-link" onClick={() => openBills('&discount=1')}><span className="stat-label">{t('reports.discounts')}</span><span className="stat-value">{formatRupees(s.discount)}</span></button>
            <button className="stat-tile stat-link" onClick={() => setTab('gst')}><span className="stat-label">{t('reports.gst')}</span><span className="stat-value">{formatRupees(s.tax)}</span></button>
          </div>

          <div className="dash-columns">
            <section>
              <h3 className="section-title">{t('reports.byMethod')}</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead><tr><th>{t('reports.colMethod')}</th><th className="num">{t('reports.bills')}</th><th className="num">{t('reports.colAmount')}</th></tr></thead>
                  <tbody>
                    {sales.by_method.length === 0 && <tr><td colSpan={3} className="empty-row">{t('reports.noSales')}</td></tr>}
                    {sales.by_method.map((m) => (
                      <tr key={m.method}><td>{t(`methods.${m.method}`)}</td><td className="num">{m.bills}</td><td className="num">{formatRupees(m.amount)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3 className="section-title">{t('reports.dayByDay')}</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead><tr><th>{t('reports.colDate')}</th><th className="num">{t('reports.bills')}</th><th className="num">{t('reports.colTotal')}</th></tr></thead>
                  <tbody>
                    {sales.daily.length === 0 && <tr><td colSpan={3} className="empty-row">{t('reports.noSales')}</td></tr>}
                    {sales.daily.map((d) => (
                      <tr key={d.day}><td>{d.day}</td><td className="num">{d.bills}</td><td className="num">{formatRupees(d.total)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h3 className="section-title">{t('reports.topProducts')}</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead><tr><th>{t('reports.colProduct')}</th><th className="num">{t('reports.colQty')}</th><th className="num">{t('reports.colAmountExcl')}</th></tr></thead>
                  <tbody>
                    {sales.top_products.length === 0 && <tr><td colSpan={3} className="empty-row">{t('reports.noSales')}</td></tr>}
                    {sales.top_products.map((p) => (
                      <tr key={p.product_id}><td>{p.product_name}</td><td className="num">{p.qty}</td><td className="num">{formatRupees(p.amount)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3 className="section-title">{t('reports.offersUsed')}</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr><th>{t('reports.colOffer')}</th><th>{t('reports.colType')}</th><th className="num">{t('reports.bills')}</th><th className="num">{t('reports.colDiscountGiven')}</th></tr>
                  </thead>
                  <tbody>
                    {sales.offers.length === 0 && <tr><td colSpan={4} className="empty-row">{t('reports.noOffers')}</td></tr>}
                    {sales.offers.map((o, i) => (
                      <tr key={`${o.kind}-${i}`}>
                        <td>{o.kind === 'manual' ? t('reports.manualDiscounts') : o.name}</td>
                        <td>{t(`reports.offerKinds.${o.kind}`)}</td>
                        <td className="num">{o.bills}</td>
                        <td className="num">{formatRupees(o.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </>
      )}

      {sales && gstTotals && tab === 'gst' && (
        <>
          <p className="hint-text">{t('reports.gstHint')}</p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th className="num">{t('reports.colGstRate')}</th><th className="num">{t('reports.colTaxable')}</th><th className="num">{t('reports.colCgst')}</th><th className="num">{t('reports.colSgst')}</th><th className="num">{t('reports.colTotalGst')}</th></tr>
              </thead>
              <tbody>
                {sales.gst.length === 0 && <tr><td colSpan={5} className="empty-row">{t('reports.noSales')}</td></tr>}
                {sales.gst.map((g) => (
                  <tr key={g.tax_rate}>
                    <td className="num">{Number(g.tax_rate)}%</td>
                    <td className="num">{formatRupees(g.taxable)}</td>
                    <td className="num">{formatRupees(g.cgst)}</td>
                    <td className="num">{formatRupees(g.sgst)}</td>
                    <td className="num">{formatRupees(g.tax)}</td>
                  </tr>
                ))}
              </tbody>
              {sales.gst.length > 0 && (
                <tfoot>
                  <tr className="total-row">
                    <td className="num">{t('reports.colTotal')}</td>
                    <td className="num">{formatRupees(gstTotals.taxable)}</td>
                    <td className="num">{formatRupees(gstTotals.cgst)}</td>
                    <td className="num">{formatRupees(gstTotals.sgst)}</td>
                    <td className="num">{formatRupees(gstTotals.tax)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          <h3 className="section-title">{t('reports.byHsn')}</h3>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th>{t('reports.colHsn')}</th><th className="num">{t('reports.colGstRate')}</th><th className="num">{t('reports.colTaxable')}</th><th className="num">{t('reports.colCgst')}</th><th className="num">{t('reports.colSgst')}</th><th className="num">{t('reports.colTotalGst')}</th></tr>
              </thead>
              <tbody>
                {sales.gst_hsn.length === 0 && <tr><td colSpan={6} className="empty-row">{t('reports.noSales')}</td></tr>}
                {sales.gst_hsn.map((g) => (
                  <tr key={`${g.hsn_code ?? '-'}-${g.tax_rate}`}>
                    <td>{g.hsn_code ?? <span className="status-muted">{t('reports.noHsn')}</span>}</td>
                    <td className="num">{Number(g.tax_rate)}%</td>
                    <td className="num">{formatRupees(g.taxable)}</td>
                    <td className="num">{formatRupees(g.cgst)}</td>
                    <td className="num">{formatRupees(g.sgst)}</td>
                    <td className="num">{formatRupees(g.tax)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {collection && tab === 'collection' && !loading && (
        <>
          <p className="hint-text">{t('reports.collectionHint')}</p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('reports.colCashier')}</th><th>{t('reports.colCounter')}</th><th className="num">{t('reports.bills')}</th>
                  <th className="num">{t('methods.cash')}</th><th className="num">{t('methods.upi')}</th><th className="num">{t('methods.card')}</th>
                  <th className="num">{t('reports.colTotal')}</th><th className="num">{t('reports.returns')}</th><th className="num">{t('reports.colNet')}</th>
                  <th className="num">{t('reports.colDifference')}</th>
                </tr>
              </thead>
              <tbody>
                {collection.rows.length === 0 && <tr><td colSpan={10} className="empty-row">{t('reports.noSales')}</td></tr>}
                {collection.rows.map((r) => {
                  const diff = r.cash_difference === null ? null : Number(r.cash_difference);
                  return (
                    <tr key={`${r.cashier_id}-${r.counter_code ?? '-'}`}>
                      <td>{r.cashier_name}</td>
                      <td>{r.counter_code ?? '—'}</td>
                      <td className="num">{r.bills}</td>
                      <td className="num">{formatRupees(r.cash)}</td>
                      <td className="num">{formatRupees(r.upi)}</td>
                      <td className="num">{formatRupees(r.card)}</td>
                      <td className="num">{formatRupees(r.total)}</td>
                      <td className="num">{Number(r.refunds) > 0 ? `− ${formatRupees(r.refunds)}` : '—'}</td>
                      <td className="num"><strong>{formatRupees(r.net)}</strong></td>
                      <td className="num">
                        {r.shift_open ? <span className="stock-badge stock-low">{t('reports.shiftOpen')}</span>
                          : diff === null ? '—' : diff === 0 ? t('reports.ok') : (
                            <span className={`stock-badge ${diff < 0 ? 'stock-out' : 'stock-low'}`}>
                              {t(diff < 0 ? 'reports.short' : 'reports.over', { amount: formatRupees(Math.abs(diff)) })}
                            </span>
                          )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {collection.rows.length > 0 && (
                <tfoot>
                  <tr className="total-row">
                    <td colSpan={2}>{t('reports.colTotal')}</td>
                    <td className="num">{collection.totals.bills}</td>
                    <td className="num">{formatRupees(collection.totals.cash)}</td>
                    <td className="num">{formatRupees(collection.totals.upi)}</td>
                    <td className="num">{formatRupees(collection.totals.card)}</td>
                    <td className="num">{formatRupees(collection.totals.total)}</td>
                    <td className="num">{Number(collection.totals.refunds) > 0 ? `− ${formatRupees(collection.totals.refunds)}` : '—'}</td>
                    <td className="num">{formatRupees(collection.totals.net)}</td>
                    <td />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </>
      )}

      {profit && tab === 'profit' && !loading && (
        <>
          <p className="hint-text">{t('reports.profitHint')}</p>
          {profit.summary.uncosted_products > 0 && (
            <div className="notice-bar notice-warn">
              {t('reports.uncostedNotice', {
                count: profit.summary.uncosted_products, amount: formatRupees(profit.summary.uncosted_sales),
              })}
            </div>
          )}
          <div className="stat-grid">
            <button className="stat-tile stat-link" onClick={() => openBills()}>
              <span className="stat-label">{t('reports.profitSales')}</span>
              <span className="stat-value">{formatRupees(profit.summary.costed_sales)}</span>
              {Number(profit.summary.returns) > 0 && (
                <span className="stat-sub">{t('reports.afterReturns', { amount: formatRupees(profit.summary.returns) })}</span>
              )}
            </button>
            <button className="stat-tile stat-link" onClick={showProfitDetail}>
              <span className="stat-label">{t('reports.cogs')}</span>
              <span className="stat-value">{formatRupees(profit.summary.cogs)}</span>
            </button>
            <button className="stat-tile stat-link" onClick={showProfitDetail}>
              <span className="stat-label">{t('reports.grossProfit')}</span>
              <span className={`stat-value${Number(profit.summary.gross_profit) < 0 ? ' profit-loss' : ''}`}>
                {formatRupees(profit.summary.gross_profit)}
              </span>
            </button>
            <button className="stat-tile stat-link" onClick={showProfitDetail}>
              <span className="stat-label">{t('reports.margin')}</span>
              <span className="stat-value">{pct(profit.summary.margin_pct)}</span>
            </button>
          </div>

          <h3 className="section-title" id="profit-detail">{t('reports.byCategory')}</h3>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('reports.colCategory')}</th><th className="num">{t('reports.colAmountExcl')}</th><th className="num">{t('reports.cogs')}</th>
                  <th className="num">{t('reports.grossProfit')}</th><th className="num">{t('reports.margin')}</th>
                </tr>
              </thead>
              <tbody>
                {profit.by_category.length === 0 && <tr><td colSpan={5} className="empty-row">{t('reports.noSales')}</td></tr>}
                {profit.by_category.map((c) => (
                  <tr key={c.category ?? '-'}>
                    <td>{c.category ?? <span className="status-muted">{t('reports.noCategory')}</span>}</td>
                    <td className="num">{formatRupees(c.net_sales)}</td>
                    <td className="num">{formatRupees(c.cogs)}</td>
                    <td className={`num${Number(c.gross_profit) < 0 ? ' profit-loss' : ''}`}>{formatRupees(c.gross_profit)}</td>
                    <td className="num">{pct(c.margin_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="section-title">{t('reports.byProduct')}</h3>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('reports.colProduct')}</th><th className="num">{t('reports.colQty')}</th><th className="num">{t('reports.colAmountExcl')}</th>
                  <th className="num">{t('reports.cogs')}</th><th className="num">{t('reports.grossProfit')}</th><th className="num">{t('reports.margin')}</th>
                </tr>
              </thead>
              <tbody>
                {profit.products.length === 0 && <tr><td colSpan={6} className="empty-row">{t('reports.noSales')}</td></tr>}
                {profit.products.map((r) => {
                  const loss = Number(r.gross_profit) < 0;
                  return (
                    <tr key={r.product_id}>
                      <td>
                        {r.product_name}
                        {loss && <> <span className="stock-badge stock-out">{t('reports.belowCost')}</span></>}
                      </td>
                      <td className="num">{r.qty}</td>
                      <td className="num">{formatRupees(r.net_sales)}</td>
                      <td className="num">{formatRupees(r.cogs)}</td>
                      <td className={`num${loss ? ' profit-loss' : ''}`}>{formatRupees(r.gross_profit)}</td>
                      <td className="num">{pct(r.margin_pct)}</td>
                    </tr>
                  );
                })}
              </tbody>
              {profit.products.length > 0 && (
                <tfoot>
                  <tr className="total-row">
                    <td colSpan={2}>{t('reports.colTotal')}</td>
                    <td className="num">{formatRupees(profit.summary.costed_sales)}</td>
                    <td className="num">{formatRupees(profit.summary.cogs)}</td>
                    <td className="num">{formatRupees(profit.summary.gross_profit)}</td>
                    <td className="num">{pct(profit.summary.margin_pct)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {profit.uncosted.length > 0 && (
            <>
              <h3 className="section-title">{t('reports.uncostedTitle')}</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr><th>{t('reports.colProduct')}</th><th className="num">{t('reports.colQty')}</th><th className="num">{t('reports.colAmountExcl')}</th></tr>
                  </thead>
                  <tbody>
                    {profit.uncosted.map((r) => (
                      <tr key={r.product_id}><td>{r.product_name}</td><td className="num">{r.qty}</td><td className="num">{formatRupees(r.net_sales)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {tab === 'shifts' && !loading && (
        <>
          <p className="hint-text">{t('reports.shiftsHint')}</p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('reports.colCashier')}</th><th>{t('reports.colCounter')}</th><th>{t('reports.colOpened')}</th><th>{t('reports.colClosed')}</th><th className="num">{t('reports.bills')}</th>
                  <th className="num">{t('reports.colFloat')}</th><th className="num">{t('reports.colCashSales')}</th><th className="num">{t('reports.colCashRefunds')}</th><th className="num">{t('reports.colExpected')}</th><th className="num">{t('reports.colCounted')}</th><th className="num">{t('reports.colDifference')}</th>
                </tr>
              </thead>
              <tbody>
                {shifts.length === 0 && <tr><td colSpan={11} className="empty-row">{t('reports.noShifts')}</td></tr>}
                {shifts.map((r) => {
                  const diff = r.difference === null ? null : Number(r.difference);
                  return (
                    <tr key={r.id}>
                      <td>{r.cashier_name}</td>
                      <td>{r.counter_code ?? '—'}</td>
                      <td className="ts-cell">{formatDateTime(r.opened_at)}</td>
                      <td className="ts-cell">{r.closed_at ? formatDateTime(r.closed_at) : <span className="stock-badge stock-low">{t('reports.open')}</span>}</td>
                      <td className="num">{r.bills}</td>
                      <td className="num">{formatRupees(r.opening_float)}</td>
                      <td className="num">{formatRupees(r.cash_sales)}</td>
                      <td className="num">{Number(r.cash_refunds) > 0 ? `− ${formatRupees(r.cash_refunds)}` : '—'}</td>
                      <td className="num">{r.expected_cash === null ? '—' : formatRupees(r.expected_cash)}</td>
                      <td className="num">{r.actual_cash === null ? '—' : formatRupees(r.actual_cash)}</td>
                      <td className="num">
                        {diff === null ? '—' : diff === 0 ? t('reports.ok') : (
                          <span className={`stock-badge ${diff < 0 ? 'stock-out' : 'stock-low'}`}>
                            {t(diff < 0 ? 'reports.short' : 'reports.over', { amount: formatRupees(Math.abs(diff)) })}
                          </span>
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
    </div>
  );
}
