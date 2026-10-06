// Today's sales summary.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { StoreFilter } from '../../components/admin/StoreFilter';
import { getErrorMessage } from '../../services/api/httpClient';
import { getDashboard } from '../../services/api/reportApi';
import type { DashboardOut } from '../../types/report';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

const METHOD_LABEL: Record<string, string> = { cash: 'Cash', card: 'Card', upi: 'UPI', split: 'Split' };
const REFRESH_MS = 60_000;

export function DashboardPage() {
  const navigate = useNavigate();
  const [storeId, setStoreId] = useState<number | null>(null);
  const [data, setData] = useState<DashboardOut | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    function load() {
      getDashboard(storeId)
        .then((d) => { if (!cancelled) { setData(d); setError(''); } })
        .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); });
    }
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [storeId]);

  const s = data?.summary;

  return (
    <div className="admin-page dashboard-page">
      <AdminNav />
      <div className="admin-header">
        <h2>Today{data ? ` — ${new Date(data.date).toLocaleDateString('en-IN', { dateStyle: 'medium' })}` : ''}</h2>
        <div className="admin-actions">
          <StoreFilter value={storeId} onChange={setStoreId} />
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {!data && !error && <div className="loading-text">Loading…</div>}

      {data && s && (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <span className="stat-label">Sales (incl. GST)</span>
              <span className="stat-value">{formatRupees(s.total)}</span>
            </div>
            <div className="stat-tile">
              <span className="stat-label">Bills</span>
              <span className="stat-value">{s.bills}</span>
              <span className="stat-sub">Avg {formatRupees(s.average_bill)}</span>
            </div>
            <div className="stat-tile">
              <span className="stat-label">Discounts given</span>
              <span className="stat-value">{formatRupees(s.discount)}</span>
            </div>
            <div className="stat-tile">
              <span className="stat-label">GST collected</span>
              <span className="stat-value">{formatRupees(s.tax)}</span>
            </div>
            <button className="stat-tile stat-link" onClick={() => navigate('/admin/reports')}>
              <span className="stat-label">Open shifts</span>
              <span className="stat-value">{data.open_shifts}</span>
              <span className="stat-sub">Voided bills today: {s.voided}</span>
            </button>
            <button className="stat-tile stat-link" onClick={() => navigate('/admin/inventory')}>
              <span className="stat-label">Low / out of stock</span>
              <span className="stat-value">{data.low_stock}</span>
              <span className="stat-sub">{data.low_stock ? 'Review stock →' : 'All stocked'}</span>
            </button>
          </div>

          <div className="dash-columns">
            <section>
              <h3 className="section-title">By payment method</h3>
              <table className="data-table">
                <thead><tr><th>Method</th><th className="num">Bills</th><th className="num">Amount</th></tr></thead>
                <tbody>
                  {data.by_method.length === 0 && <tr><td colSpan={3} className="empty-row">No sales yet today.</td></tr>}
                  {data.by_method.map((m) => (
                    <tr key={m.method}>
                      <td>{METHOD_LABEL[m.method] ?? m.method}</td>
                      <td className="num">{m.bills}</td>
                      <td className="num">{formatRupees(m.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section>
              <h3 className="section-title">Latest bills</h3>
              <table className="data-table">
                <thead><tr><th>Bill</th><th>Cashier</th><th>Time</th><th className="num">Total</th></tr></thead>
                <tbody>
                  {data.recent_sales.length === 0 && <tr><td colSpan={4} className="empty-row">No bills yet.</td></tr>}
                  {data.recent_sales.map((r) => (
                    <tr key={r.id} className="clickable-row" onClick={() => navigate(`/pos/reprint/${r.id}`)} title="Open receipt">
                      <td><code>{r.bill_number}</code></td>
                      <td>{r.cashier_name}</td>
                      <td className="ts-cell">{formatDateTime(r.completed_at)}</td>
                      <td className="num">{formatRupees(r.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
          <p className="hint-text">Refreshes every minute.</p>
        </>
      )}
    </div>
  );
}
