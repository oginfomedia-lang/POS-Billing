// Sales, GST and shift reports.
import type { ParseKeys } from 'i18next';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { getErrorMessage } from '../../services/api/httpClient';
import { getSalesReport, getShiftReport } from '../../services/api/reportApi';
import type { SalesReportOut, ShiftRow } from '../../types/report';
import { downloadCsv } from '../../utils/csv';
import { formatDateTime, isoDateIst, monthStartIst } from '../../utils/format';
import { formatRupees } from '../../utils/money';
import { useStoreContext, useStoreDisplayName } from '../../store/storeContext';

type Tab = 'sales' | 'gst' | 'shifts';
const QUICK_RANGES: { label: ParseKeys; from: () => string; to: () => string }[] = [
  { label: 'reports.today', from: () => isoDateIst(), to: () => isoDateIst() },
  { label: 'reports.yesterday', from: () => isoDateIst(1), to: () => isoDateIst(1) },
  { label: 'reports.last7', from: () => isoDateIst(6), to: () => isoDateIst() },
  { label: 'reports.thisMonth', from: monthStartIst, to: () => isoDateIst() },
];

export function ReportsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('sales');
  const storeId = useStoreContext((s) => s.selectedId);
  const storeName = useStoreDisplayName();
  const [dateFrom, setDateFrom] = useState(isoDateIst());
  const [dateTo, setDateTo] = useState(isoDateIst());

  const [sales, setSales] = useState<SalesReportOut | null>(null);
  const [shifts, setShifts] = useState<ShiftRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!dateFrom || !dateTo) return;
    const filter = { store_id: storeId, date_from: dateFrom, date_to: dateTo };
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([getSalesReport(filter), getShiftReport(filter)])
      .then(([s, sh]) => { if (!cancelled) { setSales(s); setShifts(sh); } })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [storeId, dateFrom, dateTo]);

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
        {(['sales', 'gst', 'shifts'] as Tab[]).map((tabKey) => (
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
            <div className="stat-tile">
              <span className="stat-label">{t('reports.netSales')}</span>
              <span className="stat-value">{formatRupees(s.net_total)}</span>
              {s.returns > 0 && <span className="stat-sub">{t('reports.salesMinusReturns', { sales: formatRupees(s.total), returns: formatRupees(s.refunded) })}</span>}
            </div>
            <div className="stat-tile">
              <span className="stat-label">{t('reports.returns')}</span>
              <span className="stat-value">{formatRupees(s.refunded)}</span>
              <span className="stat-sub">{t('reports.returnsCount', { count: s.returns })}</span>
            </div>
            <div className="stat-tile"><span className="stat-label">{t('reports.bills')}</span><span className="stat-value">{s.bills}</span><span className="stat-sub">{t('reports.avgVoided', { avg: formatRupees(s.average_bill), voided: s.voided })}</span></div>
            <div className="stat-tile"><span className="stat-label">{t('reports.gross')}</span><span className="stat-value">{formatRupees(s.subtotal)}</span></div>
            <div className="stat-tile"><span className="stat-label">{t('reports.discounts')}</span><span className="stat-value">{formatRupees(s.discount)}</span></div>
            <div className="stat-tile"><span className="stat-label">{t('reports.gst')}</span><span className="stat-value">{formatRupees(s.tax)}</span></div>
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
