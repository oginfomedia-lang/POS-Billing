import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useCounterStore } from '../../store/counterStore';
import { useShiftStore } from '../../store/shiftStore';
import { getErrorMessage } from '../../services/api/httpClient';
import { listCounters } from '../../services/api/storeApi';

export function OpenShiftPage() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const counterCode = useCounterStore((s) => s.config?.counterCode ?? '');
  const { open, busy } = useShiftStore();
  const navigate = useNavigate();

  const [openingFloat, setOpeningFloat] = useState('0');
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    const storeId = user?.store_id;
    if (!storeId) {
      setError(t('shift.noStore'));
      return;
    }
    try {
      // The shift records which till it runs on; bill numbers include that counter's code.
      const counter = (await listCounters(storeId)).find((c) => c.code.toLowerCase() === counterCode.toLowerCase() && c.is_active);
      if (!counter) {
        setError(t('shift.counterMissing', { code: counterCode }));
        return;
      }
      await open(storeId, parseFloat(openingFloat) || 0, counter.id);
      navigate('/pos/billing', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>{t('shift.openTitle', { name: user?.full_name ?? user?.username, code: counterCode })}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" onClick={logout}>{t('common.logout')}</button>
        </div>
      </div>

      <div className="shift-panel">
        {error && <div className="page-error">{error}</div>}
        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field-label">
            {t('shift.openingFloatLabel')}
            <input
              className="field-input"
              type="number"
              min="0"
              step="0.01"
              value={openingFloat}
              onChange={(e) => setOpeningFloat(e.target.value)}
            />
          </label>
          <div className="modal-buttons">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? t('shift.opening') : t('shift.open')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
