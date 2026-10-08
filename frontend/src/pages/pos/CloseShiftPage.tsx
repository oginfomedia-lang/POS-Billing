import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useShiftStore } from '../../store/shiftStore';
import { getErrorMessage } from '../../services/api/httpClient';

export function CloseShiftPage() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { shift, close, busy } = useShiftStore();
  const navigate = useNavigate();

  const [actualCash, setActualCash] = useState('0');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await close(parseFloat(actualCash) || 0);
      setDone(true);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  if (done) {
    return (
      <div className="admin-page">
        <div className="admin-header">
          <h2>{t('shift.closedTitle')}</h2>
          <div className="admin-actions">
            <button className="btn-secondary" onClick={logout}>{t('common.logout')}</button>
          </div>
        </div>
        <div className="shift-panel shift-panel-center">
          <p className="shift-done-text">{t('shift.closedOk')}</p>
          <button className="btn-primary" onClick={() => navigate('/', { replace: true })}>
            {t('shift.backToLogin')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>{t('shift.closeTitle', { name: user?.full_name ?? user?.username })}</h2>
        <div className="admin-actions">
          <button className="btn-secondary" onClick={() => navigate('/pos/billing')}>{t('shift.backToPos')}</button>
          <button className="btn-secondary" onClick={logout}>{t('common.logout')}</button>
        </div>
      </div>

      <div className="shift-panel">
        {shift && (
          <div className="shift-summary">
            <div className="shift-summary-row">
              <span>{t('shift.openingFloat')}</span>
              <strong>₹{Number(shift.opening_float).toFixed(2)}</strong>
            </div>
            {shift.expected_cash !== null && (
              <div className="shift-summary-row">
                <span>{t('shift.expectedCash')}</span>
                <strong>₹{Number(shift.expected_cash).toFixed(2)}</strong>
              </div>
            )}
          </div>
        )}

        {error && <div className="page-error">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field-label">
            {t('shift.actualCash')}
            <input
              className="field-input"
              type="number"
              min="0"
              step="0.01"
              value={actualCash}
              onChange={(e) => setActualCash(e.target.value)}
            />
          </label>
          <div className="modal-buttons">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? t('shift.closing') : t('shift.close')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
