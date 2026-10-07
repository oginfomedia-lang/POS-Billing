// Today's sales summary.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { StoreFilter } from '../../components/admin/StoreFilter';
import {
  IconAlert,
  IconBarChart,
  IconCash,
  IconFileText,
  IconPercent,
  IconReceipt,
  IconStore,
} from '../../components/common/Icons';
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
        <div>
          <span className="page-pretitle">Real-Time Overview</span>
          <h2>Supermarket Dashboard{data ? ` — ${new Date(data.date).toLocaleDateString('en-IN', { dateStyle: 'medium' })}` : ''}</h2>
        </div>
        <div className="admin-actions">
          <StoreFilter value={storeId} onChange={setStoreId} />
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {!data && !error && <div className="loading-text">Loading supermarket metrics…</div>}

      {data && s && (
        <>
          <div className="stat-grid">
            <div className="stat-tile stat-tile-sales">
              <div className="stat-icon-wrapper sales">
                <IconCash size={20} />
              </div>
              <span className="stat-label">Total Sales (incl. GST)</span>
              <span className="stat-value">{formatRupees(s.total)}</span>
            </div>

            <div className="stat-tile stat-tile-bills">
              <div className="stat-icon-wrapper bills">
                <IconReceipt size={20} />
              </div>
              <span className="stat-label">Completed Bills</span>
              <span className="stat-value">{s.bills}</span>
              <span className="stat-sub">Avg Basket: {formatRupees(s.average_bill)}</span>
            </div>

            <div className="stat-tile stat-tile-discounts">
              <div className="stat-icon-wrapper discounts">
                <IconPercent size={20} />
              </div>
              <span className="stat-label">Discounts Given</span>
              <span className="stat-value">{formatRupees(s.discount)}</span>
            </div>

            <div className="stat-tile stat-tile-tax">
              <div className="stat-icon-wrapper tax">
                <IconFileText size={20} />
              </div>
              <span className="stat-label">GST Collected</span>
              <span className="stat-value">{formatRupees(s.tax)}</span>
            </div>

            <button className="stat-tile stat-link stat-tile-shifts" onClick={() => navigate('/admin/reports')}>
              <div className="stat-icon-wrapper shifts">
                <IconStore size={20} />
              </div>
              <span className="stat-label">Active Shifts</span>
              <span className="stat-value">{data.open_shifts}</span>
              <span className="stat-sub">Voided Bills Today: {s.voided} →</span>
            </button>

            <button className="stat-tile stat-link stat-tile-lowstock" onClick={() => navigate('/admin/inventory')}>
              <div className={`stat-icon-wrapper ${data.low_stock ? 'alert' : 'ok'}`}>
                <IconAlert size={20} />
              </div>
              <span className="stat-label">Stock Warnings</span>
              <span className="stat-value">{data.low_stock}</span>
              <span className="stat-sub">{data.low_stock ? 'Review low stock items →' : 'All items well stocked'}</span>
            </button>
          </div>

          <div className="dash-columns">
            <section className="dash-card">
              <div className="card-header">
                <IconBarChart size={18} color="#4f46e5" />
                <h3 className="section-title">Sales by Tender Method</h3>
              </div>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Method</th>
                      <th className="num">Bills Count</th>
                      <th className="num">Total Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_method.length === 0 && (
                      <tr>
                        <td colSpan={3} className="empty-row">No sales transactions recorded yet today.</td>
                      </tr>
                    )}
                    {data.by_method.map((m) => (
                      <tr key={m.method}>
                        <td>
                          <span className={`method-badge method-${m.method}`}>
                            {METHOD_LABEL[m.method] ?? m.method}
                          </span>
                        </td>
                        <td className="num">{m.bills}</td>
                        <td className="num font-semibold">{formatRupees(m.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="dash-card">
              <div className="card-header">
                <IconReceipt size={18} color="#059669" />
                <h3 className="section-title">Latest Cashier Bills</h3>
              </div>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Bill #</th>
                      <th>Cashier</th>
                      <th>Time</th>
                      <th className="num">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_sales.length === 0 && (
                      <tr>
                        <td colSpan={4} className="empty-row">No bills completed yet.</td>
                      </tr>
                    )}
                    {data.recent_sales.map((r) => (
                      <tr key={r.id} className="clickable-row" onClick={() => navigate(`/pos/reprint/${r.id}`)} title="Click to view & reprint receipt">
                        <td><code className="bill-code">{r.bill_number}</code></td>
                        <td>{r.cashier_name}</td>
                        <td className="ts-cell">{formatDateTime(r.completed_at)}</td>
                        <td className="num font-bold text-emerald">{formatRupees(r.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
          <p className="hint-text live-refresh-hint">⚡ Live data auto-refreshes every 60 seconds.</p>
        </>
      )}
    </div>
  );
}

