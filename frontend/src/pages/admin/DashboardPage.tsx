// Today's sales summary.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconAlert, IconBarChart, IconCash, IconFileText, IconHistory, IconPercent, IconReceipt, IconStore } from '../../components/common/Icons';
import { getErrorMessage } from '../../services/api/httpClient';
import { getDashboard } from '../../services/api/reportApi';
import type { DashboardOut } from '../../types/report';
import { formatDate, formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';
import { useStoreContext, useStoreDisplayName } from '../../store/storeContext';

const REFRESH_MS = 60_000;

export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const storeId = useStoreContext((s) => s.selectedId);
  const storeName = useStoreDisplayName();

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
          <span className="page-pretitle">{t('dashboard.pretitle')}</span>
          <h2>{t('dashboard.title', { store: storeName })}{data ? ` — ${formatDate(data.date)}` : ''}</h2>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {!data && !error && <div className="loading-text">{t('dashboard.loadingMetrics', { store: storeName })}</div>}

      {data && s && (
        <>
          <div className="stat-grid">
            {/* Every tile opens the list or report behind its number (today, this branch). */}
            <button className="stat-tile stat-link stat-tile-sales" onClick={() => navigate('/admin/bills')}>
              <div className="stat-icon-wrapper sales">
                <IconCash size={20} />
              </div>
              <span className="stat-label">{t('dashboard.totalSales')}</span>
              <span className="stat-value">{formatRupees(s.net_total)}</span>
              {s.returns > 0 && (
                <span className="stat-sub">
                  {t('reports.salesMinusReturns', { sales: formatRupees(s.total), returns: formatRupees(s.refunded) })}
                </span>
              )}
            </button>

            <button className="stat-tile stat-link stat-tile-bills" onClick={() => navigate('/admin/bills')}>
              <div className="stat-icon-wrapper bills">
                <IconReceipt size={20} />
              </div>
              <span className="stat-label">{t('dashboard.completedBills')}</span>
              <span className="stat-value">{s.bills}</span>
              <span className="stat-sub">{t('dashboard.avgBasket', { amount: formatRupees(s.average_bill) })}</span>
            </button>

            <button className="stat-tile stat-link stat-tile-discounts" onClick={() => navigate('/admin/bills?discount=1')}>
              <div className="stat-icon-wrapper discounts">
                <IconPercent size={20} />
              </div>
              <span className="stat-label">{t('dashboard.discountsGiven')}</span>
              <span className="stat-value">{formatRupees(s.discount)}</span>
            </button>

            <button className="stat-tile stat-link stat-tile-tax" onClick={() => navigate('/admin/reports?tab=gst')}>
              <div className="stat-icon-wrapper tax">
                <IconFileText size={20} />
              </div>
              <span className="stat-label">{t('dashboard.gstCollected')}</span>
              <span className="stat-value">{formatRupees(s.tax)}</span>
            </button>

            <button className="stat-tile stat-link stat-tile-shifts" onClick={() => navigate('/admin/reports?tab=shifts')}>
              <div className="stat-icon-wrapper shifts">
                <IconStore size={20} />
              </div>
              <span className="stat-label">{t('dashboard.activeShifts')}</span>
              <span className="stat-value">{data.open_shifts}</span>
              <span className="stat-sub">{t('dashboard.voidedToday', { count: s.voided })}</span>
            </button>

            <button className="stat-tile stat-link stat-tile-lowstock" onClick={() => navigate('/admin/inventory')}>
              <div className={`stat-icon-wrapper ${data.low_stock ? 'alert' : 'ok'}`}>
                <IconAlert size={20} />
              </div>
              <span className="stat-label">{t('dashboard.stockWarnings')}</span>
              <span className="stat-value">{data.low_stock}</span>
              <span className="stat-sub">{data.low_stock ? t('dashboard.reviewLow') : t('dashboard.allStocked')}</span>
            </button>

            <button className="stat-tile stat-link stat-tile-expiry" onClick={() => navigate('/admin/inventory?tab=expiry')}>
              <div className={`stat-icon-wrapper ${data.near_expiry ? 'warn' : 'ok'}`}>
                <IconHistory size={20} />
              </div>
              <span className="stat-label">{t('dashboard.nearExpiry')}</span>
              <span className="stat-value">{data.near_expiry}</span>
              <span className="stat-sub">{data.near_expiry ? t('dashboard.reviewExpiry') : t('dashboard.noExpiry')}</span>
            </button>
          </div>

          <div className="dash-columns">
            <section className="dash-card">
              <div className="card-header">
                <IconBarChart size={18} color="#4f46e5" />
                <h3 className="section-title">{t('dashboard.byMethod')}</h3>
              </div>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t('dashboard.colMethod')}</th>
                      <th className="num">{t('dashboard.colBills')}</th>
                      <th className="num">{t('dashboard.colTotalAmount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_method.length === 0 && (
                      <tr>
                        <td colSpan={3} className="empty-row">{t('dashboard.noSalesToday')}</td>
                      </tr>
                    )}
                    {data.by_method.map((m) => (
                      <tr key={m.method}>
                        <td>
                          <span className={`method-badge method-${m.method}`}>
                            {t(`methods.${m.method}`)}
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
                <h3 className="section-title">{t('dashboard.latestBills')}</h3>
              </div>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t('dashboard.colBill')}</th>
                      <th>{t('dashboard.colCashier')}</th>
                      <th>{t('dashboard.colTime')}</th>
                      <th className="num">{t('dashboard.colAmount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_sales.length === 0 && (
                      <tr>
                        <td colSpan={4} className="empty-row">{t('dashboard.noBills')}</td>
                      </tr>
                    )}
                    {data.recent_sales.map((r) => (
                      <tr key={r.id} className="clickable-row" onClick={() => navigate(`/pos/reprint/${r.id}`)} title={t('dashboard.reprintHint')}>
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
          <p className="hint-text live-refresh-hint">{t('dashboard.liveHint')}</p>
        </>
      )}
    </div>
  );
}

