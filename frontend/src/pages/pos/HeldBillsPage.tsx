// List and resume held bills.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { listHeld } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import { useBillStore } from '../../store/billStore';
import type { SaleOut } from '../../types/sale';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

export function HeldBillsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { resume, busy } = useBillStore();

  const [sales, setSales] = useState<SaleOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useKeyboardShortcuts({ Escape: () => navigate('/pos/billing') });

  useEffect(() => {
    listHeld()
      .then(setSales)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  async function handleResume(id: number) {
    setError('');
    try {
      await resume(id);
      navigate('/pos/billing');
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>{t('held.title')}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" onClick={() => navigate('/pos/billing')}>
            {t('held.back')}
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('held.colBill')}</th><th>{t('held.colStarted')}</th><th>{t('held.colItems')}</th><th>{t('held.colTotal')}</th><th>{t('held.colNote')}</th><th />
            </tr>
          </thead>
          <tbody>
            {!loading && sales.length === 0 && (
              <tr><td colSpan={6} className="empty-row">{t('held.empty')}</td></tr>
            )}
            {sales.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td className="ts-cell">{formatDateTime(s.created_at)}</td>
                <td>{s.items.reduce((n, i) => n + i.qty, 0)}</td>
                <td>{formatRupees(s.total)}</td>
                <td>{s.note ?? '—'}</td>
                <td>
                  <button className="btn-primary btn-compact" disabled={busy} onClick={() => handleResume(s.id)}>
                    {t('held.resume')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
