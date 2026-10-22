import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ShiftCashSummary } from '../../components/pos/ShiftCashSummary';
import { useAuth } from '../../hooks/useAuth';
import { useShiftStore } from '../../store/shiftStore';
import { getErrorMessage } from '../../services/api/httpClient';
import { getShiftBills } from '../../services/api/shiftApi';
import type { ShiftSummary } from '../../types/shift';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';

export function CloseShiftPage() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { shift, close, busy } = useShiftStore();
  const navigate = useNavigate();

  const [actualCash, setActualCash] = useState('0');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  // The server's own figures for this shift (the same ones close_shift saves as expected cash).
  const [summary, setSummary] = useState<ShiftSummary | null>(null);
  const [summaryError, setSummaryError] = useState('');

  useEffect(() => {
    if (!shift || shift.status !== 'open') return;
    getShiftBills(shift.id)
      .then((d) => setSummary(d.summary))
      .catch((err) => setSummaryError(getErrorMessage(err)));
  }, [shift?.id]);

  // Counted − expected, in paise so ₹0.10 + ₹0.20 style sums stay exact. Negative = cash short.
  const diffPaise = summary && actualCash.trim() !== '' && !Number.isNaN(Number(actualCash))
    ? toPaise(actualCash) - toPaise(summary.expected_cash)
    : null;

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
          <button className="btn-secondary" onClick={() => navigate('/pos/shift/bills')}>{t('shift.viewBills')}</button>
          <button className="btn-secondary" onClick={logout}>{t('common.logout')}</button>
        </div>
      </div>

      <div className="shift-panel">
        {summary && <ShiftCashSummary summary={summary} />}
        {summaryError && <div className="page-error">{t('shift.loadFailed', { error: summaryError })}</div>}
        {shift && !summary && (
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
            <span className="hint-text">{t('shift.countHint')}</span>
          </label>
          {diffPaise !== null && (
            <div className={`shift-diff ${diffPaise < 0 ? 'shift-diff-short' : diffPaise > 0 ? 'shift-diff-over' : 'shift-diff-ok'}`}>
              <span>{t('shift.difference')}</span>
              <strong>
                {diffPaise === 0
                  ? t('shift.matches')
                  : t(diffPaise < 0 ? 'shift.short' : 'shift.over', { amount: formatRupees(paiseToString(Math.abs(diffPaise))) })}
              </strong>
            </div>
          )}
          {/* Held bills belong to this shift: they must be paid or voided before it can close (the server checks too). */}
          {summary && summary.held_bills > 0 && (
            <div className="page-error">
              <span>{t('shift.heldBlocksClose', { count: summary.held_bills })}</span>
              <button type="button" className="btn-sm" onClick={() => navigate('/pos/held')}>{t('shift.openHeld')}</button>
            </div>
          )}
          <div className="modal-buttons">
            <button type="submit" className="btn-primary" disabled={busy || (summary?.held_bills ?? 0) > 0}>
              {busy ? t('shift.closing') : t('shift.close')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
