// List and resume held bills.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { listHeld } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import { useBillStore } from '../../store/billStore';
import type { SaleOut } from '../../types/sale';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

export function HeldBillsPage() {
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
        <h2>Held Bills</h2>
        <div className="admin-actions">
          <button className="btn-secondary" onClick={() => navigate('/pos/billing')}>
            ← Back to Billing (Esc)
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      <table className="data-table">
        <thead>
          <tr>
            <th>Bill #</th><th>Started</th><th>Items</th><th>Total</th><th>Note</th><th />
          </tr>
        </thead>
        <tbody>
          {!loading && sales.length === 0 && (
            <tr><td colSpan={6} className="empty-row">No held bills in this shift.</td></tr>
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
                  Resume
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
