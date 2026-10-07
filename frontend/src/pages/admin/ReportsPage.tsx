// Sales, GST and shift reports.
import { useEffect, useState } from 'react';
import { AdminNav } from '../../components/admin/AdminNav';
import { StoreFilter } from '../../components/admin/StoreFilter';
import { getErrorMessage } from '../../services/api/httpClient';
import { getSalesReport, getShiftReport } from '../../services/api/reportApi';
import type { SalesReportOut, ShiftRow } from '../../types/report';
import { downloadCsv } from '../../utils/csv';
import { formatDateTime, isoDateIst, monthStartIst } from '../../utils/format';
import { formatRupees } from '../../utils/money';

type Tab = 'sales' | 'gst' | 'shifts';
const METHOD_LABEL: Record<string, string> = { cash: 'Cash', card: 'Card', upi: 'UPI', split: 'Split' };

const QUICK_RANGES: { label: string; from: () => string; to: () => string }[] = [
  { label: 'Today', from: () => isoDateIst(), to: () => isoDateIst() },
  { label: 'Yesterday', from: () => isoDateIst(1), to: () => isoDateIst(1) },
  { label: 'Last 7 days', from: () => isoDateIst(6), to: () => isoDateIst() },
  { label: 'This month', from: monthStartIst, to: () => isoDateIst() },
];

export function ReportsPage() {
  const [tab, setTab] = useState<Tab>('sales');
  const [storeId, setStoreId] = useState<number | null>(null);
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
        ['GST rate %', 'Taxable value', 'CGST', 'SGST', 'Total GST'],
        sales.gst.map((g) => [g.tax_rate, g.taxable, g.cgst, g.sgst, g.tax]),
      );
    } else {
      downloadCsv(
        `shifts_${range}.csv`,
        ['Shift', 'Cashier', 'Counter', 'Opened', 'Closed', 'Bills', 'Opening float', 'Cash sales', 'Expected', 'Counted', 'Difference'],
        shifts.map((s) => [
          s.id, s.cashier_name, s.counter_code, s.opened_at, s.closed_at, s.bills,
          s.opening_float, s.cash_sales, s.expected_cash, s.actual_cash, s.difference,
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
        <h2>Reports</h2>
        <div className="admin-actions no-print">
          <button className="btn-secondary" onClick={exportCsv} disabled={!sales}>Download CSV</button>
          <button className="btn-secondary" onClick={() => window.print()} disabled={!sales}>Print</button>
        </div>
      </div>

      <div className="filter-bar no-print">
        <StoreFilter value={storeId} onChange={setStoreId} />
        <input className="field-input filter-input" type="date" value={dateFrom} max={dateTo} onChange={(e) => setDateFrom(e.target.value)} />
        <span className="filter-sep">to</span>
        <input className="field-input filter-input" type="date" value={dateTo} min={dateFrom} max={isoDateIst()} onChange={(e) => setDateTo(e.target.value)} />
        {QUICK_RANGES.map((r) => (
          <button key={r.label} className="btn-sm" onClick={() => { setDateFrom(r.from()); setDateTo(r.to()); }}>{r.label}</button>
        ))}
      </div>

      <div className="tab-bar no-print" role="tablist">
        {(['sales', 'gst', 'shifts'] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>
            {{ sales: 'Sales', gst: 'GST Summary', shifts: 'Shifts & Cash' }[t]}
          </button>
        ))}
      </div>

      <p className="print-only report-title">
        {{ sales: 'Sales report', gst: 'GST summary', shifts: 'Shifts & cash' }[tab]} — {dateFrom === dateTo ? dateFrom : `${dateFrom} to ${dateTo}`}
      </p>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      {sales && s && tab === 'sales' && (
        <>
          <div className="stat-grid">
            <div className="stat-tile"><span className="stat-label">Net sales (incl. GST)</span><span className="stat-value">{formatRupees(s.total)}</span></div>
            <div className="stat-tile"><span className="stat-label">Bills</span><span className="stat-value">{s.bills}</span><span className="stat-sub">Avg {formatRupees(s.average_bill)} · {s.voided} voided</span></div>
            <div className="stat-tile"><span className="stat-label">Gross (before discount)</span><span className="stat-value">{formatRupees(s.subtotal)}</span></div>
            <div className="stat-tile"><span className="stat-label">Discounts</span><span className="stat-value">{formatRupees(s.discount)}</span></div>
            <div className="stat-tile"><span className="stat-label">GST</span><span className="stat-value">{formatRupees(s.tax)}</span></div>
          </div>

          <div className="dash-columns">
            <section>
              <h3 className="section-title">By payment method</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead><tr><th>Method</th><th className="num">Bills</th><th className="num">Amount</th></tr></thead>
                  <tbody>
                    {sales.by_method.length === 0 && <tr><td colSpan={3} className="empty-row">No sales in this period.</td></tr>}
                    {sales.by_method.map((m) => (
                      <tr key={m.method}><td>{METHOD_LABEL[m.method] ?? m.method}</td><td className="num">{m.bills}</td><td className="num">{formatRupees(m.amount)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3 className="section-title">Day by day</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead><tr><th>Date</th><th className="num">Bills</th><th className="num">Total</th></tr></thead>
                  <tbody>
                    {sales.daily.length === 0 && <tr><td colSpan={3} className="empty-row">No sales in this period.</td></tr>}
                    {sales.daily.map((d) => (
                      <tr key={d.day}><td>{d.day}</td><td className="num">{d.bills}</td><td className="num">{formatRupees(d.total)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h3 className="section-title">Top products</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead><tr><th>Product</th><th className="num">Qty</th><th className="num">Amount (excl. GST)</th></tr></thead>
                  <tbody>
                    {sales.top_products.length === 0 && <tr><td colSpan={3} className="empty-row">No sales in this period.</td></tr>}
                    {sales.top_products.map((p) => (
                      <tr key={p.product_id}><td>{p.product_name}</td><td className="num">{p.qty}</td><td className="num">{formatRupees(p.amount)}</td></tr>
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
          <p className="hint-text">Intra-state sales: GST is split equally into CGST and SGST. Taxable value is after discounts.</p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th className="num">GST rate</th><th className="num">Taxable value</th><th className="num">CGST</th><th className="num">SGST</th><th className="num">Total GST</th></tr>
              </thead>
              <tbody>
                {sales.gst.length === 0 && <tr><td colSpan={5} className="empty-row">No sales in this period.</td></tr>}
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
                    <td className="num">Total</td>
                    <td className="num">{formatRupees(gstTotals.taxable)}</td>
                    <td className="num">{formatRupees(gstTotals.cgst)}</td>
                    <td className="num">{formatRupees(gstTotals.sgst)}</td>
                    <td className="num">{formatRupees(gstTotals.tax)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </>
      )}

      {tab === 'shifts' && !loading && (
        <>
          <p className="hint-text">Expected cash = opening float + cash taken on the shift's bills. Difference = counted − expected (negative means cash short).</p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Cashier</th><th>Counter</th><th>Opened</th><th>Closed</th><th className="num">Bills</th>
                  <th className="num">Float</th><th className="num">Cash sales</th><th className="num">Expected</th><th className="num">Counted</th><th className="num">Difference</th>
                </tr>
              </thead>
              <tbody>
                {shifts.length === 0 && <tr><td colSpan={10} className="empty-row">No shifts opened in this period.</td></tr>}
                {shifts.map((r) => {
                  const diff = r.difference === null ? null : Number(r.difference);
                  return (
                    <tr key={r.id}>
                      <td>{r.cashier_name}</td>
                      <td>{r.counter_code ?? '—'}</td>
                      <td className="ts-cell">{formatDateTime(r.opened_at)}</td>
                      <td className="ts-cell">{r.closed_at ? formatDateTime(r.closed_at) : <span className="stock-badge stock-low">Open</span>}</td>
                      <td className="num">{r.bills}</td>
                      <td className="num">{formatRupees(r.opening_float)}</td>
                      <td className="num">{formatRupees(r.cash_sales)}</td>
                      <td className="num">{r.expected_cash === null ? '—' : formatRupees(r.expected_cash)}</td>
                      <td className="num">{r.actual_cash === null ? '—' : formatRupees(r.actual_cash)}</td>
                      <td className="num">
                        {diff === null ? '—' : diff === 0 ? 'OK' : (
                          <span className={`stock-badge ${diff < 0 ? 'stock-out' : 'stock-low'}`}>
                            {diff < 0 ? 'Short ' : 'Over '}{formatRupees(Math.abs(diff))}
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
